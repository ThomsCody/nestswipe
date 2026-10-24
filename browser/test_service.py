import asyncio
import fcntl
import json
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from service import (
    Renderer,
    allowed_url,
    proxy_config,
    skip_resource,
    render,
    RenderRequest,
    clear_stale_chromium_locks,
    capture_failure,
    save_diagnostic,
    safe_title,
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

    def test_ads_and_analytics_blocked_without_blocking_listing_dependencies(self):
        for kind in ("script", "fetch", "xhr", "document"):
            for host in (
                "google-analytics.com",
                "www.google-analytics.com",
                "ad.doubleclick.net",
                "static.criteo.net",
            ):
                self.assertTrue(skip_resource(f"https://{host}/asset", kind))
        for host in (
            "www.seloger.com",
            "assets.example-cdn.com",
            "geo.captcha-delivery.com",
            "challenges.cloudflare.com",
            "google-analytics.com.example.com",
        ):
            for kind in ("script", "stylesheet", "fetch", "xhr"):
                self.assertFalse(skip_resource(f"https://{host}/asset", kind))


class RendererTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {"PROFILE_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)

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

        async def render_page(url, *, deadline=None, diagnostic=None):
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


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def page(self):
        page = MagicMock()
        page.url = URL + "?token=private-secret"
        page.is_closed.return_value = False
        page.route = AsyncMock()
        page.close = AsyncMock()
        page.wait_for_function = AsyncMock(side_effect=TimeoutError("private-secret"))
        page.evaluate = AsyncMock(
            return_value={
                "title": "Access blocked https://example.com/?token=private-secret",
                "challenge": "datadome_captcha",
                "text_chars": 120,
            }
        )
        page.screenshot = AsyncMock(return_value=b"test-png")

        async def navigate(*args, **kwargs):
            response = MagicMock(status=403, frame=page.main_frame)
            response.request.is_navigation_request.return_value = True
            page.on.call_args.args[1](response)

        page.goto = AsyncMock(side_effect=navigate)
        return page

    async def test_blocked_page_captured_before_close_and_correlated_without_secrets(
        self,
    ):
        page = self.page()
        renderer = Renderer()
        renderer.start = AsyncMock()
        renderer.close = AsyncMock()
        renderer.context = MagicMock(new_page=AsyncMock(return_value=page))
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"PROFILE_DIR": directory}),
        ):
            with self.assertLogs("service", level="WARNING") as logs:
                with self.assertRaises(HTTPException) as caught:
                    await renderer.render(page.url)
            detail = caught.exception.detail
            self.assertEqual(detail["stage"], "challenge_wait")
            self.assertEqual(detail["challenge"], "datadome_captcha")
            artifact = next((Path(directory) / "diagnostics").glob("*.json"))
            saved = json.loads(artifact.read_text())
            self.assertEqual(saved["http_status"], 403)
            self.assertEqual(saved["diagnostic_id"], detail["diagnostic_id"])
            self.assertTrue(saved["screenshot_saved"])
            self.assertEqual(artifact.with_suffix(".png").read_bytes(), b"test-png")
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(artifact.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(
                "private-secret", artifact.read_text() + str(logs.output) + str(detail)
            )
            self.assertNotIn("title", str(logs.output))
        page.close.assert_awaited_once()
        renderer.close.assert_awaited_once()

    async def test_capture_failure_does_not_replace_original_failure(self):
        page = self.page()
        page.evaluate.side_effect = RuntimeError("private-secret")
        page.screenshot.side_effect = RuntimeError("private-secret")
        diagnostic = {}
        self.assertIsNone(await capture_failure(page, diagnostic))
        self.assertEqual(diagnostic["inspection_error"], "RuntimeError")
        self.assertEqual(diagnostic["capture_error"], "RuntimeError")
        self.assertNotIn("private-secret", str(diagnostic))

    async def test_removed_page_after_challenge_is_not_a_browser_failure(self):
        for status in (404, 410):
            page = self.page()

            async def completed_check(*args, **kwargs):
                response = MagicMock(status=status, frame=page.main_frame)
                response.request.is_navigation_request.return_value = True
                page.on.call_args.args[1](response)

            page.wait_for_function = AsyncMock(side_effect=completed_check)
            renderer = Renderer()
            renderer.start = AsyncMock()
            renderer.context = MagicMock(new_page=AsyncMock(return_value=page))
            result = await renderer.render(URL)
            self.assertTrue(result["unavailable"])
            self.assertEqual(result["http_status"], status)
            self.assertEqual(result["html"], "")
            page.screenshot.assert_not_awaited()
            page.close.assert_awaited_once()

    async def test_capture_is_bounded_and_does_not_capture_external_pages(self):
        page = self.page()
        page.url = "https://untrusted.example/"
        self.assertIsNone(await capture_failure(page, {}))
        page.screenshot.assert_not_awaited()
        page.url = URL

        async def stalled(**kwargs):
            await asyncio.sleep(10)

        page.screenshot.side_effect = stalled
        with patch("service.DIAGNOSTIC_TIMEOUT_SECONDS", 0.01):
            async with asyncio.timeout(0.2):
                diagnostic = {}
                self.assertIsNone(await capture_failure(page, diagnostic))
        self.assertEqual(diagnostic["capture_error"], "TimeoutError")

    def test_artifact_count_age_and_size_are_bounded(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"PROFILE_DIR": directory}),
        ):
            root = Path(directory) / "diagnostics"
            root.mkdir()
            for suffix in ("json", "png"):
                old = root / f"www.pap.fr-old.{suffix}"
                old.write_text("expired")
                os.utime(old, (time.time() - 49 * 3600,) * 2)
            for index in range(8):
                save_diagnostic(
                    {"host": "www.seloger.com", "diagnostic_id": f"{index:032x}"},
                    b"png",
                )
            self.assertEqual(len(list(root.glob("*.json"))), 5)
            self.assertEqual(len(list(root.glob("*.png"))), 5)
            self.assertFalse(list(root.glob("www.pap.fr-*")))
            diagnostic = {
                "host": "www.bellesdemeures.com",
                "diagnostic_id": "a" * 32,
                "screenshot_saved": False,
            }
            save_diagnostic(diagnostic, b"x" * (2 * 1024 * 1024 + 1))
            self.assertFalse(diagnostic["screenshot_saved"])
            self.assertFalse(list(root.glob("www.bellesdemeures.com-*.png")))

    def test_title_redaction(self):
        self.assertEqual(
            safe_title("Blocked token=secret person@example.com"),
            "Blocked [redacted] [redacted]",
        )


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
