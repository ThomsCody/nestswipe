import asyncio
import base64
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sqlalchemy import select

from app.models.listing import Listing, ListingPhoto
from app.models.parse_attempt import ParseAttempt
from app.services.email_processing_state import (
    get_polling_state,
    track_email_processing,
)
from app.services.browser_scraper import ScrapedListing
from app.services.duplicate_detector import compute_fingerprint
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

FAKE_SCRAPED_PRE_APPROVED = ScrapedListing(
    resolved_url="https://www.seloger.com/annonces/456.htm",
    source_id="456",
    photo_urls=[
        "https://mms.seloger.com/photo1.jpg",
        "https://mms.seloger.com/photo2.jpg",
    ],
    photo_labels={"https://mms.seloger.com/photo1.jpg": "LIVING_ROOM"},
    page_text="Appartement 3 pieces 60m2",
)

FAKE_EXTRACTED = ExtractedListing(
    is_listing=True,
    title="Bel Appartement",
    price=450000,
    sqm=60,
    bedrooms=2,
    toilets=2,
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
            return_value=(["https://www.seloger.com/annonces/123.htm"], 8, 2)
        ),
        f"{_M}.extract_photos_from_html": MagicMock(
            return_value=["https://mms.seloger.com/photo1.jpg"]
        ),
        f"{_M}.scrape_listing": AsyncMock(return_value=FAKE_SCRAPED),
        f"{_M}.extract_listing_from_page": AsyncMock(
            return_value=(FAKE_EXTRACTED, 10, 5)
        ),
        f"{_M}.classify_photos": AsyncMock(
            side_effect=lambda _key, data: (data, 20, 3)
        ),
        f"{_M}.download_photo": AsyncMock(return_value=FAKE_PNG_BYTES),
        f"{_M}.compute_phash": MagicMock(return_value="abcdef1234567890"),
        f"{_M}.get_minio_client": MagicMock(return_value=MagicMock()),
        f"{_M}.ensure_bucket": MagicMock(),
        f"{_M}.upload_photo": MagicMock(return_value="photos/uploaded.jpg"),
    }
    for target, mock_value in targets.items():
        stack.enter_context(patch(target, mock_value))


class TestProcessEmailsForUser:
    async def test_remaining_email_count_excludes_duplicates_and_decreases(
        self, db_session, test_user
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        db_session.add(
            ParseAttempt(
                household_id=test_user.household_id,
                user_id=test_user.id,
                source="seloger",
                email_id="old",
                status="success",
            )
        )
        await db_session.commit()
        counts = []

        async def extract(*args):
            counts.append(get_polling_state(test_user.household_id)["remaining_emails"])
            # No listings found still completes an email and decrements the count.
            return ([], 8, 2)

        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(
                patch(
                    f"{_M}._gmail_list_messages",
                    return_value=[
                        {"id": "old"},
                        {"id": "new1"},
                        {"id": "new1"},
                        {"id": "new2"},
                        {"id": "new3"},
                    ],
                )
            )
            fetch = stack.enter_context(
                patch(f"{_M}._gmail_get_message", return_value=FAKE_GMAIL_MESSAGE)
            )
            stack.enter_context(
                patch(f"{_M}.extract_listing_urls", side_effect=extract)
            )
            await process_emails_for_user(test_user, db_session)
        assert counts == [3, 2, 1]
        assert [call.args[1] for call in fetch.call_args_list] == [
            "new1",
            "new2",
            "new3",
        ]
        assert get_polling_state(test_user.household_id)["remaining_emails"] == 0

    @pytest.mark.parametrize("scenario", ["empty", "duplicate", "unknown", "no_html"])
    async def test_no_parsing_keeps_indicator_hidden(
        self, db_session, test_user, scenario
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        if scenario == "duplicate":
            db_session.add(
                ParseAttempt(
                    household_id=test_user.household_id,
                    user_id=test_user.id,
                    source="seloger",
                    email_id="msg1",
                    status="success",
                )
            )
            await db_session.commit()
        message = deepcopy(FAKE_GMAIL_MESSAGE)
        if scenario == "unknown":
            message["payload"]["headers"][0]["value"] = "someone@example.com"
        if scenario == "no_html":
            message["payload"]["body"] = {}
        with ExitStack() as stack:
            _apply_all_patches(stack)
            if scenario == "empty":
                stack.enter_context(
                    patch(f"{_M}._gmail_list_messages", return_value=[])
                )
            stack.enter_context(patch(f"{_M}._gmail_get_message", return_value=message))
            tracking = stack.enter_context(
                patch(f"{_M}.track_email_processing", wraps=track_email_processing)
            )
            assert await process_emails_for_user(test_user, db_session) == 0
            tracking.assert_not_called()
        assert get_polling_state(test_user.household_id) == {
            "is_polling": False,
            "started_at": None,
            "remaining_emails": 0,
        }

    @pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
    async def test_indicator_tracks_actual_parsing_and_always_clears(
        self, db_session, test_user, outcome
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        household_id = test_user.household_id

        def list_messages(*args):
            assert not get_polling_state(household_id)["is_polling"]
            return [{"id": "msg1"}]

        async def extract(*args):
            state = get_polling_state(household_id)
            assert state["is_polling"]
            assert state["remaining_emails"] == 1
            assert state["started_at"] is not None
            assert not get_polling_state(household_id + 1)["is_polling"]
            if outcome == "error":
                raise RuntimeError("Extraction failed")
            if outcome == "cancelled":
                raise asyncio.CancelledError()
            return ([FAKE_SCRAPED.resolved_url], 8, 2)

        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(
                patch(f"{_M}._gmail_list_messages", side_effect=list_messages)
            )
            extraction = stack.enter_context(
                patch(f"{_M}.extract_listing_urls", side_effect=extract)
            )
            if outcome == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await process_emails_for_user(test_user, db_session)
            else:
                assert await process_emails_for_user(test_user, db_session) == (
                    1 if outcome == "success" else 0
                )
            extraction.assert_awaited_once()
        assert get_polling_state(household_id) == {
            "is_polling": False,
            "started_at": None,
            "remaining_emails": 0,
        }

    @pytest.mark.parametrize("failed", [False, True])
    async def test_duplicate_email_urls_are_scraped_only_once(
        self, db_session, test_user, failed
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        url = FAKE_SCRAPED.resolved_url
        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(
                patch(
                    f"{_M}.extract_listing_urls",
                    AsyncMock(return_value=([url, url], 8, 2)),
                )
            )
            scrape = stack.enter_context(
                patch(
                    f"{_M}.scrape_listing",
                    AsyncMock(
                        return_value=ScrapedListing() if failed else FAKE_SCRAPED
                    ),
                )
            )
            await process_emails_for_user(test_user, db_session)
        scrape.assert_awaited_once_with(url, "seloger", purpose="email")

    async def test_no_new_emails_never_requests_provider(self, db_session, test_user):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(patch(f"{_M}._gmail_list_messages", return_value=[]))
            scrape = stack.enter_context(patch(f"{_M}.scrape_listing", AsyncMock()))
            assert await process_emails_for_user(test_user, db_session) == 0
        scrape.assert_not_awaited()

    @pytest.mark.parametrize(
        "last_poll", [None, datetime(2026, 10, 13, tzinfo=timezone.utc)]
    )
    @pytest.mark.parametrize(
        "sender",
        [
            "alerts@bellesdemeures.com",
            "Belles Demeures <ALERTS@EMAIL.BELLESDEMEURES.COM>",
        ],
    )
    async def test_bellesdemeures_email_is_fetched_and_processed(
        self, db_session, test_user, sender, last_poll
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        test_user.last_email_poll = last_poll
        await db_session.commit()
        message = deepcopy(FAKE_GMAIL_MESSAGE)
        message["payload"]["headers"][0]["value"] = sender
        url = "https://www.bellesdemeures.com/annonces/vente/256203535/"
        scraped = deepcopy(FAKE_SCRAPED)
        scraped.resolved_url = url
        scraped.source_id = "256203535"

        with ExitStack() as stack:
            _apply_all_patches(stack)
            list_messages = stack.enter_context(
                patch(f"{_M}._gmail_list_messages", return_value=[{"id": "msg1"}])
            )
            stack.enter_context(patch(f"{_M}._gmail_get_message", return_value=message))
            extract_urls = stack.enter_context(
                patch(
                    f"{_M}.extract_listing_urls", AsyncMock(return_value=([url], 8, 2))
                )
            )
            scrape = stack.enter_context(
                patch(f"{_M}.scrape_listing", AsyncMock(return_value=scraped))
            )
            assert await process_emails_for_user(test_user, db_session) == 1

        assert "from:bellesdemeures.com" in list_messages.call_args.args[1].split()
        assert extract_urls.await_args.args[2] == "seloger"
        scrape.assert_awaited_once_with(url, "seloger", purpose="email")
        listing = (await db_session.execute(select(Listing))).scalar_one()
        assert listing.source == "seloger"
        assert listing.source_id == "256203535"
        assert listing.external_url == url

    @pytest.mark.parametrize("existing_source", [None, "junot", "pap"])
    async def test_junot_authenticated_entry_point_is_stored_and_refreshed(
        self, db_session, test_user, existing_source
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        bare = "https://ap.immo/p/86114147"
        original = "https://r.info.junot.fr/tr/cl/test-email-token"
        existing = None
        if existing_source:
            existing = Listing(
                user_id=test_user.id,
                household_id=test_user.household_id,
                source=existing_source,
                source_id="86114147",
                external_url=bare,
                title="Existing apartment",
            )
            db_session.add(existing)
        await db_session.commit()
        message = deepcopy(FAKE_GMAIL_MESSAGE)
        message["payload"]["headers"][0]["value"] = "alerts@info.junot.fr"
        scraped = ScrapedListing(
            resolved_url=bare,
            source_id="86114147",
            page_text="Apartment details",
            photo_urls=["https://example.com/photo.jpg"],
        )
        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(patch(f"{_M}._gmail_get_message", return_value=message))
            stack.enter_context(
                patch(
                    f"{_M}.extract_listing_urls",
                    AsyncMock(return_value=([original], 8, 2)),
                )
            )
            stack.enter_context(
                patch(f"{_M}.scrape_listing", AsyncMock(return_value=scraped))
            )
            stack.enter_context(
                patch(
                    f"{_M}.extract_listing_from_page",
                    AsyncMock(return_value=(deepcopy(FAKE_EXTRACTED), 10, 5)),
                )
            )
            if existing_source == "pap":
                stack.enter_context(
                    patch(f"{_M}.find_duplicate", AsyncMock(return_value=existing))
                )
            assert await process_emails_for_user(test_user, db_session) == 1
        listings = (await db_session.execute(select(Listing))).scalars().all()
        assert len(listings) == 1
        assert listings[0].toilets == 2
        assert listings[0].external_url == original

    @pytest.mark.parametrize("source_id", ["123", "old-publication", None])
    async def test_listing_update_refreshes_link(
        self, db_session, test_user, source_id
    ):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        old_seen_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        existing = Listing(
            user_id=test_user.id,
            household_id=test_user.household_id,
            source="seloger",
            source_id=source_id,
            external_url="https://www.seloger.com/annonces/old-publication.htm",
            title="Existing apartment",
            fingerprint=compute_fingerprint(
                "seloger",
                FAKE_EXTRACTED.city,
                FAKE_EXTRACTED.district,
                FAKE_EXTRACTED.sqm,
                FAKE_EXTRACTED.bedrooms,
                FAKE_EXTRACTED.price,
            ),
            first_seen_at=old_seen_at,
            last_seen_at=old_seen_at,
        )
        db_session.add(existing)
        await db_session.commit()
        listing_id = existing.id

        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(
                patch(
                    f"{_M}.extract_listing_from_page",
                    AsyncMock(return_value=(deepcopy(FAKE_EXTRACTED), 10, 5)),
                )
            )
            assert await process_emails_for_user(test_user, db_session) == 1

        db_session.expire_all()
        listing = (await db_session.execute(select(Listing))).scalar_one()
        assert listing.id == listing_id
        assert listing.external_url == FAKE_SCRAPED.resolved_url
        assert listing.first_seen_at.replace(tzinfo=timezone.utc) == old_seen_at
        assert listing.last_seen_at.replace(tzinfo=timezone.utc) > old_seen_at

    async def test_creates_listing(self, db_session, test_user):
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        await db_session.commit()

        with ExitStack() as stack:
            _apply_all_patches(stack)
            count = await process_emails_for_user(test_user, db_session)

        assert count == 1

        result = await db_session.execute(
            select(Listing).where(Listing.user_id == test_user.id)
        )
        listing = result.scalars().first()
        assert listing is not None
        assert listing.title == "Bel Appartement"
        assert listing.price == 450000
        assert listing.city == "Paris"
        assert listing.toilets == 2

        photos_result = await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
        photos = photos_result.scalars().all()
        assert len(photos) >= 1

    async def test_skips_vision_for_pre_approved_photos(self, db_session, test_user):
        """Photos SeLoger's own classifier already labeled as a real room should
        bypass classify_photos entirely; only the unlabeled one is sent."""
        test_user.gmail_refresh_token = "test-refresh-token"
        test_user.openai_api_key = "sk-test-key"
        await db_session.commit()

        classify_mock = AsyncMock(side_effect=lambda _key, data: (data, 20, 3))

        with ExitStack() as stack:
            _apply_all_patches(stack)
            stack.enter_context(
                patch(
                    f"{_M}.scrape_listing",
                    AsyncMock(return_value=FAKE_SCRAPED_PRE_APPROVED),
                )
            )
            stack.enter_context(patch(f"{_M}.classify_photos", classify_mock))
            count = await process_emails_for_user(test_user, db_session)

        assert count == 1
        classify_mock.assert_awaited_once()
        sent_urls = [url for _, _, url in classify_mock.call_args.args[1]]
        assert sent_urls == ["https://mms.seloger.com/photo2.jpg"]

        result = await db_session.execute(
            select(Listing).where(Listing.user_id == test_user.id)
        )
        listing = result.scalars().first()
        photos_result = await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
        assert len(photos_result.scalars().all()) == 2

    async def test_no_credentials_returns_zero(self, db_session, test_user):
        """User without gmail_refresh_token should be skipped immediately."""
        test_user.gmail_refresh_token = None
        test_user.openai_api_key = None
        await db_session.commit()

        count = await process_emails_for_user(test_user, db_session)

        assert count == 0

        result = await db_session.execute(
            select(Listing).where(Listing.user_id == test_user.id)
        )
        assert result.scalars().first() is None

    async def test_no_credentials_with_only_openai_key(self, db_session, test_user):
        """Having only an OpenAI key but no Gmail token should still return 0."""
        test_user.gmail_refresh_token = None
        test_user.openai_api_key = "sk-test-key"
        await db_session.commit()

        count = await process_emails_for_user(test_user, db_session)

        assert count == 0


async def test_email_persists_scraped_contact_over_llm(db_session, test_user):
    test_user.gmail_refresh_token = "test-refresh-token"
    test_user.openai_api_key = "test-key"
    await db_session.commit()
    scraped = deepcopy(FAKE_SCRAPED)
    scraped.contact_phone = "06 14 59 87 04"
    scraped.agency_name = "IVA IMMOBILIER"
    scraped.agent_name = "Ethan Naim"
    extracted = deepcopy(FAKE_EXTRACTED)
    extracted.contact_phone = "01 53 38 28 00"
    with ExitStack() as stack:
        _apply_all_patches(stack)
        stack.enter_context(
            patch(f"{_M}.scrape_listing", AsyncMock(return_value=scraped))
        )
        stack.enter_context(
            patch(
                f"{_M}.extract_listing_from_page",
                AsyncMock(return_value=(extracted, 0, 0)),
            )
        )
        assert await process_emails_for_user(test_user, db_session) == 1
    listing = (await db_session.scalars(select(Listing))).one()
    assert listing.contact_phone == "06 14 59 87 04"
    assert listing.agency_name == "IVA IMMOBILIER"
    assert listing.agent_name == "Ethan Naim"
