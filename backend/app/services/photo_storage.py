import io
import uuid
from datetime import timedelta

import httpx
import imagehash
from minio import Minio
from PIL import Image

from app.config import settings


def get_minio_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )


def ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


MIN_PHOTO_DIMENSION = 200


async def download_photo(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                img = Image.open(io.BytesIO(resp.content))
                w, h = img.size
                if w < MIN_PHOTO_DIMENSION or h < MIN_PHOTO_DIMENSION:
                    return None
                return resp.content
    except Exception:
        pass
    return None


def compute_phash(image_bytes: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return str(imagehash.phash(img))
    except Exception:
        return None


def upload_photo(client: Minio, image_bytes: bytes, extension: str = "jpg") -> str:
    s3_key = f"photos/{uuid.uuid4().hex}.{extension}"
    client.put_object(
        settings.minio_bucket,
        s3_key,
        io.BytesIO(image_bytes),
        length=len(image_bytes),
        content_type=f"image/{extension}",
    )
    return s3_key


def get_presigned_url(client: Minio, s3_key: str) -> str:
    return client.presigned_get_object(
        settings.minio_bucket,
        s3_key,
        expires=timedelta(hours=1),
    )
