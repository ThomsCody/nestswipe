"""Monitoring contracts: behavior, metric names, tags and deployed queries."""

import asyncio
import json
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from datadog import DogStatsd

from app.services import browser_scraper as scraper
from app.services import listing_metrics as metrics
from app.services import listing_probe as probe
from tests.test_browser_scraper import PAGE, URL, response, session


@pytest.fixture
def client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(metrics, "_client", lambda: client)
    return client


@pytest.mark.parametrize(
    "status,outcome",
    [(200, "success"), (404, "unavailable"), (410, "unavailable"), (500, "failure")],
)
async def test_final_outcome_contract(client, status, outcome):
    with patch.object(scraper, "AsyncSession", return_value=session(response(status))):
        await scraper.scrape_listing("https://www.junot.fr/annonce/test", "junot")
    tags = ["listing_source:junot", "purpose:import"]
    assert client.increment.call_args_list == [
        call("nestswipe.listing_access.attempts", 1, tags=tags),
        *[
            call("nestswipe.listing_access." + name, int(outcome == name), tags=tags)
            for name in ("success", "failure", "unavailable")
        ],
    ]


async def test_browser_recovery_counts_one_success_and_no_failure(client, monkeypatch):
    monkeypatch.setattr(scraper, "_throttle", AsyncMock())
    challenge = response(403, "Please enable JS", headers={"x-datadome": "protected"})
    monkeypatch.setattr(
        scraper, "AsyncSession", lambda **kwargs: session(response(), challenge)
    )
    monkeypatch.setattr(
        scraper,
        "_scrape_browser",
        AsyncMock(return_value=scraper.ScrapedListing(page_text=PAGE)),
    )
    await scraper.scrape_listing(URL, "seloger")
    assert client.increment.call_args_list[2] == call(
        "nestswipe.listing_access.failure",
        0,
        tags=["listing_source:seloger", "purpose:import"],
    )
    assert len(client.increment.call_args_list) == 4


async def test_failed_browser_and_unexpected_exceptions_count_once(client, monkeypatch):
    monkeypatch.setattr(scraper, "_throttle", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "AsyncSession",
        lambda **kwargs: session(response(), RuntimeError("private")),
    )
    monkeypatch.setattr(scraper, "_scrape_browser", AsyncMock(return_value=None))
    await scraper.scrape_listing(URL, "seloger")
    failure = call(
        "nestswipe.listing_access.failure",
        1,
        tags=["listing_source:seloger", "purpose:import"],
    )
    assert client.increment.call_args_list.count(failure) == 1
    client.reset_mock()
    monkeypatch.setattr(
        scraper, "_scrape_listing", AsyncMock(side_effect=ValueError("private"))
    )
    with pytest.raises(ValueError):
        await scraper.scrape_listing(URL, "seloger")
    assert client.increment.call_args_list == [
        call(
            "nestswipe.listing_access.attempts",
            1,
            tags=["listing_source:seloger", "purpose:import"],
        ),
        call(
            "nestswipe.listing_access.success",
            0,
            tags=["listing_source:seloger", "purpose:import"],
        ),
        failure,
        call(
            "nestswipe.listing_access.unavailable",
            0,
            tags=["listing_source:seloger", "purpose:import"],
        ),
    ]


async def test_metrics_cannot_break_import(client, monkeypatch, caplog):
    client.increment.side_effect = OSError("private token")
    monkeypatch.setattr(
        scraper,
        "_scrape_listing",
        AsyncMock(return_value=scraper.ScrapedListing(page_text=PAGE)),
    )
    assert (await scraper.scrape_listing(URL, "seloger")).page_text == PAGE
    assert "private token" not in caplog.text


def test_bounded_tags(client):
    metrics.scrape_attempt("https://private.example/?token=secret", "unknown")
    client.increment.assert_called_once_with(
        "nestswipe.listing_access.attempts",
        1,
        tags=["listing_source:other", "purpose:import"],
    )


def test_actual_dogstatsd_wire_contract(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(1)
        client = DogStatsd(
            host="127.0.0.1",
            port=receiver.getsockname()[1],
            constant_tags=["service:nestswipe-backend", "env:test"],
            disable_buffering=True,
            disable_telemetry=True,
        )
        monkeypatch.setattr(metrics, "_client", lambda: client)
        metrics.scrape_outcome("seloger", "probe", "failure")
        metrics.probe_result("seloger", False)
        metrics.probes_completed()
        packets = [receiver.recv(4096).decode() for _ in range(5)]
        client.close_socket()
    assert any(p.startswith("nestswipe.listing_access.failure:1|c|") for p in packets)
    assert any(p.startswith("nestswipe.listing_probe.healthy:0|g|") for p in packets)
    assert any(p.startswith("nestswipe.listing_probe.completed:1|g|") for p in packets)
    assert all("service:nestswipe-backend" in p and "env:test" in p for p in packets)


async def test_probe_tries_next_removed_listing(client, monkeypatch):
    scrape = AsyncMock(
        side_effect=[
            scraper.ScrapedListing(unavailable=True),
            scraper.ScrapedListing(page_text=PAGE),
        ]
    )
    monkeypatch.setattr(probe, "scrape_listing", scrape)
    assert await probe._probe_source("seloger", [URL, URL + "2"])
    assert scrape.await_args_list == [
        call(URL, "seloger", purpose="probe"),
        call(URL + "2", "seloger", purpose="probe"),
    ]
    client.gauge.assert_called_once_with(
        "nestswipe.listing_probe.healthy", 1, tags=["listing_source:seloger"]
    )


@pytest.mark.parametrize("result", [scraper.ScrapedListing(), RuntimeError("private")])
async def test_probe_reports_failure_without_extra_requests(
    client, monkeypatch, result
):
    scrape = AsyncMock(side_effect=[result])
    monkeypatch.setattr(probe, "scrape_listing", scrape)
    assert not await probe._probe_source("pap", [URL, URL + "2"])
    assert scrape.await_count == 1
    client.gauge.assert_called_once_with(
        "nestswipe.listing_probe.healthy", 0, tags=["listing_source:pap"]
    )


async def test_probe_timeout_and_no_targets_are_not_healthy(client, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(probe, "scrape_listing", slow)
    monkeypatch.setattr(probe, "PROBE_TIMEOUT_SECONDS", 0.01)
    assert not await probe._probe_source("seloger", [URL])
    assert not await probe._probe_source("pap", [])
    assert [c.args[1] for c in client.gauge.call_args_list] == [0, 0]


async def test_completion_waits_for_all_sources_even_failed_checks(client, monkeypatch):
    monkeypatch.setattr(
        probe,
        "_candidate_urls",
        AsyncMock(return_value={s: [] for s in metrics.SOURCES}),
    )
    results = await probe.run_listing_probes()
    assert set(results) == metrics.SOURCES
    assert not any(results.values())
    assert len(client.gauge.call_args_list) == 7
    assert client.gauge.call_args_list[-1] == call(
        "nestswipe.listing_probe.completed", 1, tags=[]
    )


async def test_no_false_heartbeat_on_database_failure(client, monkeypatch):
    monkeypatch.setattr(
        probe, "_candidate_urls", AsyncMock(side_effect=RuntimeError("private"))
    )
    assert await probe.run_listing_probes() is None
    client.gauge.assert_not_called()


async def test_candidate_selection_is_bounded_distinct_and_validates_source(
    monkeypatch,
):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value = [
        "https://www.seloger.com:invalid/annonce/test",
        "https://private@www.seloger.com/annonce/test",
        "https://www.seloger.com.evil.example/annonce/test",
        "http://www.seloger.com/annonce/test",
        "https://www.pap.fr/annonce/test",
        URL,
        URL,
        URL + "2",
        URL + "3",
        URL + "4",
    ]
    db.execute = AsyncMock(return_value=rows)
    monkeypatch.setattr(probe, "async_session", lambda: db)
    monkeypatch.setattr(metrics, "SOURCES", {"seloger"})
    assert await probe._candidate_urls() == {"seloger": [URL, URL + "2", URL + "3"]}
    statement = str(db.execute.await_args.args[0])
    assert "ORDER BY listings.last_seen_at DESC, listings.id DESC" in statement


@pytest.mark.parametrize("enabled", [True, False])
async def test_scheduler_registers_bounded_probes_only_when_enabled(
    monkeypatch, enabled
):
    from app import scheduler

    fake_scheduler = MagicMock()
    fake_scheduler.get_job.return_value = None
    monkeypatch.setattr(scheduler, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler, "_get_last_poll_time", AsyncMock(return_value=None))
    monkeypatch.setattr(scheduler.settings, "listing_probes_enabled", enabled)
    await scheduler.start_scheduler()
    jobs = [
        c
        for c in fake_scheduler.add_job.call_args_list
        if c.kwargs["id"] == "listing_probes"
    ]
    assert len(jobs) == int(enabled)
    if enabled:
        assert jobs[0].args == (probe.run_listing_probes, "interval")
        assert jobs[0].kwargs["minutes"] == 10
        assert jobs[0].kwargs["max_instances"] == 1
        assert jobs[0].kwargs["coalesce"] is True


@pytest.mark.parametrize("source", ["barnes", "junot", "consultantsimmobilier"])
async def test_shared_agency_redirects_are_eligible_probe_targets(monkeypatch, source):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value = ["https://ap.immo/click/test"]
    db.execute = AsyncMock(return_value=rows)
    monkeypatch.setattr(probe, "async_session", lambda: db)
    monkeypatch.setattr(metrics, "SOURCES", {source})
    assert await probe._candidate_urls() == {source: ["https://ap.immo/click/test"]}


async def test_disabled_provider_is_not_selected_for_paid_probes(monkeypatch):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value = [URL]
    db.execute = AsyncMock(return_value=rows)
    monkeypatch.setattr(probe, "async_session", lambda: db)
    monkeypatch.setattr(metrics, "SOURCES", {"seloger", "leboncoin"})
    assert await probe._candidate_urls() == {"seloger": [URL]}
    db.execute.assert_awaited_once()
    assert "leboncoin" in metrics.SOURCES


def test_monitor_queries_and_missing_data_contract():
    root = Path(__file__).resolve().parents[2] / "deploy" / "datadog"
    failure = json.loads((root / "listing-access-monitor.json").read_text())
    healthy = json.loads((root / "listing-probe-monitor.json").read_text())
    heartbeat = json.loads((root / "listing-probe-heartbeat-monitor.json").read_text())
    assert (
        failure["query"]
        == "sum(last_15m):sum:nestswipe.listing_access.failure{service:nestswipe-backend,env:prod,purpose:import,!listing_source:leboncoin}.as_count() > 0"
    )
    assert (
        healthy["query"]
        == "max(last_20m):min:nestswipe.listing_probe.healthy{service:nestswipe-backend,env:prod,!listing_source:leboncoin} by {listing_source}.fill(null) < 1"
    )
    assert (
        heartbeat["query"]
        == "max(last_30m):max:nestswipe.listing_probe.completed{service:nestswipe-backend,env:prod}.fill(null) < 1"
    )
    for payload in [failure, healthy, heartbeat]:
        assert payload["type"] == "query alert"
        assert payload["options"]["require_full_window"] is False
    assert failure["options"]["on_missing_data"] == "resolve"
    assert healthy["options"]["on_missing_data"] == "show_and_notify_no_data"
    assert heartbeat["options"]["on_missing_data"] == "show_and_notify_no_data"
    assert 2 * probe.PROBE_INTERVAL_MINUTES <= 30
