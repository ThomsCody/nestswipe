import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from service import Renderer, allowed_url, proxy_config

URL = "https://www.seloger.com/annonce/achat/paris/267446L6C3DU"


class UrlTests(unittest.TestCase):
    def test_known_listing_and_tracking_hosts(self):
        for url in (
            URL,
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

        async def render_page(url):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"url": url, "html": "ok"}

        renderer._render_page = render_page
        await asyncio.gather(renderer.render(URL), renderer.render(URL))
        self.assertEqual(maximum, 1)

    async def test_disallowed_url_does_not_start_browser(self):
        renderer = Renderer()
        renderer.start = AsyncMock()
        with self.assertRaises(HTTPException):
            await renderer.render("https://127.0.0.1/")
        renderer.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
