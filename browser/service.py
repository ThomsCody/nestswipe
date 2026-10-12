"""Internal listing renderer with persistent direct and French proxy browsers."""

import asyncio
import fcntl
import logging
import os
import re
import socket
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
ALLOWED_HOSTS = {
    "seloger.com",
    "www.seloger.com",
    "click.by.seloger.com",
    "bellesdemeures.com",
    "www.bellesdemeures.com",
    "pap.fr",
    "www.pap.fr",
    "leboncoin.fr",
    "www.leboncoin.fr",
}
MAX_HTML_BYTES = 5 * 1024 * 1024
READY = """() => document.body && document.body.innerText.length > 500
    && !/just a moment/i.test(document.title)
    && !document.querySelector('#challenge-form')
    && !document.querySelector('iframe[src*="captcha-delivery.com"]')"""


def allowed_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def skip_resource(url: str, resource_type: str) -> bool:
    """Collect photo URLs from HTML without paying to download their contents."""
    host = urlsplit(url).hostname or ""
    # Allow the automatic device checks to load their own resources.
    if any(
        host == domain or host.endswith("." + domain)
        for domain in ("captcha-delivery.com", "challenges.cloudflare.com")
    ):
        return False
    return resource_type in {"image", "media", "font"}


def proxy_config(profile: Path) -> dict | None:
    username = os.environ.get("PROXY_USER", "")
    password = os.environ.get("PROXY_PASSWORD", "")
    if not username or not password:
        return None
    # Preserve the same Decodo session across browser/process restarts. Once a
    # provider session expires, Chromium can clear the device check again.
    session_file = profile / "proxy-session"
    session = session_file.read_text().strip() if session_file.exists() else ""
    if not re.fullmatch(r"[a-f0-9]{16}", session):
        session = uuid.uuid4().hex[:16]
        session_file.write_text(session)
    return {
        "server": "http://gate.decodo.com:7000",
        "username": f"user-{username.removeprefix('user-')}-country-fr-session-{session}",
        "password": password,
    }


def clear_stale_chromium_locks(profile: Path):
    """Recover an exclusively owned container profile without deleting cookies.

    The dedicated volume belongs to one browser service. Its advisory lock must
    be held before calling this; it also prevents concurrent replacement workers.
    Chromium embeds the old container hostname in its own persistent lock.
    """
    lock = profile / "SingletonLock"
    if not lock.is_symlink():
        return
    owner, separator, pid = os.readlink(lock).rpartition("-")
    if not separator or not pid.isdigit() or int(pid) <= 0:
        return
    if owner == socket.gethostname():
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            return
        else:
            return  # Never unlock a live local process.
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        entry = profile / name
        if entry.is_symlink():
            entry.unlink()
    logger.info("Removed stale Chromium profile locks")


class Renderer:
    def __init__(self, *, use_proxy: bool = True):
        self.use_proxy = use_proxy
        self.lock = asyncio.Lock()
        self.playwright = None
        self.context = None
        self.profile_lock = None

    async def close(self):
        if self.context:
            with suppress(Exception):
                await self.context.close()
            self.context = None
        if self.playwright:
            with suppress(Exception):
                await self.playwright.stop()
            self.playwright = None
        if self.profile_lock:
            self.profile_lock.close()
            self.profile_lock = None

    async def start(self):
        if self.context:
            return
        profile = Path(os.environ.get("PROFILE_DIR", "/data/profile"))
        if not self.use_proxy:
            profile = profile / "direct"
        profile.mkdir(parents=True, exist_ok=True)
        self.profile_lock = (profile / ".renderer.lock").open("a")
        try:
            fcntl.flock(self.profile_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.profile_lock.close()
            self.profile_lock = None
            raise
        clear_stale_chromium_locks(profile / "chromium")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(profile / "chromium"),
            headless=False,
            proxy=proxy_config(profile) if self.use_proxy else None,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

    async def render(self, url: str) -> dict:
        if not allowed_url(url):
            raise HTTPException(400, "Unsupported listing URL")
        try:
            # Includes time queued behind another scrape, not just navigation.
            async with asyncio.timeout(75):
                async with self.lock:
                    try:
                        await self.start()
                        return await self._render_page(url)
                    except BaseException:
                        # A crashed/disconnected browser must not poison later requests.
                        await self.close()
                        raise
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Browser rendering failed: %s", type(exc).__name__)
            raise HTTPException(502, "Listing could not be rendered") from None

    async def _render_page(self, url: str) -> dict:
        page = await self.context.new_page()
        status = None

        def received(response):
            nonlocal status
            if (
                response.request.is_navigation_request()
                and response.frame == page.main_frame
            ):
                status = response.status

        async def route_request(route):
            request = route.request
            if (
                request.is_navigation_request()
                and request.frame == page.main_frame
                and not allowed_url(request.url)
            ):
                await route.abort()
            elif skip_resource(request.url, request.resource_type):
                await route.abort()
            else:
                await route.continue_()

        page.on("response", received)
        await page.route("**/*", route_request)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # The initial navigation may be 403. Wait for the automatic device
            # check to reload the main document; a persistent CAPTCHA times out.
            await page.wait_for_function(READY, timeout=35000)
            if status != 200 or not allowed_url(page.url):
                raise HTTPException(502, "Listing remained blocked")
            html = await page.content()
            if len(html.encode()) > MAX_HTML_BYTES:
                raise HTTPException(502, "Listing page is too large")
            return {"url": page.url, "html": html}
        finally:
            with suppress(Exception):
                await page.close()


renderer = Renderer()
pap_renderer = Renderer(use_proxy=False)


@asynccontextmanager
async def lifespan(app):
    yield
    await renderer.close()
    await pap_renderer.close()


app = FastAPI(lifespan=lifespan)


class RenderRequest(BaseModel):
    url: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/render")
async def render(request: RenderRequest):
    if not allowed_url(request.url):
        raise HTTPException(400, "Unsupported listing URL")
    target = (
        pap_renderer
        if urlsplit(request.url).hostname in {"pap.fr", "www.pap.fr"}
        else renderer
    )
    return await target.render(request.url)
