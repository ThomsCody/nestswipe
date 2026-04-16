"""Daily job: remove photos from stale listings to reclaim storage.

Listings not updated in STALE_THRESHOLD (3 weeks) that are NOT in any
household's favorites have their MinIO objects deleted and replaced by a
single lightweight placeholder image.
"""

import io
import logging
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.interaction import Favorite
from app.models.listing import Listing, ListingPhoto
from app.services.photo_storage import ensure_bucket, get_minio_client

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(weeks=3)
PLACEHOLDER_S3_KEY = "photos/_placeholder.jpg"


def _generate_placeholder() -> bytes:
    """Create a simple grey placeholder image with centred text."""
    width, height = 600, 400
    img = Image.new("RGB", (width, height), color=(220, 220, 220))
    draw = ImageDraw.Draw(img)

    text = "Photo no longer available"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default(size=22)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((width - text_w) / 2, (height - text_h) / 2),
        text,
        fill=(120, 120, 120),
        font=font,
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _ensure_placeholder(minio_client) -> str:
    """Upload the placeholder once if it doesn't already exist."""
    try:
        minio_client.stat_object(settings.minio_bucket, PLACEHOLDER_S3_KEY)
    except Exception:
        placeholder_bytes = _generate_placeholder()
        minio_client.put_object(
            settings.minio_bucket,
            PLACEHOLDER_S3_KEY,
            io.BytesIO(placeholder_bytes),
            length=len(placeholder_bytes),
            content_type="image/jpeg",
        )
        logger.info("Uploaded placeholder image to %s", PLACEHOLDER_S3_KEY)
    return PLACEHOLDER_S3_KEY


async def cleanup_stale_photos() -> int:
    """Delete photos for stale, non-favorited listings. Returns count of cleaned listings."""
    cutoff = datetime.now(timezone.utc) - STALE_THRESHOLD
    minio_client = get_minio_client()
    ensure_bucket(minio_client)
    placeholder_key = _ensure_placeholder(minio_client)

    cleaned = 0
    async with async_session() as db:
        # Listings that are still someone's favorite should keep their photos
        fav_listing_ids = select(Favorite.listing_id)

        result = await db.execute(
            select(Listing)
            .where(
                Listing.last_seen_at < cutoff,
                Listing.id.notin_(fav_listing_ids),
            )
            .options(selectinload(Listing.photos))
        )
        stale_listings = result.scalars().unique().all()

        for listing in stale_listings:
            # Already cleaned?
            if (
                len(listing.photos) == 1
                and listing.photos[0].s3_key == placeholder_key
            ):
                continue

            # Collect keys before mutating the relationship
            old_photos = list(listing.photos)
            s3_keys = [p.s3_key for p in old_photos if p.s3_key != placeholder_key]

            # Remove all photo rows
            for photo in old_photos:
                await db.delete(photo)
            await db.flush()

            # Delete original photos from MinIO
            for key in s3_keys:
                try:
                    minio_client.remove_object(settings.minio_bucket, key)
                except Exception:
                    logger.warning("Failed to delete %s from MinIO", key)

            # Insert single placeholder row
            db.add(ListingPhoto(
                listing_id=listing.id,
                s3_key=placeholder_key,
                original_url=None,
                phash=None,
                position=0,
            ))
            cleaned += 1

            # Commit per listing so progress isn't lost on failure
            await db.commit()

        logger.info("Photo cleanup: cleaned %d stale listing(s)", cleaned)
    return cleaned
