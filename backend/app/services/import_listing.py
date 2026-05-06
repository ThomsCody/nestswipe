import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Favorite
from app.models.listing import Listing, ListingPhoto, PriceHistory
from app.models.user import User
from app.services.browser_scraper import (
    MAX_PHOTOS_PER_LISTING,
    detect_source_from_url,
    scrape_listing,
)
from app.services.duplicate_detector import compute_fingerprint, find_duplicate
from app.services.llm_extractor import extract_listing_from_page
from app.services.photo_classifier import classify_photos
from app.services.photo_storage import (
    compute_phash,
    download_photo,
    ensure_bucket,
    get_minio_client,
    upload_photo,
)

logger = logging.getLogger(__name__)


class ImportError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class ImportResult:
    favorite: Favorite
    listing: Listing
    created: bool
    already_favorited: bool


async def import_listing_from_url(
    url: str, user: User, db: AsyncSession
) -> ImportResult:
    """Import a listing from a URL directly into the user's favorites."""

    # 1. Detect source
    source = detect_source_from_url(url)
    if not source:
        raise ImportError("Unsupported domain. Supported: seloger, pap, leboncoin, consultantsimmobilier, barnes, junot.")

    # 2. Resolve API key: user's own, otherwise any household member's
    api_key = user.openai_api_key
    if not api_key:
        result = await db.execute(
            select(User.openai_api_key).where(
                User.household_id == user.household_id,
                User.openai_api_key.isnot(None),
            ).limit(1)
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            logger.info("User %d has no OpenAI key, falling back to household %d key", user.id, user.household_id)
    if not api_key:
        raise ImportError("No OpenAI API key available. You or a household member must set one in Settings.")

    # 3. Scrape
    scraped = await scrape_listing(url, source)
    if not scraped.page_text:
        raise ImportError("Could not load the listing page. The site may be blocking requests.", status_code=502)

    # 4. LLM extraction
    extracted = await extract_listing_from_page(api_key, scraped.page_text, source)
    if not extracted or not extracted.title:
        raise ImportError("Could not extract listing data from the page.", status_code=502)

    # Set URL — keep original for ap.immo links (they carry auth params)
    if source in ("consultantsimmobilier", "barnes", "junot") and "ap.immo" in url:
        extracted.external_url = url
    else:
        extracted.external_url = scraped.resolved_url or url
    if scraped.source_id:
        extracted.source_id = scraped.source_id

    # Compute price_per_sqm
    price_per_sqm = None
    if extracted.price and extracted.sqm and extracted.sqm > 0:
        price_per_sqm = round(extracted.price / extracted.sqm, 2)

    fingerprint = compute_fingerprint(
        source, extracted.city, extracted.district,
        extracted.sqm, extracted.bedrooms, extracted.price,
    )

    # 5. Download + classify photos (optional — manual imports proceed without photos)
    photo_data: list[tuple[bytes, str | None, str]] = []
    photo_phashes: list[str] = []
    photo_urls = scraped.photo_urls or []
    for photo_url in photo_urls[:MAX_PHOTOS_PER_LISTING]:
        img_bytes = await download_photo(photo_url)
        if img_bytes:
            phash = compute_phash(img_bytes)
            photo_data.append((img_bytes, phash, photo_url))
            if phash:
                photo_phashes.append(phash)

    if photo_data:
        photo_data = await classify_photos(api_key, photo_data)
        photo_phashes = [phash for _, phash, _ in photo_data if phash]

    # 6. Check for duplicates
    existing = await find_duplicate(
        db, user.id, source,
        extracted.source_id, extracted.external_url,
        fingerprint, photo_phashes,
    )

    now = datetime.now(timezone.utc)
    created = False

    if existing:
        listing = existing
        listing.last_seen_at = now
        if extracted.price and extracted.price != existing.price:
            db.add(PriceHistory(listing_id=existing.id, price=extracted.price))
            listing.price = extracted.price
            if listing.sqm and listing.sqm > 0:
                listing.price_per_sqm = round(extracted.price / listing.sqm, 2)
        # Backfill missing fields
        for fld in (
            "title", "description", "sqm", "bedrooms", "rooms",
            "floor", "city", "district", "location_detail",
            "external_url", "source_id",
            "contact_phone", "agency_name", "agent_name",
        ):
            new_val = getattr(extracted, fld, None)
            if new_val is not None and getattr(listing, fld, None) is None:
                setattr(listing, fld, new_val)
    else:
        listing = Listing(
            household_id=user.household_id,
            user_id=user.id,
            source=source,
            source_id=extracted.source_id,
            external_url=extracted.external_url,
            title=extracted.title,
            description=extracted.description,
            price=extracted.price,
            sqm=extracted.sqm,
            price_per_sqm=price_per_sqm,
            bedrooms=extracted.bedrooms,
            rooms=extracted.rooms,
            floor=extracted.floor,
            city=extracted.city,
            district=extracted.district,
            location_detail=extracted.location_detail,
            contact_phone=extracted.contact_phone,
            agency_name=extracted.agency_name,
            agent_name=extracted.agent_name,
            fingerprint=fingerprint,
        )
        db.add(listing)
        await db.flush()
        created = True

        if extracted.price:
            db.add(PriceHistory(listing_id=listing.id, price=extracted.price))

        # Upload photos
        if photo_data:
            minio_client = get_minio_client()
            ensure_bucket(minio_client)
            for i, (img_bytes, phash, original_url) in enumerate(photo_data):
                s3_key = upload_photo(minio_client, img_bytes)
                db.add(ListingPhoto(
                    listing_id=listing.id,
                    s3_key=s3_key,
                    original_url=original_url,
                    phash=phash,
                    position=i,
                ))

        logger.info("Created new listing %d: %s", listing.id, listing.title)

    # 7. Create favorite if not already favorited
    already_favorited = False
    fav_result = await db.execute(
        select(Favorite).where(
            Favorite.household_id == user.household_id,
            Favorite.listing_id == listing.id,
        )
    )
    favorite = fav_result.scalar_one_or_none()

    if favorite:
        already_favorited = True
    else:
        favorite = Favorite(
            household_id=user.household_id,
            listing_id=listing.id,
            seller_name=listing.agency_name or listing.agent_name,
            seller_phone=listing.contact_phone,
            seller_is_agency=bool(listing.agency_name),
        )
        db.add(favorite)

    await db.commit()
    await db.refresh(favorite)
    await db.refresh(listing)

    return ImportResult(
        favorite=favorite,
        listing=listing,
        created=created,
        already_favorited=already_favorited,
    )
