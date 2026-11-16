from functools import lru_cache
import json
from pathlib import Path

import io
import logging
import uuid
import opendal

import httpx
import imagehash
from PIL import Image

from app.config import settings


logger = logging.getLogger(__name__)


def get_storage() -> opendal.Operator:
    if settings.storage_backend not in {"s3", "fs", "memory", "gcs", "azblob"}:
        raise ValueError("Unsupported storage backend")
    options = {}
    if settings.storage_options_file:
        try:
            options = json.loads(Path(settings.storage_options_file).read_text())
            if not isinstance(options, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in options.items()
            ):
                raise ValueError()
        except (OSError, ValueError):
            raise RuntimeError("Cannot read storage options file") from None
    options["root"] = settings.storage_root
    if settings.storage_backend == "s3":
        scheme = "https" if settings.storage_secure else "http"
        options.update(
            endpoint=f"{scheme}://{settings.storage_endpoint}",
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            access_key_id=settings.storage_access_key,
            secret_access_key=settings.storage_secret_key,
            disable_config_load="true",
            disable_ec2_metadata="true",
        )
    return _operator(settings.storage_backend, tuple(sorted(options.items())))


@lru_cache(maxsize=4)
def _operator(backend: str, options: tuple[tuple[str, str], ...]) -> opendal.Operator:
    try:
        operator = opendal.Operator(backend, **dict(options))
        capabilities = operator.capability()
        if not all(
            getattr(capabilities, name)
            for name in ("read", "write", "stat", "delete", "list")
        ):
            raise ValueError()
        return operator
    except Exception:
        # Provider exceptions can include configuration; never echo credentials.
        raise RuntimeError(
            "Storage backend configuration is invalid or lacks required operations"
        ) from None


def ensure_storage(storage: opendal.Operator) -> None:
    # The deployment provisions storage and permissions; requests only check access.
    storage.check()


MIN_PHOTO_DIMENSION = 200


async def download_photo(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200 and resp.headers.get(
                "content-type", ""
            ).startswith("image"):
                img = Image.open(io.BytesIO(resp.content))
                w, h = img.size
                if w < MIN_PHOTO_DIMENSION or h < MIN_PHOTO_DIMENSION:
                    return None
                return resp.content
    except Exception as exc:
        logger.warning("Photo download failed: error_type=%s", type(exc).__name__)
    return None


def compute_phash(image_bytes: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return str(imagehash.phash(img))
    except Exception:
        return None


def upload_photo(
    storage: opendal.Operator, image_bytes: bytes, extension: str = "jpg"
) -> str:
    key = f"photos/{uuid.uuid4().hex}.{extension}"
    storage.write(key, image_bytes, content_type=f"image/{extension}")
    return key


async def get_presigned_url(storage: opendal.Operator, key: str) -> str:
    request = await storage.to_async_operator().presign_read(key, 3600)
    return request.url
