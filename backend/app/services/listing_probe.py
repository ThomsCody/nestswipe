"""Exercise actual listing access, with bounded work and no import side effects."""

import asyncio
import logging
from urllib.parse import urlsplit

from sqlalchemy import select

from app.database import async_session
from app.models.listing import Listing
from app.services import listing_metrics
from app.services.browser_scraper import detect_source_from_url, scrape_listing

logger = logging.getLogger(__name__)
PROBE_INTERVAL_MINUTES = 10
PROBE_TIMEOUT_SECONDS = 240
MAX_CANDIDATES = 3
# Leboncoin monitoring is intentionally disabled to avoid paid proxy checks.
# Keep its metric source tag so import metrics can still be excluded by source.
DISABLED_PROBE_SOURCES = frozenset({"leboncoin"})


def _matches_source(url: str, hostname: str | None, source: str) -> bool:
    # Several agencies share this email redirect service. The listing's stored
    # source, not ap.immo's default URL classification, identifies the agency.
    if hostname == "ap.immo" and source in {"barnes", "junot", "consultantsimmobilier"}:
        return True
    return detect_source_from_url(url) == source


async def _candidate_urls() -> dict[str, list[str]]:
    candidates = {}
    async with async_session() as db:
        for source in sorted(listing_metrics.SOURCES - DISABLED_PROBE_SOURCES):
            rows = await db.execute(
                select(Listing.external_url)
                .where(Listing.source == source, Listing.external_url.isnot(None))
                .order_by(Listing.last_seen_at.desc(), Listing.id.desc())
                .limit(30)
            )
            urls = []
            for url in rows.scalars():
                try:
                    parsed = urlsplit(url)
                    port = parsed.port
                except ValueError:
                    continue
                if (
                    parsed.scheme == "https"
                    and not parsed.username
                    and not parsed.password
                    and port in (None, 443)
                    and _matches_source(url, parsed.hostname, source)
                    and url not in urls
                ):
                    urls.append(url)
                if len(urls) == MAX_CANDIDATES:
                    break
            # Missing targets are a failed check, never silently considered healthy.
            candidates[source] = urls
    return candidates


async def _probe_source(source: str, urls: list[str]) -> bool:
    reason = "no_available_listing"
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            for url in urls:
                result = await scrape_listing(url, source, purpose="probe")
                if result.page_text:
                    listing_metrics.probe_result(source, True)
                    logger.info("Listing probe succeeded: source=%s", source)
                    return True
                if not result.unavailable:
                    reason = "access_failed"
                    break
                # A removed advert is not a provider outage. Try another recent one.
    except Exception as exc:
        reason = type(exc).__name__
    listing_metrics.probe_result(source, False)
    logger.warning("Listing probe failed: source=%s reason=%s", source, reason)
    return False


async def run_listing_probes():
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS + 30):
            candidates = await _candidate_urls()
            results = await asyncio.gather(
                *(_probe_source(source, urls) for source, urls in candidates.items())
            )
        listing_metrics.probes_completed()
        return dict(zip(candidates, results))
    except Exception as exc:
        # Do not emit completion on DB/job failures: the missing-check alert fires.
        logger.error("Listing probe job failed: %s", type(exc).__name__)
        return None
