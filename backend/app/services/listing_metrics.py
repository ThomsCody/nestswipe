"""Stable monitoring contract, independent of log wording and log ingestion.

Metric names and bounded tags are consumed by deploy/datadog/*-monitor.json.
Change them together with the contract tests and deployed monitors.
"""

import logging
import os
from functools import lru_cache
from urllib.parse import urlsplit

from datadog import DogStatsd

logger = logging.getLogger(__name__)
SOURCES = frozenset(
    {
        "seloger",
        "bellesdemeures",
        "pap",
        "consultantsimmobilier",
        "barnes",
        "junot",
        "leboncoin",
    }
)


def access_source(source: str, url: str) -> str:
    """Separate website health without changing stored listing/provider identities."""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return source
    if source == "seloger" and host in {
        "bellesdemeures.com",
        "www.bellesdemeures.com",
        "click.by.bellesdemeures.com",
    }:
        return "bellesdemeures"
    return source


@lru_cache(maxsize=1)
def _client():
    # Development/test runs do not require an Agent or emit production telemetry.
    host = os.getenv("DD_AGENT_HOST")
    url = os.getenv("DD_DOGSTATSD_URL", "")
    socket_path = urlsplit(url).path if url.startswith("unix://") else None
    if not host and not socket_path:
        return None
    return DogStatsd(
        host=host,
        port=int(os.getenv("DD_DOGSTATSD_PORT", "8125")),
        socket_path=socket_path,
        constant_tags=[
            "service:" + os.getenv("DD_SERVICE", "nestswipe-backend"),
            "env:" + os.getenv("DD_ENV", "dev"),
        ],
        disable_buffering=True,
    )


def _emit(name: str, value: int, *, source=None, purpose=None, gauge=False):
    tags = []
    if source is not None:
        tags.append("listing_source:" + (source if source in SOURCES else "other"))
    if purpose is not None:
        tags.append(
            "purpose:" + (purpose if purpose in {"email", "probe"} else "import")
        )
    try:
        client = _client()
        if client is not None:
            send = client.gauge if gauge else client.increment
            send(name, value, tags=tags)
    except Exception as exc:
        # Monitoring must never prevent an import; no URL, credentials or user tags.
        logger.warning("Listing metric submission failed: %s", type(exc).__name__)


def scrape_attempt(source: str, purpose: str):
    _emit("nestswipe.listing_access.attempts", 1, source=source, purpose=purpose)


def scrape_outcome(source: str, purpose: str, outcome: str):
    # Explicit zeros keep sparse failure series evaluable during healthy traffic.
    for status in ("success", "failure", "unavailable"):
        _emit(
            "nestswipe.listing_access." + status,
            int(outcome == status),
            source=source,
            purpose=purpose,
        )


def probe_result(source: str, healthy: bool):
    _emit("nestswipe.listing_probe.healthy", int(healthy), source=source, gauge=True)


def probes_completed():
    # Only emitted AFTER all configured providers have finished, never on startup.
    _emit("nestswipe.listing_probe.completed", 1, gauge=True)
