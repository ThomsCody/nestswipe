import asyncio
import fcntl
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from service import (
    Renderer,
    allowed_url,
    proxy_config,
    skip_resource,
    render,
    RenderRequest,
    clear_stale_chromium_locks,
)

URL = "https://www.seloger.com/annonce/achat/paris/267446L6C3DU"


class UrlTests(unittest.TestCase):
    def test_previous_container_locks_removed_without_losing_session(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            (profile / "SingletonLock").symlink_to("previous-container-123")
            (profile / "SingletonCookie").symlink_to("old-cookie-lock")
            (profile / "SingletonSocket").symlink_to("/tmp/old-chromium/socket")
            (profile / "Cookies").write_text("retained browser session")
            clear_stale_chromium_locks(profile)
            self.assertFalse((profile / "SingletonLock").is_symlink())
            self.assertFalse((profile / "SingletonCookie").is_symlink())
            self.assertFalse((profile / "SingletonSocket").is_symlink())
            self.assertEqual(
                (profile / "Cookies").read_text(), "retained browser session"
            )

    def test_live_local_browser_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            (profile / "SingletonLock").symlink_to(
                f"{socket.gethostname()}-{os.getpid()}"
            )
            clear_stale_chromium_locks(profile)
            self.assertTrue((profile / "SingletonLock").is_symlink())

    def test_known_listing_and_tracking_hosts(self):
        for url in (
            URL,
            "https://www.pap.fr/annonces/test-r123",
            "https://www.leboncoin.fr/ad/ventes_immobilieres/123",
            "https://click.by.seloger.com/?qs=test",
            "https://www.bellesdemeures.com/annonces/123/",
        ):
            self.assertTrue(allowed_url(url))

    def test_external_and_credential_urls_rejected(self):
        for url in (
            "http://www.seloger.com/",
            "https://www.seloger.com.evil.test/",
            "https://www.seloger.com@evil.test/",
            "https://user:pass@www.seloger.com/",
            "https://127.0.0.1/",
            "https://www.seloger.com:1234/",
            "https://[invalid",
        ):
            self.assertFalse(allowed_url(url))

    def test_bandwidth_savings_preserve_challenges_and_scripts(self):
        for kind in ("image", "media", "font"):
            self.assertTrue(skip_resource("https://photos.pap.fr/photo.jpg", kind))
            self.assertFalse(
                skip_resource("https://geo.captcha-delivery.com/check", kind)
            )
            self.assertFalse(
                skip_resource("https://challenges.cloudflare.com/check", kind)
            )
        self.assertFalse(skip_resource("https://www.pap.fr/app.js", "script"))
        self.assertFalse(skip_resource("https://www.pap.fr/api/listing", "fetch"))

    def test_proxy_session_survives_restart(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                "os.environ",
                {"PROXY_USER": "example", "PROXY_PASSWORD": "example-password"},
                clear=True,
            ),
        ):
            first = proxy_config(Path(directory))
            second = proxy_config(Path(directory))
            self.assertEqual(first, second)
            self.assertIn("-country-fr-session-", first["username"])
            self.assertNotIn(
                "example-password", (Path(directory) / "proxy-session").read_text()
            )


class RendererTests(unittest.IsolatedAsyncioTestCase):
    async def test_another_worker_cannot_clear_profile_locks(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"PROFILE_DIR": directory}),
        ):
            profile = Path(directory)
            chromium = profile / "chromium"
            chromium.mkdir()
            (chromium / "SingletonLock").symlink_to("previous-container-123")
            renderer = Renderer()
            with (profile / ".renderer.lock").open("a") as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    await renderer.start()
            self.assertTrue((chromium / "SingletonLock").is_symlink())
            self.assertIsNone(renderer.profile_lock)

    async def test_failure_releases_browser_for_next_request(self):
        renderer = Renderer()
        renderer.start = AsyncMock()
        renderer.close = AsyncMock()
        renderer._render_page = AsyncMock(
            side_effect=[RuntimeError("private"), {"url": URL, "html": "ok"}]
        )
        with self.assertRaises(HTTPException) as caught:
            await renderer.render(URL)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn("private", caught.exception.detail)
        renderer.close.assert_awaited_once()
        self.assertEqual((await renderer.render(URL))["html"], "ok")

    async def test_scrapes_are_serialized(self):
        renderer = Renderer()
        renderer.start = AsyncMock()
        active = 0
        maximum = 0

        async def render_page(url, *, deadline=None):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"url": url, "html": "ok"}

        renderer._render_page = render_page
        await asyncio.gather(renderer.render(URL), renderer.render(URL))
        self.assertEqual(maximum, 1)

    async def test_pap_uses_separate_direct_browser(self):
        with (
            patch("service.pap_renderer.render", new_callable=AsyncMock) as direct,
            patch("service.renderer.render", new_callable=AsyncMock) as proxied,
        ):
            url = "https://www.pap.fr/annonces/test-r123"
            await render(RenderRequest(url=url))
            direct.assert_awaited_once_with(url)
            proxied.assert_not_called()
            await render(RenderRequest(url=URL))
            proxied.assert_awaited_once_with(URL)

    async def test_disallowed_url_does_not_start_browser(self):
        renderer = Renderer()
        renderer.start = AsyncMock()
        with self.assertRaises(HTTPException):
            await renderer.render("https://127.0.0.1/")
        renderer.start.assert_not_called()

    async def test_bellesdemeures_uses_separate_persistent_proxy_session(self):
        from service import bellesdemeures_renderer

        with (
            patch(
                "service.bellesdemeures_renderer.render", new_callable=AsyncMock
            ) as belles,
            patch("service.renderer.render", new_callable=AsyncMock) as seloger,
        ):
            url = "https://www.bellesdemeures.com/annonces/vente/282384907/"
            await render(RenderRequest(url=url))
            belles.assert_awaited_once_with(url)
            seloger.assert_not_called()
            self.assertEqual(bellesdemeures_renderer.profile_name, "bellesdemeures")
            self.assertTrue(bellesdemeures_renderer.use_proxy)


class PhoneResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_number_is_returned(self):
        from unittest.mock import MagicMock
        from service import resolve_listing_phone

        page = MagicMock()
        page.url = "https://www.bellesdemeures.com/annonces/vente/282384907/"
        page.evaluate = AsyncMock(return_value="01 59 13 83 47")
        self.assertEqual(await resolve_listing_phone(page, None), "01 59 13 83 47")

    async def test_invalid_and_failed_responses_are_optional(self):
        from unittest.mock import MagicMock
        from service import resolve_listing_phone

        page = MagicMock()
        page.url = "https://www.bellesdemeures.com/annonces/vente/282384907/"
        for result in [None, {}, "", "<html>blocked</html>"]:
            page.evaluate = AsyncMock(return_value=result)
            self.assertIsNone(await resolve_listing_phone(page, None))
        page.evaluate = AsyncMock(side_effect=RuntimeError("unavailable"))
        self.assertIsNone(await resolve_listing_phone(page, None))

    async def test_other_sites_have_no_phone_request(self):
        from unittest.mock import MagicMock
        from service import resolve_listing_phone

        page = MagicMock()
        page.url = URL
        self.assertIsNone(await resolve_listing_phone(page, None))
        page.evaluate.assert_not_called()

    async def test_optional_lookup_finishes_before_outer_deadline(self):
        from unittest.mock import MagicMock
        from service import resolve_listing_phone

        page = MagicMock()
        page.url = "https://www.bellesdemeures.com/annonces/vente/282384907/"

        async def stuck(_script):
            await asyncio.sleep(10)

        page.evaluate = AsyncMock(side_effect=stuck)
        async with asyncio.timeout(0.2):
            result = await resolve_listing_phone(
                page, asyncio.get_running_loop().time() + 2.01
            )
        self.assertIsNone(result)

    async def test_no_time_left_skips_optional_lookup(self):
        from unittest.mock import MagicMock
        from service import resolve_listing_phone

        page = MagicMock()
        page.url = "https://www.bellesdemeures.com/annonces/vente/282384907/"
        self.assertIsNone(
            await resolve_listing_phone(page, asyncio.get_running_loop().time() + 1)
        )
        page.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
