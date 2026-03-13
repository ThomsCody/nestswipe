"""Backfill consultantsimmobilier listing URLs with authenticated ap.immo links.

Re-reads recent Gmail emails from consultantsimmobilier.com, extracts ap.immo
URLs (which carry auth query params), and updates matching listings whose
external_url currently points to the extranet (not accessible without login).

Run from the backend container:

    python -m scripts.backfill_ci_urls [--dry-run] [--days 14]
"""

import argparse
import asyncio
import logging
import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import async_session
from app.models.listing import Listing
from app.models.user import User
from app.services.email_processor import (
    _get_gmail_service,
    _gmail_get_message,
    _gmail_list_messages,
    _extract_html_body,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Pattern: https://ap.immo/p/REFERENCE_ID?u=...&p=...
AP_IMMO_RE = re.compile(r"https://ap\.immo/p/(\d+)\?[^\s\"'<>]+")


def _extract_ap_immo_urls(html: str) -> dict[str, str]:
    """Extract ap.immo URLs from email HTML, keyed by reference ID."""
    urls: dict[str, str] = {}
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        match = AP_IMMO_RE.match(href)
        if match:
            ref_id = match.group(1)
            if ref_id not in urls:
                urls[ref_id] = href
    return urls


async def backfill(dry_run: bool = False, days: int = 14) -> None:
    async with async_session() as db:
        # Get a user with Gmail credentials
        user_result = await db.execute(
            select(User).where(User.gmail_refresh_token.isnot(None)).limit(1)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error("No user with Gmail credentials found")
            return

        # Fetch consultantsimmobilier emails from Gmail
        service = await asyncio.to_thread(_get_gmail_service, user.gmail_refresh_token)
        query = f"from:consultantsimmobilier.com newer_than:{days}d"
        messages = await asyncio.to_thread(_gmail_list_messages, service, query, 200)
        logger.info("Found %d email(s) from consultantsimmobilier in last %d days", len(messages), days)

        # Collect all ap.immo URLs keyed by reference ID
        all_urls: dict[str, str] = {}
        for msg_meta in messages:
            msg = await asyncio.to_thread(_gmail_get_message, service, msg_meta["id"])
            html = _extract_html_body(msg.get("payload", {}))
            if html:
                urls = _extract_ap_immo_urls(html)
                for ref_id, url in urls.items():
                    if ref_id not in all_urls:
                        all_urls[ref_id] = url

        logger.info("Extracted %d unique ap.immo URL(s) from emails", len(all_urls))
        if not all_urls:
            return

        # Find consultantsimmobilier listings that need URL updates
        result = await db.execute(
            select(Listing).where(
                Listing.source == "consultantsimmobilier",
            )
        )
        listings = result.scalars().all()
        logger.info("Found %d consultantsimmobilier listing(s) in DB", len(listings))

        updated = 0
        for listing in listings:
            # Match by source_id
            if listing.source_id and listing.source_id in all_urls:
                new_url = all_urls[listing.source_id]
                if listing.external_url == new_url:
                    continue
                old_url = listing.external_url
                prefix = "[DRY RUN] " if dry_run else ""
                logger.info(
                    "%sListing %d (%s): %s -> %s",
                    prefix, listing.id, listing.title, old_url, new_url,
                )
                if not dry_run:
                    listing.external_url = new_url
                updated += 1
                continue

            # Fallback: try to extract ref from current external_url
            if listing.external_url:
                match = re.search(r"/p/(\d+)", listing.external_url)
                if match:
                    ref_id = match.group(1)
                    if ref_id in all_urls:
                        new_url = all_urls[ref_id]
                        if listing.external_url == new_url:
                            continue
                        old_url = listing.external_url
                        prefix = "[DRY RUN] " if dry_run else ""
                        logger.info(
                            "%sListing %d (%s): %s -> %s",
                            prefix, listing.id, listing.title, old_url, new_url,
                        )
                        if not dry_run:
                            listing.external_url = new_url
                            if not listing.source_id:
                                listing.source_id = ref_id
                        updated += 1

        if not dry_run and updated > 0:
            await db.commit()

        logger.info("Done: %d listing(s) updated", updated)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill consultantsimmobilier URLs with authenticated ap.immo links"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log changes without writing to DB")
    parser.add_argument("--days", type=int, default=14, help="How far back to scan emails (default: 14)")
    args = parser.parse_args()

    asyncio.run(backfill(dry_run=args.dry_run, days=args.days))


if __name__ == "__main__":
    main()
