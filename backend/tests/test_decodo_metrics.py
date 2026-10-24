from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr

from app.services import decodo_metrics as metrics


def payload(download=1200, upload=30, requests=4):
    return {
        "metadata": {
            "totals": {
                "total_rx": download,
                "total_tx": upload,
                "total_rx_tx": download + upload,
                "requests": requests,
            }
        }
    }


@pytest.mark.parametrize(
    "bad", [None, {}, {"metadata": {}}, payload(-1), payload(1.2), payload(True)]
)
def test_rejects_missing_or_invalid_totals(bad):
    with pytest.raises((KeyError, TypeError, ValueError)):
        metrics.parse_totals(bad)


def test_rejects_inconsistent_bytes():
    data = payload()
    data["metadata"]["totals"]["total_rx_tx"] = 1231
    with pytest.raises(ValueError):
        metrics.parse_totals(data)


def test_accepts_real_zero_usage_and_uses_metadata_not_paginated_rows():
    data = payload(0, 0, 0)
    data["data"] = []
    assert metrics.parse_totals(data) == {
        "download": 0,
        "upload": 0,
        "total": 0,
        "requests": 0,
    }
    data = payload(1200, 30, 4)
    data["data"] = [{"rx_tx_bytes": 10}]
    assert metrics.parse_totals(data)["total"] == 1230


async def test_reporting_requests_are_direct_and_have_explicit_windows(monkeypatch):
    import json

    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=payload())

    real_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs == {"timeout": 30, "trust_env": False}
        return real_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(metrics.httpx, "AsyncClient", client)
    result = await metrics.fetch_usage(
        "test-secret", datetime(2026, 10, 21, 10, tzinfo=timezone.utc)
    )
    assert result["24h"]["total"] == 1230
    assert result["30d"]["total"] == 1230
    assert len(requests) == 2
    for request, start in zip(requests, ["2026-10-20 10:00:00", "2026-09-21 10:00:00"]):
        assert str(request.url) == metrics.TRAFFIC_URL
        assert request.headers["Authorization"] == "test-secret"
        body = json.loads(request.content)
        assert body["startDate"] == start
        assert body["endDate"] == "2026-10-21 10:00:00"
        assert body["proxyType"] == "residential_proxies"


@pytest.fixture
def collector(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(metrics, "_client", lambda: client)
    monkeypatch.setattr(metrics.settings, "decodo_api_key", SecretStr("test-secret"))
    fetch = AsyncMock(
        return_value={w: metrics.parse_totals(payload()) for w in metrics.WINDOWS}
    )
    monkeypatch.setattr(metrics, "fetch_usage", fetch)
    return client, fetch


async def test_emits_gauges_with_windows_and_no_secret_tags(collector):
    client, fetch = collector
    await metrics.collect_decodo_usage()
    assert fetch.await_count == 1
    assert client.gauge.call_count == 10
    client.increment.assert_not_called()
    calls = client.gauge.call_args_list
    traffic = [c for c in calls if c.args[0].endswith("traffic_bytes")]
    assert len(traffic) == 6
    assert {c.args[1] for c in traffic} == {1200, 30, 1230}
    assert all("scope:account" in c.kwargs["tags"] for c in calls)
    assert "test-secret" not in str(calls)


async def test_failure_does_not_publish_zero_usage_or_fake_freshness(collector, caplog):
    client, fetch = collector
    fetch.side_effect = ValueError("test-secret")
    await metrics.collect_decodo_usage()
    client.gauge.assert_called_once_with(
        "nestswipe.decodo.collection_success", 0, tags=metrics.TAGS
    )
    assert "test-secret" not in caplog.text


async def test_disabled_without_key(collector, monkeypatch):
    client, fetch = collector
    monkeypatch.setattr(metrics.settings, "decodo_api_key", SecretStr(""))
    await metrics.collect_decodo_usage()
    fetch.assert_not_awaited()
    client.gauge.assert_not_called()


async def test_scheduler_registers_reporting_only_when_configured(monkeypatch):
    from app import scheduler

    fake = MagicMock()
    fake.get_job.return_value = None
    monkeypatch.setattr(scheduler, "scheduler", fake)
    monkeypatch.setattr(scheduler, "_get_last_poll_time", AsyncMock(return_value=None))
    monkeypatch.setattr(scheduler.settings, "decodo_api_key", SecretStr("test-secret"))
    await scheduler.start_scheduler()
    jobs = {call.kwargs["id"]: call for call in fake.add_job.call_args_list}
    assert set(jobs) == {"poll_emails", "photo_cleanup", "decodo_usage"}
    assert jobs["decodo_usage"].kwargs["minutes"] == 15
    assert jobs["decodo_usage"].kwargs["max_instances"] == 1
