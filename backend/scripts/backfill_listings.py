"""Backfill existing listings by re-scraping their page and running LLM extraction.

Targets listings with NULL bedrooms or floor that have an external_url.
Run from the backend container:

    python -m scripts.backfill_listings [--dry-run] [--limit N]
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import or_, select

from app.database import async_session
from app.models.listing import Listing
from app.models.user import User
from app.services.browser_scraper import scrape_listing
from app.services.llm_extractor import extract_listing_from_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Fields to backfill from page extraction
BACKFILL_FIELDS = (
    "bedrooms", "rooms", "floor", "sqm",
    "city", "district", "location_detail", "description",
)


async def backfill(dry_run: bool = False, limit: int = 0) -> None:
    async with async_session() as db:
        # Find listings missing key fields that have a URL to scrape
        query = (
            select(Listing)
            .where(Listing.external_url.isnot(None))
            .where(or_(Listing.bedrooms.is_(None), Listing.floor.is_(None)))
            .order_by(Listing.id)
        )
        if limit > 0:
            query = query.limit(limit)

        result = await db.execute(query)
        listings = result.scalars().all()
        logger.info("Found %d listing(s) to backfill", len(listings))

        if not listings:
            return

        # We need an OpenAI API key — grab one from the first user that has one
        user_result = await db.execute(
            select(User).where(User.openai_api_key.isnot(None)).limit(1)
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.openai_api_key:
            logger.error("No user with an OpenAI API key found — cannot run LLM extraction")
            return

        updated = 0
        skipped = 0

        for listing in listings:
            logger.info(
                "[%d/%d] Backfilling listing %d: %s (%s)",
                updated + skipped + 1, len(listings),
                listing.id, listing.title, listing.external_url,
            )

            scraped = await scrape_listing(listing.external_url, listing.source)
            if not scraped.page_text:
                logger.warning("  No page text for listing %d, skipping", listing.id)
                skipped += 1
                continue

            extracted = await extract_listing_from_page(
                user.openai_api_key, scraped.page_text, listing.source,
            )
            if not extracted:
                logger.warning("  LLM extraction returned nothing for listing %d, skipping", listing.id)
                skipped += 1
                continue

            # Apply backfill: only fill in NULL fields
            changes = []
            for fld in BACKFILL_FIELDS:
                new_val = getattr(extracted, fld, None)
                if new_val is not None and getattr(listing, fld, None) is None:
                    if not dry_run:
                        setattr(listing, fld, new_val)
                    changes.append(f"{fld}={new_val}")

            # Also update price_per_sqm if we now have sqm
            if listing.price and listing.sqm and listing.sqm > 0 and not listing.price_per_sqm:
                ppsqm = round(listing.price / listing.sqm, 2)
                if not dry_run:
                    listing.price_per_sqm = ppsqm
                changes.append(f"price_per_sqm={ppsqm}")

            if changes:
                prefix = "[DRY RUN] " if dry_run else ""
                logger.info("  %sUpdated listing %d: %s", prefix, listing.id, ", ".join(changes))
                updated += 1
            else:
                logger.info("  No new data for listing %d", listing.id)
                skipped += 1

            if not dry_run:
                await db.commit()

        logger.info("Done: %d updated, %d skipped out of %d total", updated, skipped, len(listings))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill listing fields from page scraping")
    parser.add_argument("--dry-run", action="store_true", help="Log changes without writing to DB")
    parser.add_argument("--limit", type=int, default=0, help="Max listings to process (0 = all)")
    args = parser.parse_args()

    asyncio.run(backfill(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
