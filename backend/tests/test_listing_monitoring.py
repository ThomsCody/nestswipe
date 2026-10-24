"""Monitoring contracts: behavior, metric names, tags and deployed queries."""

import asyncio
import json
import runpy
import socket
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from datadog import DogStatsd

from app.services import browser_scraper as scraper
from app.services import listing_metrics as metrics
from app.services import listing_probe as probe
from tests.test_browser_scraper import PAGE, URL, response, session


@pytest.fixture(autouse=True)
def isolated_probe_targets(monkeypatch):
    monkeypatch.setattr(probe, "_unavailable_targets", {})


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


async def test_real_email_failure_has_distinct_monitoring_tag(client, monkeypatch):
    monkeypatch.setattr(
        scraper, "_scrape_listing", AsyncMock(return_value=scraper.ScrapedListing())
    )
    await scraper.scrape_listing(URL, "seloger", purpose="email")
    assert (
        call(
            "nestswipe.listing_access.failure",
            1,
            tags=["listing_source:seloger", "purpose:email"],
        )
        in client.increment.call_args_list
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


def test_host_agent_socket_transport(monkeypatch):
    # macOS limits Unix socket paths to 104 bytes; pytest's temp root is longer.
    directory = tempfile.TemporaryDirectory(prefix="dsd-", dir="/tmp")
    path = str(Path(directory.name) / "dsd.socket")
    monkeypatch.delenv("DD_AGENT_HOST", raising=False)
    monkeypatch.setenv("DD_DOGSTATSD_URL", "unix://" + path)
    monkeypatch.setenv("DD_SERVICE", "nestswipe-backend")
    monkeypatch.setenv("DD_ENV", "test")
    metrics._client.cache_clear()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
            receiver.bind(path)
            receiver.settimeout(1)
            metrics.probe_result("seloger", True)
            packet = receiver.recv(4096).decode()
            assert packet.startswith("nestswipe.listing_probe.healthy:1|g|")
            assert "service:nestswipe-backend" in packet
            assert "env:test" in packet
            assert "listing_source:seloger" in packet
    finally:
        client = metrics._client()
        if client is not None:
            client.close_socket()
        metrics._client.cache_clear()
        directory.cleanup()


def test_metrics_disabled_without_agent_endpoint(monkeypatch):
    monkeypatch.delenv("DD_AGENT_HOST", raising=False)
    monkeypatch.delenv("DD_DOGSTATSD_URL", raising=False)
    metrics._client.cache_clear()
    try:
        assert metrics._client() is None
    finally:
        metrics._client.cache_clear()


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
    assert not probe._unavailable_targets
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
    assert len(client.gauge.call_args_list) == len(metrics.SOURCES) + 1
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
async def test_scheduler_never_registers_probes_even_with_legacy_flag(
    monkeypatch, enabled
):
    from app import scheduler

    fake_scheduler = MagicMock()
    fake_scheduler.get_job.return_value = None
    monkeypatch.setattr(scheduler, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler, "_get_last_poll_time", AsyncMock(return_value=None))
    monkeypatch.setattr(scheduler.settings, "listing_probes_enabled", enabled)
    from pydantic import SecretStr

    monkeypatch.setattr(scheduler.settings, "decodo_api_key", SecretStr(""))
    await scheduler.start_scheduler()
    jobs = [
        c
        for c in fake_scheduler.add_job.call_args_list
        if c.kwargs["id"] == "listing_probes"
    ]
    assert jobs == []
    assert {c.kwargs["id"] for c in fake_scheduler.add_job.call_args_list} == {
        "poll_emails",
        "photo_cleanup",
    }


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


async def test_sibling_site_cannot_starve_seloger_candidates(
    db_session, test_user, monkeypatch
):
    from app.models.listing import Listing
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    db_session.add(
        Listing(
            household_id=test_user.household_id,
            user_id=test_user.id,
            source="seloger",
            title="SeLoger",
            external_url=URL,
            last_seen_at=now - timedelta(days=1),
        )
    )
    for index in range(35):
        db_session.add(
            Listing(
                household_id=test_user.household_id,
                user_id=test_user.id,
                source="seloger",
                title="Belles Demeures",
                external_url=f"https://www.bellesdemeures.com/annonces/{index}/",
                last_seen_at=now,
            )
        )
    await db_session.commit()
    monkeypatch.setattr(probe, "async_session", lambda: db_session)
    monkeypatch.setattr(metrics, "SOURCES", {"seloger", "bellesdemeures"})
    candidates = await probe._candidate_urls()
    assert candidates["seloger"] == [URL]
    assert len(candidates["bellesdemeures"]) == 3
    assert all("bellesdemeures.com" in url for url in candidates["bellesdemeures"])


async def test_removed_targets_advance_across_runs_and_expire(
    db_session, test_user, client, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from app.models.listing import Listing

    now = datetime.now(timezone.utc)
    urls = [URL + str(index) for index in range(34)]
    for index, url in enumerate(urls):
        db_session.add(
            Listing(
                household_id=test_user.household_id,
                user_id=test_user.id,
                source="seloger",
                title="Probe candidate",
                external_url=url,
                last_seen_at=now - timedelta(minutes=index),
            )
        )
    await db_session.commit()
    monkeypatch.setattr(probe, "async_session", lambda: db_session)
    monkeypatch.setattr(metrics, "SOURCES", {"seloger"})
    clock = [100.0]
    monkeypatch.setattr(probe.time, "monotonic", lambda: clock[0])

    async def scrape(url, source, *, purpose):
        return scraper.ScrapedListing(
            page_text=PAGE if url == urls[-1] else "",
            unavailable=url != urls[-1],
        )

    fetch = AsyncMock(side_effect=scrape)
    monkeypatch.setattr(probe, "scrape_listing", fetch)
    # More than the SQL window of 30 removed targets must not starve the live one.
    for offset in range(0, 33, 3):
        candidates = await probe._candidate_urls()
        assert candidates["seloger"] == urls[offset : offset + 3]
        assert not await probe._probe_source("seloger", candidates["seloger"])
    candidates = await probe._candidate_urls()
    assert candidates == {"seloger": [urls[-1]]}
    assert await probe._probe_source("seloger", candidates["seloger"])
    assert fetch.await_count == 34
    assert await probe._candidate_urls() == candidates
    clock[0] += probe.UNAVAILABLE_TTL_SECONDS
    assert await probe._candidate_urls() == {"seloger": urls[:3]}


async def test_removed_target_cache_is_bounded_and_source_specific(client, monkeypatch):
    monkeypatch.setattr(probe, "MAX_UNAVAILABLE_TARGETS", 2)
    monkeypatch.setattr(
        probe,
        "scrape_listing",
        AsyncMock(return_value=scraper.ScrapedListing(unavailable=True)),
    )
    assert not await probe._probe_source("seloger", [URL, URL + "2", URL + "3"])
    assert list(probe._unavailable_targets["seloger"]) == [URL + "2", URL + "3"]
    assert "bellesdemeures" not in probe._unavailable_targets


async def test_sibling_probe_failure_cannot_be_hidden_by_seloger_success(
    client, monkeypatch
):
    belles = "https://www.bellesdemeures.com/annonces/123/"
    monkeypatch.setattr(
        probe,
        "_candidate_urls",
        AsyncMock(
            return_value={
                "seloger": [URL],
                "bellesdemeures": [belles],
            }
        ),
    )

    async def scrape(url, source, *, purpose):
        assert source == "seloger" and purpose == "probe"
        return scraper.ScrapedListing(page_text=PAGE if url == URL else "")

    monkeypatch.setattr(probe, "scrape_listing", scrape)
    assert await probe.run_listing_probes() == {
        "seloger": True,
        "bellesdemeures": False,
    }
    assert (
        call("nestswipe.listing_probe.healthy", 1, tags=["listing_source:seloger"])
        in client.gauge.call_args_list
    )
    assert (
        call(
            "nestswipe.listing_probe.healthy", 0, tags=["listing_source:bellesdemeures"]
        )
        in client.gauge.call_args_list
    )


async def test_bellesdemeures_access_metrics_use_site_tag_without_changing_scraper(
    client, monkeypatch
):
    url = "https://www.bellesdemeures.com/annonces/123/"
    fetch = AsyncMock(return_value=scraper.ScrapedListing(page_text=PAGE))
    monkeypatch.setattr(scraper, "_scrape_listing", fetch)
    await scraper.scrape_listing(url, "seloger", purpose="probe")
    fetch.assert_awaited_once_with(url, "seloger")
    assert all(
        c.kwargs["tags"] == ["listing_source:bellesdemeures", "purpose:probe"]
        for c in client.increment.call_args_list
    )


def test_site_tag_does_not_trust_hostname_suffixes():
    assert (
        metrics.access_source("seloger", "https://www.bellesdemeures.com.evil.test/")
        == "seloger"
    )
    assert (
        metrics.access_source(
            "seloger", "https://click.by.bellesdemeures.com/?qs=secret"
        )
        == "bellesdemeures"
    )


def test_monitor_queries_and_missing_data_contract():
    root = Path(__file__).resolve().parents[2] / "deploy" / "datadog"
    failure = json.loads((root / "listing-access-monitor.json").read_text())
    healthy = json.loads((root / "listing-probe-monitor.json").read_text())
    heartbeat = json.loads((root / "listing-probe-heartbeat-monitor.json").read_text())
    assert (
        failure["query"]
        == "sum(last_15m):sum:nestswipe.listing_access.failure{service:nestswipe-backend,env:prod,purpose:email} by {listing_source}.as_count() > 0"
    )
    assert (
        healthy["query"]
        == "max(last_4h):min:nestswipe.listing_probe.healthy{service:nestswipe-backend,env:prod,!listing_source:leboncoin} by {listing_source}.fill(null) < 1"
    )
    assert (
        heartbeat["query"]
        == "max(last_4h):max:nestswipe.listing_probe.completed{service:nestswipe-backend,env:prod}.fill(null) < 1"
    )
    for payload in [failure, healthy, heartbeat]:
        assert payload["type"] == "query alert"
        assert payload["options"]["require_full_window"] is False
    assert failure["options"]["on_missing_data"] == "resolve"
    assert healthy["options"]["on_missing_data"] == "resolve"
    assert heartbeat["options"]["on_missing_data"] == "resolve"
    assert healthy["retired"] and heartbeat["retired"]
    assert failure["options"]["new_group_delay"] == 0
    assert failure["notification_enabled"] is True
    assert failure["options"]["renotify_interval"] == 0
    prepare = runpy.run_path(str(root / "publish_monitor.py"))["prepare_payload"]
    for definition in (failure, healthy, heartbeat):
        payload = prepare(definition, "@owner@example.com")
        assert "notification_enabled" not in payload
        assert "retired" not in payload
        assert ("@owner@example.com" in payload["message"]) == definition.get(
            "notification_enabled", True
        )
        assert "@owner@example.com" not in definition["message"]


def test_publisher_retires_existing_monitor_without_recreating_missing_one():
    root = Path(__file__).resolve().parents[2] / "deploy" / "datadog"
    publisher = runpy.run_path(str(root / "publish_monitor.py"))
    definition = json.loads((root / "listing-probe-monitor.json").read_text())
    payload = publisher["prepare_payload"](definition, "@owner@example.com")
    saved = {
        **payload,
        "id": 123,
        "options": {**payload["options"], "silenced": {"*": None}},
    }
    request = MagicMock(side_effect=[[saved], {"id": 123}, {}, saved])
    publisher["upsert_monitor"](request, payload, retired=True)
    assert call("POST", "/api/v1/monitor/123/mute", {}) in request.call_args_list
    request = MagicMock(return_value=[])
    publisher["upsert_monitor"](request, payload, retired=True)
    assert request.call_count == 1
