import hashlib
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing, ListingPhoto


def compute_fingerprint(source: str, city: str | None, district: str | None, sqm: float | None, bedrooms: int | None, price: float | None) -> str:
    # Bucket price to nearest 5000 to handle minor price differences
    bucketed_price = str(int(math.floor(price / 5000) * 5000)) if price else "none"
    raw = f"{source}|{city or ''}|{district or ''}|{sqm or ''}|{bedrooms or ''}|{bucketed_price}"
    return hashlib.sha256(raw.encode()).hexdigest()


def hamming_distance(hash1: str, hash2: str) -> int:
    if len(hash1) != len(hash2):
        return 64
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    return bin(val1 ^ val2).count("1")


async def find_duplicate(
    db: AsyncSession,
    household_id: int,
    source: str,
    source_id: str | None,
    external_url: str | None,
    fingerprint: str,
    photo_phashes: list[str],
) -> Listing | None:
    # 1. Source ID match
    if source_id:
        result = await db.execute(
            select(Listing).where(
                Listing.household_id == household_id,
                Listing.source == source,
                Listing.source_id == source_id,
            )
        )
        match = result.scalars().first()
        if match:
            return match

    # 2. URL match
    if external_url:
        normalized = external_url.rstrip("/").split("?")[0]
        result = await db.execute(
            select(Listing).where(
                Listing.household_id == household_id,
                Listing.external_url.ilike(f"%{normalized}%"),
            )
        )
        match = result.scalars().first()
        if match:
            return match

    # 3. Fingerprint match
    result = await db.execute(
        select(Listing).where(
            Listing.household_id == household_id,
            Listing.fingerprint == fingerprint,
        )
    )
    match = result.scalars().first()
    if match:
        return match

    # 4. Photo phash match — need 3+ photos with hamming distance ≤ 5
    if len(photo_phashes) >= 3:
        result = await db.execute(
            select(Listing).where(Listing.household_id == household_id)
        )
        candidates = result.scalars().all()
        for candidate in candidates:
            photos_result = await db.execute(
                select(ListingPhoto).where(ListingPhoto.listing_id == candidate.id)
            )
            existing_photos = photos_result.scalars().all()
            existing_phashes = [p.phash for p in existing_photos if p.phash]
            if not existing_phashes:
                continue

            matching = 0
            for new_hash in photo_phashes:
                for existing_hash in existing_phashes:
                    if hamming_distance(new_hash, existing_hash) <= 5:
                        matching += 1
                        break
            if matching >= 3:
                return candidate

    return None
