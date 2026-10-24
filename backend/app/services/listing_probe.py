"""Exercise actual listing access, with bounded work and no import side effects."""

import asyncio
import logging
import time
from urllib.parse import urlsplit

from sqlalchemy import or_, select

from app.database import async_session
from app.models.listing import Listing
from app.services import listing_metrics
from app.services.browser_scraper import detect_source_from_url, scrape_listing

logger = logging.getLogger(__name__)
PROBE_INTERVAL_MINUTES = 10
PROBE_TIMEOUT_SECONDS = 240
MAX_CANDIDATES = 3
UNAVAILABLE_TTL_SECONDS = 24 * 60 * 60
MAX_UNAVAILABLE_TARGETS = 4096
# Only confirmed removed adverts are skipped. Access failures must keep alerting.
# Process-local state deliberately stores no authenticated URLs on disk.
_unavailable_targets: dict[str, dict[str, float]] = {}
# Leboncoin monitoring is intentionally disabled to avoid paid proxy checks.
# Keep its metric source tag so import metrics can still be excluded by source.
DISABLED_PROBE_SOURCES = frozenset({"leboncoin"})
PROBE_HOSTS = {
    "seloger": ("seloger.com", "www.seloger.com", "click.by.seloger.com"),
    "bellesdemeures": (
        "bellesdemeures.com",
        "www.bellesdemeures.com",
        "click.by.bellesdemeures.com",
    ),
}


def _matches_source(url: str, hostname: str | None, source: str) -> bool:
    # Several agencies share this email redirect service. The listing's stored
    # source, not ap.immo's default URL classification, identifies the agency.
    if hostname == "ap.immo" and source in {"barnes", "junot", "consultantsimmobilier"}:
        return True
    detected = detect_source_from_url(url)
    return (
        detected is not None and listing_metrics.access_source(detected, url) == source
    )


async def _candidate_urls() -> dict[str, list[str]]:
    candidates = {}
    async with async_session() as db:
        for source in sorted(listing_metrics.SOURCES - DISABLED_PROBE_SOURCES):
            unavailable = _unavailable_targets.setdefault(source, {})
            now = time.monotonic()
            for url, expires in list(unavailable.items()):
                if expires <= now:
                    del unavailable[url]
            stored_source = "seloger" if source == "bellesdemeures" else source
            statement = select(Listing.external_url).where(
                Listing.source == stored_source, Listing.external_url.isnot(None)
            )
            if unavailable:
                # Exclude before LIMIT, otherwise the same removed adverts can
                # permanently hide every older live target from later checks.
                statement = statement.where(
                    Listing.external_url.not_in(list(unavailable))
                )
            if source in PROBE_HOSTS:
                # Filter BEFORE the limit so a busy sibling site cannot starve
                # this site's candidate list. Still validate every URL below.
                statement = statement.where(
                    or_(
                        *(
                            Listing.external_url.like(f"https://{host}{port}/%")
                            for host in PROBE_HOSTS[source]
                            for port in ("", ":443")
                        )
                    )
                )
            rows = await db.execute(
                statement.order_by(
                    Listing.last_seen_at.desc(), Listing.id.desc()
                ).limit(30)
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
                scraper_source = "seloger" if source == "bellesdemeures" else source
                result = await scrape_listing(url, scraper_source, purpose="probe")
                if result.page_text:
                    listing_metrics.probe_result(source, True)
                    logger.info("Listing probe succeeded: source=%s", source)
                    return True
                if not result.unavailable:
                    reason = "access_failed"
                    break
                # A removed advert is not a provider outage. Try another recent one.
                unavailable = _unavailable_targets.setdefault(source, {})
                unavailable.pop(url, None)
                unavailable[url] = time.monotonic() + UNAVAILABLE_TTL_SECONDS
                while len(unavailable) > MAX_UNAVAILABLE_TARGETS:
                    del unavailable[next(iter(unavailable))]
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
