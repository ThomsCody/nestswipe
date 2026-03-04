import hashlib
import math

import pytest
from sqlalchemy import select

from app.models.listing import Listing, ListingPhoto
from app.models.user import Household, User
from app.services.duplicate_detector import compute_fingerprint, find_duplicate, hamming_distance


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    def test_deterministic_for_same_inputs(self):
        fp1 = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)
        fp2 = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex digest length

    def test_returns_sha256_hex(self):
        fp = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)

        # Recompute manually to confirm the exact algorithm
        bucketed_price = str(int(math.floor(450000.0 / 5000) * 5000))
        raw = f"seloger|Paris|Marais|60.0|2|{bucketed_price}"
        expected = hashlib.sha256(raw.encode()).hexdigest()

        assert fp == expected

    def test_buckets_price_to_nearest_5000(self):
        fp_502k = compute_fingerprint("seloger", "Paris", None, 60.0, 2, 502000.0)
        fp_500k = compute_fingerprint("seloger", "Paris", None, 60.0, 2, 500000.0)
        fp_504k = compute_fingerprint("seloger", "Paris", None, 60.0, 2, 504999.0)

        # 502000 and 504999 both bucket to 500000 (floor to nearest 5000)
        assert fp_502k == fp_500k
        assert fp_504k == fp_500k

    def test_buckets_price_boundary(self):
        """505000 buckets to 505000, distinct from 500000."""
        fp_505k = compute_fingerprint("seloger", "Paris", None, 60.0, 2, 505000.0)
        fp_500k = compute_fingerprint("seloger", "Paris", None, 60.0, 2, 500000.0)

        assert fp_505k != fp_500k

    def test_differs_with_different_inputs(self):
        fp_paris = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)
        fp_lyon = compute_fingerprint("seloger", "Lyon", "Marais", 60.0, 2, 450000.0)
        fp_bigger = compute_fingerprint("seloger", "Paris", "Marais", 80.0, 3, 450000.0)

        assert fp_paris != fp_lyon
        assert fp_paris != fp_bigger

    def test_handles_none_values(self):
        fp = compute_fingerprint("seloger", None, None, None, None, None)

        # None price becomes "none", other None fields become empty string
        # Format: source|city|district|sqm|bedrooms|bucketed_price
        raw = "seloger|||||none"
        expected = hashlib.sha256(raw.encode()).hexdigest()

        assert fp == expected


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------


class TestHammingDistance:
    def test_identical_hashes_return_zero(self):
        h = "abcdef1234567890" * 4  # 64-char hex string

        assert hamming_distance(h, h) == 0

    def test_known_different_hashes(self):
        # XOR of 0x0 and 0x1 = 0x1 which has 1 bit set
        h1 = "0" * 64
        h2 = "0" * 63 + "1"

        assert hamming_distance(h1, h2) == 1

    def test_all_bits_different(self):
        h1 = "0" * 64
        h2 = "f" * 64

        # 64 hex chars = 256 bits, 0 XOR f = 0xf = 4 bits per char
        assert hamming_distance(h1, h2) == 256

    def test_different_lengths_returns_64(self):
        assert hamming_distance("abc", "abcdef") == 64
        assert hamming_distance("", "abc") == 64


# ---------------------------------------------------------------------------
# find_duplicate (async, needs DB fixtures)
# ---------------------------------------------------------------------------


@pytest.fixture
async def listing_with_photo(db_session, test_user):
    """Create a listing with a photo and fingerprint in the DB."""
    fingerprint = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)
    listing = Listing(
        household_id=test_user.household_id,
        user_id=test_user.id,
        source="seloger",
        source_id="987654",
        external_url="https://www.seloger.com/annonces/achat/appartement/paris/987654.htm",
        title="Bel Appartement Marais",
        price=450000,
        sqm=60,
        price_per_sqm=7500,
        bedrooms=2,
        city="Paris",
        district="Marais",
        fingerprint=fingerprint,
    )
    db_session.add(listing)
    await db_session.flush()

    photo = ListingPhoto(
        listing_id=listing.id,
        s3_key="photos/test-dup.jpg",
        original_url="https://mms.seloger.com/photo-dup.jpg",
        phash="abcdef1234567890",
        position=0,
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing


class TestFindDuplicate:
    async def test_matching_source_id_returns_existing(self, db_session, test_user, listing_with_photo):
        result = await find_duplicate(
            db=db_session,
            user_id=test_user.id,
            source="seloger",
            source_id="987654",
            external_url=None,
            fingerprint="completely-different-fingerprint",
            photo_phashes=[],
        )

        assert result is not None
        assert result.id == listing_with_photo.id

    async def test_matching_fingerprint_returns_existing(self, db_session, test_user, listing_with_photo):
        expected_fingerprint = compute_fingerprint("seloger", "Paris", "Marais", 60.0, 2, 450000.0)

        result = await find_duplicate(
            db=db_session,
            user_id=test_user.id,
            source="seloger",
            source_id="different-id",
            external_url=None,
            fingerprint=expected_fingerprint,
            photo_phashes=[],
        )

        assert result is not None
        assert result.id == listing_with_photo.id

    async def test_matching_url_returns_existing(self, db_session, test_user, listing_with_photo):
        result = await find_duplicate(
            db=db_session,
            user_id=test_user.id,
            source="seloger",
            source_id="no-match",
            external_url="https://www.seloger.com/annonces/achat/appartement/paris/987654.htm",
            fingerprint="no-match-fp",
            photo_phashes=[],
        )

        assert result is not None
        assert result.id == listing_with_photo.id

    async def test_no_match_returns_none(self, db_session, test_user, listing_with_photo):
        result = await find_duplicate(
            db=db_session,
            user_id=test_user.id,
            source="pap",
            source_id="nonexistent-id",
            external_url="https://www.pap.fr/annonces/different",
            fingerprint="totally-different-fingerprint",
            photo_phashes=[],
        )

        assert result is None

    async def test_no_match_different_user(self, db_session, test_user, listing_with_photo):
        """A listing owned by a different user should not be found."""
        result = await find_duplicate(
            db=db_session,
            user_id=test_user.id + 999,
            source="seloger",
            source_id="987654",
            external_url=None,
            fingerprint=listing_with_photo.fingerprint,
            photo_phashes=[],
        )

        assert result is None
