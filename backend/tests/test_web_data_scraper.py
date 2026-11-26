"""Recovery preserves listing identity and caches successes without request quotas."""

import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services import browser_scraper as scraper
from app.services import web_data_scraper as web
from pydantic import SecretStr

from tests.test_browser_scraper import PAGE, TRACKING_URL, URL, response, session


def listing_page(url=URL):
    return f'<html><head><link rel="canonical" href="{url}"></head>{PAGE}</html>'


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        web.settings, "decodo_web_data_api_key", SecretStr("private-api-key")
    )
    monkeypatch.setattr(
        web.settings, "decodo_web_data_state_path", str(tmp_path / "state.sqlite3")
    )
    monkeypatch.setattr(web.settings, "decodo_web_data_cache_ttl_seconds", 86400)
    monkeypatch.setattr(web, "_lock", asyncio.Lock())
    metrics = MagicMock()
    monkeypatch.setattr(web.listing_metrics, "web_data_event", metrics)
    return metrics


@pytest.fixture
def api(monkeypatch):
    fake = SimpleNamespace(
        calls=[],
        options=[],
        http_status=200,
        data={"results": [{"status_code": 200, "content": listing_page()}]},
        error=None,
    )

    async def handle(request):
        fake.calls.append(request)
        if fake.error:
            raise fake.error
        return httpx.Response(fake.http_status, json=fake.data)

    client = httpx.AsyncClient

    def factory(**options):
        fake.options.append(options)
        return client(transport=httpx.MockTransport(handle), **options)

    monkeypatch.setattr(web.httpx, "AsyncClient", factory)
    return fake


async def test_recovers_and_caches_parsed_listing_across_workers(
    state, api, monkeypatch
):
    first = await web.recover_listing(URL + "?utm_source=email")
    assert first.source_id == "267446L6C3DU"
    assert "950 000" in first.page_text
    assert first.photo_urls == ["https://mms.seloger.com/photo/living-room.jpg"]
    monkeypatch.setattr(web, "_lock", asyncio.Lock())
    second = await web.cached_listing(
        URL.replace("/achat/", "/vente/") + "?utm_source=other"
    )
    assert asdict(second) == asdict(first)
    assert len(api.calls) == 1
    assert api.calls[0].url == web.API_URL
    assert json.loads(api.calls[0].content) == {"url": URL}
    assert api.calls[0].headers["Authorization"] == "Bearer private-api-key"
    assert api.options == [
        {"timeout": 60, "trust_env": False, "follow_redirects": False}
    ]
    assert [call.args[0] for call in state.call_args_list] == [
        "requests",
        "success",
        "cache_hit",
    ]


async def test_tracking_cache_also_covers_canonical_listing(state, api):
    result = await web.recover_listing(TRACKING_URL)
    assert result.resolved_url == URL
    assert (await web.recover_listing(TRACKING_URL)).page_text
    assert (await web.cached_listing(URL)).page_text
    assert len(api.calls) == 1
    assert json.loads(api.calls[0].content) == {"url": TRACKING_URL}


async def test_resolved_tracking_link_keeps_original_alias(state, api):
    assert await web.recover_listing(URL, cache_url=TRACKING_URL)
    assert await web.cached_listing(TRACKING_URL)
    assert await web.cached_listing(URL)
    assert len(api.calls) == 1


async def test_concurrent_duplicate_callers_share_one_paid_result(state, api):
    results = await asyncio.gather(*(web.recover_listing(URL) for _ in range(8)))
    assert all(result and result.page_text for result in results)
    assert len(api.calls) == 1


async def test_failed_attempts_do_not_suppress_later_retries(state, api):
    api.error = httpx.ReadTimeout("private-api-key signed-tracking-token")
    for url in [
        URL,
        URL,
        URL.replace("267446L6C3DU", "222222222"),
        URL.replace("267446L6C3DU", "333333333"),
    ]:
        assert await web.recover_listing(url) is None
    assert len(api.calls) == 4
    assert await web.recover_listing(URL) is None
    assert len(api.calls) == 5


async def test_no_daily_request_limit(state, api):
    for i in range(25):
        source_id = f"{i:012d}"
        url = URL.replace("267446L6C3DU", source_id)
        api.data = {"results": [{"status_code": 200, "content": listing_page(url)}]}
        assert (await web.recover_listing(url)).source_id == source_id
    assert len(api.calls) == 25


async def test_expired_cache_allows_fresh_request_same_day(state, api, monkeypatch):
    clock = [1800000000.0]
    monkeypatch.setattr(web, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(web.settings, "decodo_web_data_cache_ttl_seconds", 60)
    assert await web.recover_listing(URL)
    clock[0] += 61
    assert await web.cached_listing(URL) is None
    assert await web.recover_listing(URL)
    assert len(api.calls) == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://www.seloger.com/",
        "http://www.seloger.com/annonce/12345678",
        "https://www.seloger.com.evil.test/annonce/12345678",
        "https://user:pass@www.seloger.com/annonce/12345678",
        "https://www.seloger.com:1234/annonce/12345678",
        "https://www.pap.fr/annonces/test-r12345678",
    ],
)
async def test_unsupported_urls_never_spend(state, api, url):
    assert await web.recover_listing(url) is None
    assert not api.calls


async def test_can_disable_integration_with_empty_key(state, api, monkeypatch):
    monkeypatch.setattr(web.settings, "decodo_web_data_api_key", SecretStr(""))
    assert await web.recover_listing(URL) is None
    assert not api.calls


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"results": []},
        {"results": [{"status_code": 403, "content": listing_page()}]},
        {"results": [{"status_code": 200, "content": PAGE}]},
        {
            "results": [
                {
                    "status_code": 200,
                    "content": listing_page(URL.replace("267446L6C3DU", "999999999")),
                }
            ]
        },
        {
            "results": [
                {
                    "status_code": 200,
                    "content": listing_page("https://evil.test/annonce/267446L6C3DU"),
                }
            ]
        },
        {
            "results": [
                {
                    "status_code": 200,
                    "content": listing_page()
                    + '<iframe src="https://geo.captcha-delivery.com/captcha/"></iframe>',
                }
            ]
        },
        {"results": [{"status_code": 200, "content": "private-api-key"}]},
    ],
)
async def test_invalid_results_never_enter_cache(state, api, data, caplog):
    api.data = data
    assert await web.recover_listing(URL) is None
    assert await web.cached_listing(URL) is None
    assert len(api.calls) == 1
    assert "private-api-key" not in caplog.text


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_api_errors_are_not_retried_or_followed(state, api, status, caplog):
    api.http_status = status
    assert await web.recover_listing(URL) is None
    assert len(api.calls) == 1
    assert "private-api-key" not in caplog.text


async def test_unwritable_cache_does_not_block_recovery(
    state, api, tmp_path, monkeypatch
):
    monkeypatch.setattr(web.settings, "decodo_web_data_state_path", str(tmp_path))
    assert (await web.recover_listing(URL)).page_text
    assert len(api.calls) == 1
    assert await web.cached_listing(URL) is None


async def test_oversized_response_is_rejected(state, api, monkeypatch):
    monkeypatch.setattr(web, "MAX_RESPONSE_BYTES", 32)
    assert await web.recover_listing(URL) is None
    assert await web.cached_listing(URL) is None


async def test_transport_failure_does_not_leak_secrets(state, api, caplog):
    api.error = httpx.ReadTimeout("private-api-key signed-tracking-token")
    assert await web.recover_listing(TRACKING_URL) is None
    assert "private-api-key" not in caplog.text
    assert "signed-tracking-token" not in caplog.text
    assert "tracking=private" not in caplog.text


@pytest.mark.parametrize(
    "blocked,purpose,browser_success,expected",
    [
        (True, "email", False, True),
        (True, "probe", False, False),
        (True, "email", True, False),
        (False, "email", False, False),
    ],
)
async def test_paid_fallback_only_after_block_and_failed_browser(
    monkeypatch,
    blocked,
    purpose,
    browser_success,
    expected,
):
    recovered = scraper.ScrapedListing(resolved_url=URL, page_text="Recovered page")
    normal = session(
        response(),
        response(
            403 if blocked else 200,
            "Please enable JS" if blocked else PAGE,
            headers={"x-datadome": "protected"} if blocked else {},
        ),
    )
    monkeypatch.setattr(scraper, "_throttle", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_scrape_browser",
        AsyncMock(return_value=recovered if browser_success else None),
    )
    monkeypatch.setattr(web, "cached_listing", AsyncMock(return_value=None))
    paid = AsyncMock(return_value=recovered)
    monkeypatch.setattr(web, "recover_listing", paid)
    with patch.object(scraper, "AsyncSession", return_value=normal):
        result = await scraper.scrape_listing(URL, "seloger", purpose=purpose)
    assert paid.await_count == int(expected)
    if expected:
        paid.assert_awaited_once_with(URL, cache_url=URL)
        assert result == recovered
    if purpose == "probe":
        web.cached_listing.assert_not_awaited()


@pytest.mark.parametrize("status", [404, 410, 500])
async def test_ordinary_http_errors_never_spend(monkeypatch, status):
    normal = session(response(), response(status, ""))
    monkeypatch.setattr(scraper, "_throttle", AsyncMock())
    monkeypatch.setattr(web, "cached_listing", AsyncMock(return_value=None))
    paid = AsyncMock()
    monkeypatch.setattr(web, "recover_listing", paid)
    with patch.object(scraper, "AsyncSession", return_value=normal):
        await scraper.scrape_listing(URL, "seloger")
    paid.assert_not_awaited()


async def test_cached_result_avoids_all_network_requests(monkeypatch):
    recovered = scraper.ScrapedListing(resolved_url=URL, page_text="Recovered page")
    monkeypatch.setattr(web, "cached_listing", AsyncMock(return_value=recovered))
    with patch.object(scraper, "_scrape_listing", AsyncMock()) as network:
        assert (
            await scraper.scrape_listing(URL, "seloger", purpose="email") == recovered
        )
    network.assert_not_awaited()
