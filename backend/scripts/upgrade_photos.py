"""One-off script to re-download low-res SeLoger photos at higher resolution.

Run inside the backend container:
    python scripts/upgrade_photos.py
"""

import asyncio
import io
import logging
import re
import sys

from PIL import Image
from sqlalchemy import select, text

from app.database import engine, async_session
from app.models.listing import ListingPhoto
from app.services.photo_storage import download_photo, get_minio_client, upload_photo, ensure_bucket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def normalize_seloger_url(url: str) -> str:
    """Replace SeLoger crop/width path with high-res variant."""
    url = re.sub(r"/s/crop/\d+x\d+/", "/s/width/1280/", url)
    url = re.sub(r"/s/width/\d+/", "/s/width/1280/", url)
    return url


async def main():
    minio_client = get_minio_client()
    ensure_bucket(minio_client)

    async with async_session() as db:
        result = await db.execute(
            select(ListingPhoto).where(ListingPhoto.original_url.like("%/s/crop/%"))
        )
        photos = result.scalars().all()
        logger.info("Found %d low-res photos to upgrade", len(photos))

        upgraded = 0
        failed = 0
        for photo in photos:
            new_url = normalize_seloger_url(photo.original_url)
            img_bytes = await download_photo(new_url)
            if not img_bytes:
                logger.warning("Failed to download: %s", new_url)
                failed += 1
                continue

            # Check dimensions
            img = Image.open(io.BytesIO(img_bytes))
            w, h = img.size

            # Upload new image, replace s3_key
            old_key = photo.s3_key
            new_key = upload_photo(minio_client, img_bytes)
            photo.s3_key = new_key
            photo.original_url = new_url

            # Delete old object
            try:
                minio_client.remove_object("listing-photos", old_key)
            except Exception:
                pass

            upgraded += 1
            if upgraded % 20 == 0:
                logger.info("Progress: %d/%d upgraded", upgraded, len(photos))
                await db.commit()

        await db.commit()
        logger.info("Done: %d upgraded, %d failed out of %d total", upgraded, failed, len(photos))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
