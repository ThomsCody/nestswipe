from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.interaction import Favorite, SwipeAction, SwipeDirection
from app.models.listing import Listing, ListingPhoto
from app.models.user import Household, User
from app.services.photo_cleanup import (
    PLACEHOLDER_S3_KEY,
    STALE_THRESHOLD,
    cleanup_stale_photos,
)

NOW = datetime.now(timezone.utc)
STALE_DATE = NOW - STALE_THRESHOLD - timedelta(days=1)
FRESH_DATE = NOW - timedelta(days=1)


@pytest_asyncio.fixture
async def household(db_session):
    h = Household(name="H1")
    db_session.add(h)
    await db_session.flush()
    return h


@pytest_asyncio.fixture
async def user(db_session, household):
    u = User(
        google_id="g1",
        email="u@test.com",
        name="U",
        household_id=household.id,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


def _make_listing(user, last_seen_at, title="Listing"):
    return Listing(
        household_id=user.household_id,
        user_id=user.id,
        source="test",
        title=title,
        last_seen_at=last_seen_at,
    )


def _make_photos(listing_id, count=3):
    return [
        ListingPhoto(
            listing_id=listing_id,
            s3_key=f"photos/{listing_id}_{i}.jpg",
            position=i,
        )
        for i in range(count)
    ]


def _mock_minio():
    client = MagicMock()
    client.stat_object.return_value = True  # placeholder exists
    return client


@pytest.fixture
def mock_minio():
    client = _mock_minio()
    with (
        patch("app.services.photo_cleanup.get_minio_client", return_value=client),
        patch("app.services.photo_cleanup.ensure_bucket"),
    ):
        yield client


@pytest.fixture
def mock_session(db_session):
    """Patch async_session to return the test db_session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield db_session

    with patch("app.services.photo_cleanup.async_session", _session):
        yield


# ── Tests ────────────────────────────────────────────────────────────────


async def test_stale_listing_photos_deleted_from_storage(
    db_session, user, mock_minio, mock_session
):
    """Photos of stale non-favorited listings are removed from MinIO."""
    listing = _make_listing(user, STALE_DATE)
    db_session.add(listing)
    await db_session.flush()
    photos = _make_photos(listing.id)
    db_session.add_all(photos)
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 1
    removed_keys = [
        call.args[1] for call in mock_minio.remove_object.call_args_list
    ]
    assert sorted(removed_keys) == sorted(
        f"photos/{listing.id}_{i}.jpg" for i in range(3)
    )


async def test_stale_listing_gets_placeholder(
    db_session, user, mock_minio, mock_session
):
    """After cleanup a stale listing has exactly one placeholder photo row."""
    listing = _make_listing(user, STALE_DATE)
    db_session.add(listing)
    await db_session.flush()
    db_session.add_all(_make_photos(listing.id))
    await db_session.commit()

    await cleanup_stale_photos()

    rows = (
        await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].s3_key == PLACEHOLDER_S3_KEY
    assert rows[0].position == 0


async def test_fresh_listing_untouched(
    db_session, user, mock_minio, mock_session
):
    """Listings seen recently keep their photos."""
    listing = _make_listing(user, FRESH_DATE, title="Fresh")
    db_session.add(listing)
    await db_session.flush()
    db_session.add_all(_make_photos(listing.id, count=2))
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 0
    mock_minio.remove_object.assert_not_called()
    count = len(
        (
            await db_session.execute(
                select(ListingPhoto).where(
                    ListingPhoto.listing_id == listing.id
                )
            )
        ).scalars().all()
    )
    assert count == 2


async def test_favorited_listing_untouched(
    db_session, user, mock_minio, mock_session
):
    """Stale listings that are favorites are not cleaned."""
    listing = _make_listing(user, STALE_DATE, title="Fav")
    db_session.add(listing)
    await db_session.flush()
    db_session.add_all(_make_photos(listing.id))
    db_session.add(
        Favorite(household_id=user.household_id, listing_id=listing.id)
    )
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 0
    mock_minio.remove_object.assert_not_called()


async def test_idempotent(db_session, user, mock_minio, mock_session):
    """Running cleanup twice does not re-process already-cleaned listings."""
    listing = _make_listing(user, STALE_DATE)
    db_session.add(listing)
    await db_session.flush()
    db_session.add_all(_make_photos(listing.id))
    await db_session.commit()

    assert await cleanup_stale_photos() == 1
    mock_minio.remove_object.reset_mock()

    # Expire cached relationship state so the second run sees the placeholder
    db_session.expire_all()

    assert await cleanup_stale_photos() == 0
    mock_minio.remove_object.assert_not_called()


async def test_listing_with_no_photos_gets_placeholder(
    db_session, user, mock_minio, mock_session
):
    """Stale listings that somehow lost all photos still get a placeholder."""
    listing = _make_listing(user, STALE_DATE, title="No photos")
    db_session.add(listing)
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 1
    rows = (
        await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].s3_key == PLACEHOLDER_S3_KEY


async def test_minio_failure_does_not_block(
    db_session, user, mock_minio, mock_session
):
    """If MinIO delete fails, DB cleanup still proceeds."""
    mock_minio.remove_object.side_effect = Exception("connection refused")

    listing = _make_listing(user, STALE_DATE)
    db_session.add(listing)
    await db_session.flush()
    db_session.add_all(_make_photos(listing.id))
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 1
    rows = (
        await db_session.execute(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].s3_key == PLACEHOLDER_S3_KEY


async def test_mixed_stale_and_fresh(
    db_session, user, mock_minio, mock_session
):
    """Only stale non-favorited listings are cleaned in a mixed batch."""
    stale = _make_listing(user, STALE_DATE, title="Stale")
    fresh = _make_listing(user, FRESH_DATE, title="Fresh")
    stale_fav = _make_listing(user, STALE_DATE, title="Stale Fav")
    db_session.add_all([stale, fresh, stale_fav])
    await db_session.flush()
    db_session.add_all(_make_photos(stale.id, count=5))
    db_session.add_all(_make_photos(fresh.id, count=3))
    db_session.add_all(_make_photos(stale_fav.id, count=4))
    db_session.add(
        Favorite(household_id=user.household_id, listing_id=stale_fav.id)
    )
    await db_session.commit()

    cleaned = await cleanup_stale_photos()

    assert cleaned == 1  # only stale (non-fav)
    assert mock_minio.remove_object.call_count == 5  # stale had 5 photos

    # Fresh untouched
    fresh_count = len(
        (
            await db_session.execute(
                select(ListingPhoto).where(
                    ListingPhoto.listing_id == fresh.id
                )
            )
        ).scalars().all()
    )
    assert fresh_count == 3

    # Stale fav untouched
    fav_count = len(
        (
            await db_session.execute(
                select(ListingPhoto).where(
                    ListingPhoto.listing_id == stale_fav.id
                )
            )
        ).scalars().all()
    )
    assert fav_count == 4
