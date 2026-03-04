import base64
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from app.models.listing import Listing, ListingPhoto
from app.services.browser_scraper import ScrapedListing
from app.services.email_processor import process_emails_for_user
from app.services.llm_extractor import ExtractedListing

# Shared mock return values to avoid repetition across patches
FAKE_GMAIL_MESSAGE = {
    "payload": {
        "mimeType": "text/html",
        "headers": [{"name": "From", "value": "alerts@seloger.com"}],
        "body": {"data": base64.urlsafe_b64encode(b"<html>test</html>").decode()},
    }
}

FAKE_SCRAPED = ScrapedListing(
    resolved_url="https://www.seloger.com/annonces/123.htm",
    source_id="123",
    photo_urls=["https://mms.seloger.com/photo1.jpg"],
    page_text="Appartement 3 pieces 60m2",
)

FAKE_EXTRACTED = ExtractedListing(
    is_listing=True,
    title="Bel Appartement",
    price=450000,
    sqm=60,
    bedrooms=2,
    city="Paris",
    district="Marais",
)

FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

# All patches target the email_processor module namespace
_M = "app.services.email_processor"


def _apply_all_patches(stack: ExitStack) -> None:
    """Enter all patches needed to isolate process_emails_for_user from external I/O."""
    targets = {
        f"{_M}._get_gmail_service": MagicMock(return_value=MagicMock()),
        f"{_M}._gmail_list_messages": MagicMock(return_value=[{"id": "msg1"}]),
        f"{_M}._gmail_get_message": MagicMock(return_value=FAKE_GMAIL_MESSAGE),
        f"{_M}.extract_listing_urls": AsyncMock(
            return_value=["https://www.seloger.com/annonces/123.htm"]
        ),
        f"{_M}.extract_photos_from_html": MagicMock(
            return_value=["https://mms.seloger.com/photo1.jpg"]
        ),
        f"{_M}.scrape_listing": AsyncMock(return_value=FAKE_SCRAPED),
        f"{_M}.extract_listing_from_page": AsyncMock(return_value=FAKE_EXTRACTED),
        f"{_M}.classify_photos": AsyncMock(side_effect=lambda _key, data: data),
        f"{_M}.download_photo": AsyncMock(return_value=FAKE_PNG_BYTES),
        f"{_M}.compute_phash": MagicMock(return_value="abcdef1234567890"),
        f"{_M}.get_minio_client": MagicMock(return_value=MagicMock()),
        f"{_M}.ensure_bucket": MagicMock(),
        f"{_M}.upload_photo": MagicMock(return_value="photos/uploaded.jpg"),
    }
    for target, mock_value in targets.items():
        stack.enter_context(patch(target, mock_value))


class TestProcessEmailsForUser:
    async def test_creates_listing(self, db_session, test_user):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        await db_session.commit()

        with ExitStack() as stack:
            _apply_all_patches(stack)
            count = await process_emails_for_user(test_user, db_session)

        assert count == 1

        result = await db_session.execute(select(Listing).where(Listing.user_id == test_user.id))
        listing = result.scalars().first()
        assert listing is not None
        assert listing.title == "Bel Appartement"
        assert listing.price == 450000
        assert listing.city == "Paris"

        photos_result = await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
        photos = photos_result.scalars().all()
        assert len(photos) >= 1

    async def test_no_credentials_returns_zero(self, db_session, test_user):
        """User without gmail_refresh_token should be skipped immediately."""
        test_user.gmail_refresh_token = None
        test_user.openai_api_key = None
        await db_session.commit()

        count = await process_emails_for_user(test_user, db_session)

        assert count == 0

        result = await db_session.execute(select(Listing).where(Listing.user_id == test_user.id))
        assert result.scalars().first() is None

    async def test_no_credentials_with_only_openai_key(self, db_session, test_user):
        """Having only an OpenAI key but no Gmail token should still return 0."""
        test_user.gmail_refresh_token = None
        test_user.openai_api_key = "sk-test-key"
        await db_session.commit()

        count = await process_emails_for_user(test_user, db_session)

        assert count == 0
