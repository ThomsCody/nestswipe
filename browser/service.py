"""Internal listing renderer with persistent direct and French proxy browsers."""

import asyncio
import fcntl
import json
import logging
import os
import re
import socket
import time
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
DIAGNOSTIC_TIMEOUT_SECONDS = 4
DIAGNOSTIC_RETENTION_SECONDS = 48 * 60 * 60
DIAGNOSTIC_LIMIT_PER_HOST = 5
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024
# Only known advertising/analytics endpoints, not arbitrary third-party CDNs.
# Listing scripts, styles, contact APIs and challenge resources remain available.
NONESSENTIAL_HOSTS = frozenset(
    {
        "doubleclick.net",
        "googlesyndication.com",
        "googleadservices.com",
        "google-analytics.com",
        "analytics.google.com",
        "connect.facebook.net",
        "criteo.com",
        "criteo.net",
        "taboola.com",
        "outbrain.com",
        "hotjar.com",
        "hotjar.io",
        "clarity.ms",
    }
)


def safe_title(title: str) -> str:
    """Keep useful challenge titles without echoing URLs or embedded identifiers."""
    title = re.sub(r"https?://\S+|\S+@\S+", "[redacted]", title)
    title = re.sub(
        r"(?i)\b(token|password|secret|key|email|qs)\s*[=:]\s*\S+", "[redacted]", title
    )
    title = re.sub(r"[A-Za-z0-9_-]{24,}", "[redacted]", title)
    return " ".join(title.split())[:160]


def diagnostic_directory() -> Path:
    return Path(os.environ.get("PROFILE_DIR", "/data/profile")) / "diagnostics"


def save_diagnostic(diagnostic: dict, screenshot: bytes | None):
    """Private, bounded artifacts in the existing volume; never serve them over HTTP."""
    root = diagnostic_directory()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    now = time.time()
    # Sweep all hosts on each failure, including hosts that have since recovered.
    for entry in root.glob("*.*"):
        if (
            entry.suffix in {".json", ".png"}
            and entry.stat().st_mtime < now - DIAGNOSTIC_RETENTION_SECONDS
        ):
            entry.unlink(missing_ok=True)
    host = diagnostic["host"]
    records = sorted(root.glob(f"{host}-*.json"), key=lambda p: p.stat().st_mtime)
    for old in records[: max(0, len(records) - DIAGNOSTIC_LIMIT_PER_HOST + 1)]:
        old.with_suffix(".png").unlink(missing_ok=True)
        old.unlink(missing_ok=True)
    stem = f"{host}-{diagnostic['diagnostic_id']}"

    def write(path, data):
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as output:
            output.write(data)

    if screenshot is not None and len(screenshot) <= MAX_SCREENSHOT_BYTES:
        write(root / f"{stem}.png", screenshot)
        diagnostic["screenshot_saved"] = True
    write(root / f"{stem}.json", json.dumps(diagnostic).encode())


async def capture_failure(page, diagnostic: dict) -> bytes | None:
    """Inspect the failing page before it closes; diagnostics cannot prolong a scrape indefinitely."""
    screenshot = None
    try:
        async with asyncio.timeout(DIAGNOSTIC_TIMEOUT_SECONDS):
            if page.is_closed():
                diagnostic["page_closed"] = True
                return None
            if not allowed_url(page.url):
                return None
            try:
                async with asyncio.timeout(1):
                    summary = await page.evaluate("""() => {
                        const frames = Array.from(document.querySelectorAll('iframe'));
                        const urls = frames.map(frame => frame.src);
                        let challenge = 'none';
                        if (urls.some(url => /captcha-delivery\\.com\\/captcha[/?]/.test(url)))
                            challenge = 'datadome_captcha';
                        else if (urls.some(url => /captcha-delivery\\.com/.test(url)))
                            challenge = 'datadome_device_check';
                        else if (document.querySelector('#challenge-form') ||
                            urls.some(url => /challenges\\.cloudflare\\.com/.test(url)))
                            challenge = 'cloudflare';
                        return {title: document.title.slice(0, 500), challenge,
                            text_chars: (document.body?.innerText || '').length};
                    }""")
                diagnostic.update(
                    title=safe_title(summary["title"]),
                    challenge=summary["challenge"],
                    text_chars=summary["text_chars"],
                )
            except Exception as exc:
                diagnostic["inspection_error"] = type(exc).__name__
            screenshot = await page.screenshot(timeout=2000, full_page=False)
    except Exception as exc:
        diagnostic["capture_error"] = type(exc).__name__
    return screenshot


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
    if any(
        host == domain or host.endswith("." + domain) for domain in NONESSENTIAL_HOSTS
    ):
        return True
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
    def __init__(self, *, use_proxy: bool = True, profile_name: str | None = None):
        self.use_proxy = use_proxy
        self.profile_name = profile_name
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
        if self.profile_name:
            profile = profile / self.profile_name
        elif not self.use_proxy:
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
            # Service-worker requests can bypass Playwright resource routing.
            service_workers="block",
        )

    async def render(self, url: str) -> dict:
        if not allowed_url(url):
            raise HTTPException(400, "Unsupported listing URL")
        started = time.monotonic()
        diagnostic = {
            "event": "browser_render_failed",
            "diagnostic_id": uuid.uuid4().hex,
            "host": urlsplit(url).hostname,
            "stage": "queue",
            "http_status": None,
            "challenge": "unknown",
            "screenshot_saved": False,
        }
        try:
            # Includes time queued behind another scrape, not just navigation.
            async with asyncio.timeout(75) as budget:
                async with self.lock:
                    try:
                        diagnostic["stage"] = "browser_start"
                        await self.start()
                        return await self._render_page(
                            url, deadline=budget.when(), diagnostic=diagnostic
                        )
                    except BaseException:
                        # A crashed/disconnected browser must not poison later requests.
                        await self.close()
                        raise
        except (Exception, asyncio.CancelledError) as exc:
            diagnostic["error_type"] = type(exc).__name__
            diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            screenshot = diagnostic.pop("screenshot", None)
            try:
                save_diagnostic(diagnostic, screenshot)
            except Exception as storage_exc:
                diagnostic["storage_error"] = type(storage_exc).__name__
            # Page titles and screenshots stay on the private volume. Only
            # bounded fields and a random correlation ID enter centralized logs.
            logger.warning(
                json.dumps({k: v for k, v in diagnostic.items() if k != "title"})
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise HTTPException(
                502,
                {
                    "message": "Listing could not be rendered",
                    "diagnostic_id": diagnostic["diagnostic_id"],
                    "stage": diagnostic["stage"],
                    "challenge": diagnostic["challenge"],
                },
            ) from None

    async def _render_page(
        self, url: str, *, deadline: float | None = None, diagnostic: dict
    ) -> dict:
        diagnostic["stage"] = "page_open"
        page = await self.context.new_page()
        status = None

        def received(response):
            nonlocal status
            if (
                response.request.is_navigation_request()
                and response.frame == page.main_frame
            ):
                status = response.status
                diagnostic["http_status"] = status

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
            diagnostic["stage"] = "navigation"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # The initial navigation may be 403. Wait for the automatic device
            # check to reload the main document; a persistent CAPTCHA times out.
            diagnostic["stage"] = "challenge_wait"
            # Removal pages can be much shorter than real adverts. They must
            # still pass the challenge checks before being called unavailable.
            ready = (
                READY.replace("length > 500", "length > 0")
                if status in {404, 410}
                else READY
            )
            await page.wait_for_function(ready, timeout=35000)
            if status in {404, 410} and allowed_url(page.url):
                return {
                    "url": page.url,
                    "html": "",
                    "unavailable": True,
                    "http_status": status,
                }
            if status != 200 or not allowed_url(page.url):
                raise HTTPException(502, "Listing remained blocked")
            diagnostic["stage"] = "page_content"
            html = await page.content()
            if len(html.encode()) > MAX_HTML_BYTES:
                raise HTTPException(502, "Listing page is too large")
            phone = await resolve_listing_phone(page, deadline)
            return {"url": page.url, "html": html, "contact_phone": phone}
        except (Exception, asyncio.CancelledError):
            diagnostic["screenshot"] = await capture_failure(page, diagnostic)
            raise
        finally:
            with suppress(Exception):
                await page.close()


async def resolve_listing_phone(page, deadline: float | None) -> str | None:
    """Resolve the same public number as the phone button, without sending a lead."""
    if urlsplit(page.url).hostname not in {
        "www.bellesdemeures.com",
        "bellesdemeures.com",
    }:
        return None
    remaining = deadline - asyncio.get_running_loop().time() - 2 if deadline else 12
    if remaining <= 0:
        return None
    try:
        async with asyncio.timeout(min(12, remaining)):
            number = await page.evaluate(r"""async () => {
                const contact = document.querySelector('.js_agencyContact [data-contact]');
                if (!contact) return null;
                const {id, phone, agency} = contact.dataset;
                const listingId = location.pathname.replace(/\/$/, '').split('/').pop();
                if (!id || id !== listingId || !phone || !agency) return null;
                const response = await fetch('/GetNumber', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phoneNumber: phone, agencyId: agency, classifiedId: id}),
                    signal: AbortSignal.timeout(10000)
                });
                if (!response.ok) return null;
                return await response.json();
            }""")
            if isinstance(number, str) and re.fullmatch(r"[+0-9 ()\.-]{8,25}", number):
                return number
    except Exception as exc:
        logger.warning("Phone lookup unavailable: %s", type(exc).__name__)
    return None


renderer = Renderer()
pap_renderer = Renderer(use_proxy=False)
bellesdemeures_renderer = Renderer(profile_name="bellesdemeures")


@asynccontextmanager
async def lifespan(app):
    yield
    await renderer.close()
    await pap_renderer.close()
    await bellesdemeures_renderer.close()


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
    host = urlsplit(request.url).hostname
    if host in {"pap.fr", "www.pap.fr"}:
        target = pap_renderer
    elif host in {"bellesdemeures.com", "www.bellesdemeures.com"}:
        target = bellesdemeures_renderer
    else:
        target = renderer
    return await target.render(request.url)
