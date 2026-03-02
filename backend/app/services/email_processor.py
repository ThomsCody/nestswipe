import asyncio
import base64
import logging
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.listing import Listing, ListingPhoto, PriceHistory
from app.models.user import User
from app.services.browser_scraper import scrape_listing
from app.services.duplicate_detector import compute_fingerprint, find_duplicate
from app.services.llm_extractor import extract_listing, extract_listings
from app.services.photo_classifier import classify_photos
from app.services.photo_scraper import extract_photos_from_html
from app.services.photo_storage import (
    compute_phash,
    download_photo,
    ensure_bucket,
    get_minio_client,
    upload_photo,
)

logger = logging.getLogger(__name__)

SOURCES = {
    "seloger.com": "seloger",
    "pap.fr": "pap",
    "consultantsimmobilier.com": "consultantsimmobilier",
}


def _get_gmail_service(refresh_token: str):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _build_query(last_poll: datetime | None) -> str:
    sources = " OR ".join(f"from:{s}" for s in SOURCES)
    query = f"({sources})"
    if last_poll:
        # Use epoch seconds for second-level precision (YYYY/MM/DD is day-level)
        epoch = int(last_poll.timestamp())
        query += f" after:{epoch}"
    else:
        # First run: only fetch recent emails (tracking URLs expire after ~7 days)
        query += " newer_than:14d"
    return query


def _detect_source(from_header: str) -> str:
    from_lower = from_header.lower()
    for domain, name in SOURCES.items():
        if domain in from_lower:
            return name
    return "unknown"



def _extract_html_body(payload: dict) -> str:
    """Recursively extract HTML body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        html = _extract_html_body(part)
        if html:
            return html
    return ""


def _gmail_list_messages(service, query: str, max_results: int = 50) -> list[dict]:
    """Synchronous Gmail API call — run via to_thread."""
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return results.get("messages", [])


def _gmail_get_message(service, msg_id: str) -> dict:
    """Synchronous Gmail API call — run via to_thread."""
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()


async def process_emails_for_user(user: User, db: AsyncSession) -> int:
    if not user.gmail_refresh_token or not user.openai_api_key:
        return 0

    try:
        service = await asyncio.to_thread(_get_gmail_service, user.gmail_refresh_token)
    except Exception:
        logger.exception("Failed to get Gmail service for user %s", user.id)
        return 0

    first_run = user.last_email_poll is None
    query = _build_query(user.last_email_poll)
    # First run: cap at 100 emails to avoid processing the entire inbox.
    # Subsequent runs only fetch new emails (query already has after: filter).
    max_results = 100 if first_run else 50
    minio_client = get_minio_client()
    ensure_bucket(minio_client)

    processed = 0
    try:
        messages = await asyncio.to_thread(_gmail_list_messages, service, query, max_results)
        logger.info("Found %d email(s) matching query for user %s", len(messages), user.email)

        for msg_meta in messages:
            msg = await asyncio.to_thread(_gmail_get_message, service, msg_meta["id"])
            payload = msg.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            from_header = headers.get("from", "")
            source = _detect_source(from_header)
            if source == "unknown":
                continue

            html_body = _extract_html_body(payload)
            if not html_body:
                continue

            logger.info("Processing email from %s (msg %s, %d chars)", source, msg_meta["id"], len(html_body))

            # Use LLM to extract all listings from the email (handles single and multi-listing)
            all_extracted = await extract_listings(user.openai_api_key, html_body, source)
            if not all_extracted:
                logger.info("Email %s: no listings extracted", msg_meta["id"])
                continue
            logger.info("Email %s: extracted %d listing(s)", msg_meta["id"], len(all_extracted))

            for extracted in all_extracted:
                if not extracted.title:
                    continue

                logger.info("Extracted: %s — %s, %s€, %sm²", extracted.title, extracted.city, extracted.price, extracted.sqm)

                # URL resolution and photo scraping
                scraped = None
                if extracted.external_url:
                    scraped = await scrape_listing(extracted.external_url, source)
                    if scraped.resolved_url:
                        logger.info("Resolved URL: %s -> %s", extracted.external_url, scraped.resolved_url)
                        extracted.external_url = scraped.resolved_url
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

                # Photo fallback chain: listing page → email HTML → LLM extraction
                page_photos = scraped.photo_urls if scraped and scraped.photo_urls else []
                email_photos = extract_photos_from_html(html_body, source)
                llm_photos = extracted.photo_urls or []

                if page_photos:
                    photo_urls = page_photos
                    logger.info("Using %d photos from listing page", len(photo_urls))
                elif email_photos:
                    photo_urls = email_photos
                    logger.info("Falling back to %d photos from email HTML", len(photo_urls))
                else:
                    photo_urls = llm_photos
                    logger.info("Falling back to %d photos from LLM extraction", len(photo_urls))

                # Download photos and compute phashes
                photo_data: list[tuple[bytes, str | None, str]] = []
                photo_phashes: list[str] = []
                for url in photo_urls[:15]:
                    img_bytes = await download_photo(url)
                    if img_bytes:
                        phash = compute_phash(img_bytes)
                        photo_data.append((img_bytes, phash, url))
                        if phash:
                            photo_phashes.append(phash)

                # Filter out non-property photos (agency logos, agent portraits, etc.)
                if photo_data:
                    photo_data = await classify_photos(user.openai_api_key, photo_data)
                    photo_phashes = [phash for _, phash, _ in photo_data if phash]

                # Skip listings with no photos
                if not photo_data:
                    logger.info("Email %s: skipping listing with no usable photos", msg_meta["id"])
                    continue

                # Check for duplicates
                existing = await find_duplicate(
                    db, user.household_id, source,
                    extracted.source_id, extracted.external_url,
                    fingerprint, photo_phashes,
                )

                now = datetime.now(timezone.utc)

                if existing:
                    logger.info("Duplicate found (listing %d), updating", existing.id)
                    existing.last_seen_at = now
                    if extracted.price and extracted.price != existing.price:
                        db.add(PriceHistory(listing_id=existing.id, price=extracted.price))
                        existing.price = extracted.price
                        if existing.sqm and existing.sqm > 0:
                            existing.price_per_sqm = round(extracted.price / existing.sqm, 2)
                    # Backfill fields that were missing or have been updated
                    for field in ("title", "description", "sqm", "bedrooms", "rooms",
                                  "floor", "city", "district", "location_detail",
                                  "external_url", "source_id"):
                        new_val = getattr(extracted, field, None)
                        if new_val is not None and getattr(existing, field, None) is None:
                            setattr(existing, field, new_val)
                else:
                    listing = Listing(
                        household_id=user.household_id,
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
                        fingerprint=fingerprint,
                    )
                    db.add(listing)
                    await db.flush()

                    # Initial price history
                    if extracted.price:
                        db.add(PriceHistory(listing_id=listing.id, price=extracted.price))

                    # Upload photos
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

                processed += 1
                # Commit after each listing so progress is saved
                await db.commit()

        user.last_email_poll = datetime.now(timezone.utc)
        await db.commit()

    except Exception:
        logger.exception("Error processing emails for user %s", user.id)
        await db.rollback()

    return processed
