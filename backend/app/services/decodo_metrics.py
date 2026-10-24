"""Account-wide, provider-reported residential bandwidth (not scraper estimates)."""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.services.listing_metrics import _client

logger = logging.getLogger(__name__)
TRAFFIC_URL = "https://api.decodo.com/api/v2/statistics/traffic"
WINDOWS = {"24h": timedelta(hours=24), "30d": timedelta(days=30)}
TAGS = ["provider:decodo", "proxy_type:residential", "scope:account"]


def parse_totals(payload: dict) -> dict[str, int]:
    """Fail closed on schema changes; missing or malformed data is not zero usage.

    Decodo metadata totals cover the whole query, independent of row pagination.
    Units confirmed against rx_bytes/tx_bytes rows and the Decodo dashboard.
    """
    totals = payload["metadata"]["totals"]
    fields = {
        "download": "total_rx",
        "upload": "total_tx",
        "total": "total_rx_tx",
        "requests": "requests",
    }
    result = {name: totals[field] for name, field in fields.items()}
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError("Invalid Decodo usage totals")
    if result["download"] + result["upload"] != result["total"]:
        raise ValueError("Inconsistent Decodo byte totals")
    return result


async def fetch_usage(api_key: str, now: datetime) -> dict[str, dict[str, int]]:
    usage = {}
    # Explicit direct connection: proxy env vars and scraper sessions are ignored.
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        for window, duration in WINDOWS.items():
            response = await client.post(
                TRAFFIC_URL,
                headers={"Authorization": api_key},
                json={
                    "proxyType": "residential_proxies",
                    "startDate": (now - duration).strftime("%Y-%m-%d %H:%M:%S"),
                    "endDate": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "groupBy": "day",
                    "page": 1,
                    "limit": 100,
                    "sortBy": "grouping_key",
                    "sortOrder": "asc",
                },
            )
            response.raise_for_status()
            usage[window] = parse_totals(response.json())
    return usage


async def collect_decodo_usage():
    api_key = settings.decodo_api_key.get_secret_value()
    if not api_key:
        return
    try:
        client = _client()
        if client is None:
            return
        now = datetime.now(timezone.utc)
        try:
            usage = await fetch_usage(api_key, now)
        except Exception as exc:
            # Never include response bodies, request headers or credential values.
            logger.warning("Decodo usage collection failed: %s", type(exc).__name__)
            client.gauge("nestswipe.decodo.collection_success", 0, tags=TAGS)
            return
        # Publish only after both windows succeed. Gauges avoid counting the same
        # cumulative usage again every poll. Never emit fake zero bytes on failure.
        for window, totals in usage.items():
            tags = TAGS + [f"window:{window}"]
            for direction in ("download", "upload", "total"):
                client.gauge(
                    "nestswipe.decodo.traffic_bytes",
                    totals[direction],
                    tags=tags + [f"direction:{direction}"],
                )
            client.gauge("nestswipe.decodo.requests", totals["requests"], tags=tags)
        client.gauge("nestswipe.decodo.collection_success", 1, tags=TAGS)
        client.gauge(
            "nestswipe.decodo.last_success_timestamp", now.timestamp(), tags=TAGS
        )
        logger.info("Decodo account usage metrics collected")
    except Exception as exc:
        logger.warning("Decodo metric submission failed: %s", type(exc).__name__)
