import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import SwipeAction, SwipeDirection
from app.models.listing import Listing
from app.models.user import User
from app.services.browser_scraper import (
    MAX_PHOTOS_PER_LISTING,
    detect_source_from_url,
    scrape_listing,
)
from app.services.duplicate_detector import compute_fingerprint, find_listing_in_household
from app.services.llm_extractor import extract_listing_from_page
from app.services.photo_storage import compute_phash, download_photo

logger = logging.getLogger(__name__)


class LookupError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def lookup_listing_in_archive(url: str, user: User, db: AsyncSession) -> int:
    """
    Run the full 4-layer dedup pipeline against the household's listings,
    then confirm the matched listing is in the household's archive.
    Returns the listing ID on success.
    """
    source = detect_source_from_url(url)
    if not source:
        raise LookupError("Unsupported domain.", status_code=400)

    api_key = user.openai_api_key
    if not api_key:
        result = await db.execute(
            select(User.openai_api_key).where(
                User.household_id == user.household_id,
                User.openai_api_key.isnot(None),
            ).limit(1)
        )
        api_key = result.scalar_one_or_none()
    if not api_key:
        raise LookupError("No OpenAI API key available.", status_code=400)

    # 1. Scrape the page
    scraped = await scrape_listing(url, source)
    if not scraped.page_text:
        raise LookupError("Could not load the listing page.", status_code=502)

    # 2. LLM extraction to build the fingerprint
    extracted, _, _ = await extract_listing_from_page(api_key, scraped.page_text, source)
    if not extracted or not extracted.title:
        raise LookupError("Could not extract listing data from the page.", status_code=502)

    if source in ("consultantsimmobilier", "barnes", "junot") and "ap.immo" in url:
        extracted.external_url = url
    else:
        extracted.external_url = scraped.resolved_url or url
    if scraped.source_id:
        extracted.source_id = scraped.source_id

    fingerprint = compute_fingerprint(
        source, extracted.city, extracted.district,
        extracted.sqm, extracted.bedrooms, extracted.price,
    )

    # 3. Download photos and compute phashes (no classification needed — just hashes)
    photo_phashes: list[str] = []
    for photo_url in (scraped.photo_urls or [])[:MAX_PHOTOS_PER_LISTING]:
        img_bytes = await download_photo(photo_url)
        if img_bytes:
            phash = compute_phash(img_bytes)
            if phash:
                photo_phashes.append(phash)

    # 4. Full 4-layer dedup across the household
    listing = await find_listing_in_household(
        db, user.household_id, source,
        extracted.source_id, extracted.external_url,
        fingerprint, photo_phashes,
    )

    if not listing:
        raise LookupError("not_in_database", status_code=404)

    # 5. Confirm it's in the household's archive (passed by any member)
    household_user_ids = select(User.id).where(User.household_id == user.household_id)
    swipe_result = await db.execute(
        select(SwipeAction).where(
            SwipeAction.user_id.in_(household_user_ids),
            SwipeAction.listing_id == listing.id,
            SwipeAction.action == SwipeDirection.pass_,
        )
    )
    if not swipe_result.scalar_one_or_none():
        raise LookupError("not_in_archive", status_code=404)

    return listing.id
