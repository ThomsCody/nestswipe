import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.listing import Listing, ListingPhoto, PriceHistory
from app.models.parse_attempt import ParseAttempt
from app.models.user import User
from app.services.browser_scraper import scrape_listing, MAX_PHOTOS_PER_LISTING
from app.services.duplicate_detector import compute_fingerprint, find_duplicate
from app.services.email_url_extractor import extract_listing_urls
from app.services.llm_extractor import extract_listing_from_page
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
    "barnes-international.com": "barnes",
    "no.reply@leboncoin.fr": "leboncoin",
    "junot.fr": "junot",
}

# Gmail may delay indexing emails by a few minutes after delivery.
# Overlap the query window by this amount so we don't miss emails that
# arrived but weren't searchable yet during the previous poll cycle.
GMAIL_INDEX_LAG = timedelta(minutes=10)


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
        # Subtract a safety margin so emails that Gmail was slow to index
        # aren't missed.  Duplicates are handled downstream by the dedup layer.
        safe_cutoff = last_poll - GMAIL_INDEX_LAG
        epoch = int(safe_cutoff.timestamp())
        query += f" after:{epoch}"
    else:
        # First run: only fetch recent emails (tracking URLs expire after ~7 days)
        query += " newer_than:14d"
    return query


def _detect_source(from_header: str) -> str:
    from_lower = from_header.lower()
    for key, name in SOURCES.items():
        if "@" in key:
            # Full email address match — avoids matching other subdomains
            # (e.g. messagerie.leboncoin.fr must NOT match)
            if key in from_lower:
                return name
        else:
            if key in from_lower:
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
        logger.info("Gmail query: %s | Found %d email(s) for user %s", query, len(messages), user.email)

        for msg_meta in messages:
            msg = await asyncio.to_thread(_gmail_get_message, service, msg_meta["id"])
            payload = msg.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            from_header = headers.get("from", "")
            source = _detect_source(from_header)
            if source == "unknown":
                continue

            # Gmail's index-lag overlap window (GMAIL_INDEX_LAG) can re-surface
            # the same email in consecutive poll cycles. Skip it here — before
            # any LLM/scrape calls — rather than relying on downstream listing
            # dedup, which only runs *after* the costly steps.
            already_attempted = await db.execute(
                select(ParseAttempt.id)
                .where(
                    ParseAttempt.household_id == user.household_id,
                    ParseAttempt.email_id == msg_meta["id"],
                )
                .limit(1)
            )
            if already_attempted.scalar_one_or_none() is not None:
                logger.info("Skipping already-processed email %s", msg_meta["id"])
                db.add(ParseAttempt(
                    household_id=user.household_id,
                    user_id=user.id,
                    source=source,
                    email_id=msg_meta["id"],
                    url=None,
                    status="skipped_duplicate_email",
                    call_type="skipped_duplicate_email",
                ))
                await db.flush()
                await db.commit()
                continue

            html_body = _extract_html_body(payload)
            if not html_body:
                continue

            logger.info("Processing email from %s (msg %s, %d chars)", source, msg_meta["id"], len(html_body))

            # Step 1: Extract candidate listing URLs from email HTML via LLM
            candidate_urls, url_inp, url_out = await extract_listing_urls(user.openai_api_key, html_body, source)
            if not candidate_urls:
                logger.warning("extraction_failed: no candidate URLs found",
                               extra={"event": "extraction_failed", "reason": "no_urls",
                                      "source": source, "email_id": msg_meta["id"]})
                db.add(ParseAttempt(
                    household_id=user.household_id,
                    user_id=user.id,
                    source=source,
                    email_id=msg_meta["id"],
                    url=None,
                    status="failed",
                    fail_reason="no_urls",
                    llm_input_tokens=url_inp,
                    llm_output_tokens=url_out,
                    call_type="url_extraction",
                ))
                await db.flush()
                await db.commit()
                continue
            logger.info("Email %s: found %d candidate URL(s)", msg_meta["id"], len(candidate_urls))

            # Record the URL-extraction step's cost separately — it isn't tied
            # to any single listing outcome below.
            db.add(ParseAttempt(
                household_id=user.household_id,
                user_id=user.id,
                source=source,
                email_id=msg_meta["id"],
                url=None,
                status="tracking",
                call_type="url_extraction",
                llm_input_tokens=url_inp,
                llm_output_tokens=url_out,
            ))

            # Pre-extract email photos as fallback (cheap, no LLM)
            email_photos = extract_photos_from_html(html_body, source)

            # Track resolved listings to avoid re-processing duplicate tracking URLs
            seen_source_ids: set[str] = set()
            seen_resolved_urls: set[str] = set()

            for url in candidate_urls:
                # Step 2: Scrape listing page → resolved URL, source_id, photos, page text
                scraped = await scrape_listing(url, source)
                if not scraped.resolved_url:
                    logger.warning("extraction_failed: no valid resolved page",
                                   extra={"event": "extraction_failed", "reason": "no_resolved_url",
                                          "source": source, "url": url})
                    db.add(ParseAttempt(
                        household_id=user.household_id,
                        user_id=user.id,
                        source=source,
                        email_id=msg_meta["id"],
                        url=url,
                        status="failed",
                        fail_reason="no_resolved_url",
                    ))
                    continue
                if not scraped.page_text:
                    logger.warning("extraction_failed: no page text extracted",
                                   extra={"event": "extraction_failed", "reason": "no_page_text",
                                          "source": source, "url": url})
                    db.add(ParseAttempt(
                        household_id=user.household_id,
                        user_id=user.id,
                        source=source,
                        email_id=msg_meta["id"],
                        url=url,
                        status="failed",
                        fail_reason="no_page_text",
                    ))
                    continue
                if scraped.source_id and scraped.source_id in seen_source_ids:
                    logger.info("Skipping duplicate source_id %s: %s", scraped.source_id, url)
                    continue
                if scraped.resolved_url in seen_resolved_urls:
                    logger.info("Skipping duplicate resolved URL %s: %s", scraped.resolved_url, url)
                    continue
                if scraped.source_id:
                    seen_source_ids.add(scraped.source_id)
                seen_resolved_urls.add(scraped.resolved_url)

                # Step 3: LLM extraction on page text
                extracted, llm_inp, llm_out = await extract_listing_from_page(
                    user.openai_api_key, scraped.page_text, source
                )
                if not extracted or not extracted.title:
                    logger.warning("extraction_failed: LLM found no listing",
                                   extra={"event": "extraction_failed", "reason": "llm_no_listing",
                                          "source": source, "url": url})
                    db.add(ParseAttempt(
                        household_id=user.household_id,
                        user_id=user.id,
                        source=source,
                        email_id=msg_meta["id"],
                        url=url,
                        status="failed",
                        fail_reason="llm_no_listing",
                        llm_input_tokens=llm_inp,
                        llm_output_tokens=llm_out,
                        page_extraction_input_tokens=llm_inp,
                        page_extraction_output_tokens=llm_out,
                        page_text_chars=len(scraped.page_text),
                    ))
                    continue

                # Use resolved URL — except for consultantsimmobilier where
                # the original ap.immo link carries auth query params (u=, p=)
                # that are required to view the listing without an extranet login.
                if source in ("consultantsimmobilier", "barnes", "junot") and "ap.immo" in url:
                    extracted.external_url = url
                else:
                    extracted.external_url = scraped.resolved_url
                if scraped.source_id:
                    extracted.source_id = scraped.source_id

                logger.info(
                    "Extracted from page: %s — %s, %s€, %sm², %s bedrooms, floor %s",
                    extracted.title, extracted.city, extracted.price,
                    extracted.sqm, extracted.bedrooms, extracted.floor,
                )

                # Compute price_per_sqm
                price_per_sqm = None
                if extracted.price and extracted.sqm and extracted.sqm > 0:
                    price_per_sqm = round(extracted.price / extracted.sqm, 2)

                fingerprint = compute_fingerprint(
                    source, extracted.city, extracted.district,
                    extracted.sqm, extracted.bedrooms, extracted.price,
                )

                # Photo fallback chain: listing page → email HTML
                page_photos = scraped.photo_urls or []
                if page_photos:
                    photo_urls = page_photos
                    photo_labels = scraped.photo_labels
                    logger.info("Using %d photos from listing page", len(photo_urls))
                elif email_photos:
                    photo_urls = email_photos
                    photo_labels = {}
                    logger.info("Falling back to %d photos from email HTML", len(photo_urls))
                else:
                    photo_urls = []
                    photo_labels = {}

                # Download photos and compute phashes
                photo_data: list[tuple[bytes, str | None, str]] = []
                photo_phashes: list[str] = []
                for photo_url in photo_urls[:MAX_PHOTOS_PER_LISTING]:
                    img_bytes = await download_photo(photo_url)
                    if img_bytes:
                        phash = compute_phash(img_bytes)
                        photo_data.append((img_bytes, phash, photo_url))
                        if phash:
                            photo_phashes.append(phash)

                # Photos SeLoger's own scene classifier already confirmed are a
                # real room skip our vision call entirely; everything else
                # (unlabeled, or from a source with no such signal) still goes
                # through GPT-4o-mini classification as before.
                sent_photo_count = len(photo_data)
                pre_approved = [pd for pd in photo_data if pd[2] in photo_labels]
                needs_vision = [pd for pd in photo_data if pd[2] not in photo_labels]

                photo_inp = photo_out = 0
                classified: list[tuple[bytes, str | None, str]] = []
                if needs_vision:
                    classified, photo_inp, photo_out = await classify_photos(user.openai_api_key, needs_vision)
                photo_data = pre_approved + classified
                photo_phashes = [phash for _, phash, _ in photo_data if phash]

                # Skip listings with no photos
                if not photo_data:
                    logger.warning("extraction_failed: no usable photos",
                                   extra={"event": "extraction_failed", "reason": "no_photos",
                                          "source": source, "url": url})
                    db.add(ParseAttempt(
                        household_id=user.household_id,
                        user_id=user.id,
                        source=source,
                        email_id=msg_meta["id"],
                        url=url,
                        status="failed",
                        fail_reason="no_photos",
                        llm_input_tokens=llm_inp + photo_inp,
                        llm_output_tokens=llm_out + photo_out,
                        page_extraction_input_tokens=llm_inp,
                        page_extraction_output_tokens=llm_out,
                        photo_classification_input_tokens=photo_inp,
                        photo_classification_output_tokens=photo_out,
                        page_text_chars=len(scraped.page_text),
                        photo_count=sent_photo_count,
                    ))
                    continue

                # Check for duplicates
                existing = await find_duplicate(
                    db, user.id, source,
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
                    # Backfill fields that were missing
                    for fld in ("title", "description", "sqm", "bedrooms", "rooms",
                                "floor", "city", "district", "location_detail",
                                "external_url", "source_id",
                                "contact_phone", "agency_name", "agent_name"):
                        new_val = getattr(extracted, fld, None)
                        if new_val is not None and getattr(existing, fld, None) is None:
                            setattr(existing, fld, new_val)
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

                db.add(ParseAttempt(
                    household_id=user.household_id,
                    user_id=user.id,
                    source=source,
                    email_id=msg_meta["id"],
                    url=url,
                    status="success",
                    fail_reason=None,
                    result="updated" if existing else "new",
                    llm_input_tokens=llm_inp + photo_inp,
                    llm_output_tokens=llm_out + photo_out,
                    page_extraction_input_tokens=llm_inp,
                    page_extraction_output_tokens=llm_out,
                    photo_classification_input_tokens=photo_inp,
                    photo_classification_output_tokens=photo_out,
                    page_text_chars=len(scraped.page_text),
                    photo_count=sent_photo_count,
                ))
                processed += 1
                # Commit after each listing so progress is saved
                await db.commit()

        user.last_email_poll = datetime.now(timezone.utc)
        await db.commit()

    except Exception:
        logger.exception("Error processing emails for user %s", user.id)
        await db.rollback()

    return processed
