from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import browser_scraper as scraper

URL = "https://www.seloger.com/annonce/achat/ile-de-france/paris-75/paris-75000/267446L6C3DU"
TRACKING_URL = "https://click.by.seloger.com/?tracking=private"
PAGE = """<html><body><h1>Appartement à vendre Paris 16e</h1>
<p>Appartement de 92 m², quatre pièces, trois chambres, au troisième étage.
Prix de vente : 950 000 euros. Un balcon et une cave complètent ce bien.</p>
<img src="https://mms.seloger.com/photo/living-room.jpg"></body></html>"""


def response(status=200, body=PAGE, url=URL, headers=None):
    return SimpleNamespace(
        status_code=status, text=body, url=url, headers=headers or {}
    )


def session(*responses):
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.get = AsyncMock(side_effect=responses)
    return mock


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(scraper.settings, "seloger_browser_url", "http://browser:8000")
    monkeypatch.setattr(scraper, "_throttle", AsyncMock())


@pytest.fixture
def renderer():
    client = session()
    client.post = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"url": URL, "html": PAGE},
            request=httpx.Request("POST", "http://browser:8000/render"),
        )
    )
    with patch.object(scraper.httpx, "AsyncClient", return_value=client):
        yield client


@pytest.mark.parametrize("status", [200, 403])
async def test_challenge_recovers_listing_without_retrying_interstitial(
    configured, renderer, status, caplog
):
    challenge = response(
        status, "Please enable JS", headers={"x-datadome": "protected"}
    )
    normal = session(response(), challenge)
    with patch.object(scraper, "AsyncSession", return_value=normal):
        result = await scraper.scrape_listing(TRACKING_URL, "seloger")
    assert result.resolved_url == URL
    assert result.source_id == "267446L6C3DU"
    assert "950 000" in result.page_text
    assert result.photo_urls == ["https://mms.seloger.com/photo/living-room.jpg"]
    assert normal.get.await_count == 2
    renderer.post.assert_awaited_once_with(
        "http://browser:8000/render", json={"url": URL}
    )
    assert not any(
        getattr(record, "event", None) == "listing_access_failed"
        for record in caplog.records
    )


async def test_successful_scrape_does_not_start_browser(configured, renderer):
    with patch.object(
        scraper, "AsyncSession", return_value=session(response(), response())
    ):
        result = await scraper.scrape_listing(URL, "seloger")
    assert result.page_text
    renderer.post.assert_not_called()


async def test_fallback_is_disabled_without_endpoint(monkeypatch, renderer):
    monkeypatch.setattr(scraper.settings, "seloger_browser_url", "")
    assert await scraper._scrape_seloger_browser(URL) is None
    renderer.post.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://www.seloger.com/",
        "https://www.seloger.com.evil.example/annonce/12345678",
        "https://www.seloger.com@evil.example/annonce/12345678",
        "http://www.seloger.com/annonce/12345678",
        "https://127.0.0.1/annonce/12345678",
    ],
)
async def test_fallback_only_accepts_known_sources(configured, renderer, url):
    assert await scraper._scrape_seloger_browser(url) is None
    renderer.post.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        {
            "url": URL,
            "html": "Please enable JS <script src='https://geo.captcha-delivery.com/x'></script>",
        },
        {"url": URL, "html": ""},
        {"url": "https://evil.example/", "html": PAGE},
        {},
    ],
)
async def test_invalid_render_never_becomes_listing_text(configured, renderer, data):
    renderer.post.return_value = httpx.Response(
        200, json=data, request=httpx.Request("POST", "http://browser:8000/render")
    )
    assert await scraper._scrape_seloger_browser(URL) is None


async def test_browser_timeout_preserves_failure_without_leaking_secrets(
    configured, renderer, caplog
):
    renderer.post.side_effect = httpx.ReadTimeout("private tracking token")
    assert await scraper._scrape_seloger_browser(URL) is None
    assert "private tracking token" not in caplog.text


async def test_transport_error_on_tracking_link_can_use_browser(configured, renderer):
    with patch.object(
        scraper,
        "AsyncSession",
        return_value=session(response(), RuntimeError("HTTP2 error")),
    ):
        result = await scraper.scrape_listing(TRACKING_URL, "seloger")
    assert result.page_text
    renderer.post.assert_awaited_once_with(
        "http://browser:8000/render", json={"url": TRACKING_URL}
    )


async def test_other_sources_never_use_browser(configured, renderer):
    with patch.object(
        scraper,
        "AsyncSession",
        return_value=session(response(), RuntimeError("HTTP2 error")),
    ):
        await scraper.scrape_listing(
            "https://www.leboncoin.fr/ad/ventes_immobilieres/123", "leboncoin"
        )
    renderer.post.assert_not_called()


async def test_public_listing_query_parameters_are_removed(configured, renderer):
    result = await scraper._scrape_seloger_browser(
        URL + "?email=private@example.com#photos"
    )
    renderer.post.assert_awaited_once_with(
        "http://browser:8000/render", json={"url": URL}
    )
    assert result.resolved_url == URL


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (URL, "267446L6C3DU"),
        (URL + "/?utm_source=email", "267446L6C3DU"),
        (
            "https://www.seloger.com/annonces/achat/appartement/paris/228288697.htm",
            "228288697",
        ),
        (
            "https://www.bellesdemeures.com/annonces/vente/tt-2-tb-1-pl-48259/281994839/",
            "281994839",
        ),
    ],
)
def test_seloger_source_ids(url, expected):
    assert scraper._extract_source_id(url, "seloger") == expected


async def test_final_challenge_failure_emits_one_sanitized_alert(
    configured, renderer, caplog
):
    renderer.post.side_effect = httpx.ReadTimeout("private proxy password")
    challenge = response(403, "Please enable JS", headers={"x-datadome": "protected"})
    with patch.object(
        scraper, "AsyncSession", return_value=session(response(), challenge)
    ):
        result = await scraper.scrape_listing(TRACKING_URL, "seloger")
    assert not result.page_text
    events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "listing_access_failed"
    ]
    assert len(events) == 1
    assert events[0].listing_source == "seloger"
    assert events[0].listing_host == "www.seloger.com"
    assert events[0].http_status == 403
    assert events[0].reason == "anti_bot_challenge"
    assert not hasattr(events[0], "url")
    assert "private proxy password" not in caplog.text


@pytest.mark.parametrize("status", [404, 410, 500])
async def test_removed_listing_does_not_trigger_access_alert(
    configured, caplog, status
):
    with patch.object(
        scraper, "AsyncSession", return_value=session(response(status, body=""))
    ):
        await scraper.scrape_listing("https://www.junot.fr/annonce/test", "junot")
    events = [
        record
        for record in caplog.records
        if getattr(record, "event", None)
        in {"listing_access_failed", "listing_unavailable"}
    ]
    assert len(events) == 1
    assert events[0].event == (
        "listing_unavailable" if status in {404, 410} else "listing_access_failed"
    )
    assert events[0].listing_source == "junot"


async def test_other_provider_transport_failure_emits_access_alert(configured, caplog):
    with patch.object(
        scraper,
        "AsyncSession",
        return_value=session(RuntimeError("private credentials")),
    ):
        await scraper.scrape_listing(
            "https://www.junot.fr/annonce/test?token=private", "junot"
        )
    events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "listing_access_failed"
    ]
    assert len(events) == 1
    assert events[0].reason == "request_error"
    assert events[0].error_type == "RuntimeError"
    assert events[0].http_status is None
    assert "private credentials" not in caplog.text
    assert "token=private" not in caplog.text


async def test_empty_success_response_triggers_access_alert(configured, caplog):
    with patch.object(
        scraper, "AsyncSession", return_value=session(response(200, body=""))
    ):
        await scraper.scrape_listing("https://www.junot.fr/annonce/test", "junot")
    events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "listing_access_failed"
    ]
    assert len(events) == 1
    assert events[0].reason == "empty_page"
