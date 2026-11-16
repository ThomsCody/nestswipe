#!/usr/bin/env python3
"""Exercise a disposable MinIO/Garage pair, never production endpoints."""

import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import AsyncMock, patch

import jwt
from minio import Minio
import requests

from app.config import settings
from app.services.photo_storage import (
    ensure_bucket,
    get_minio_client,
    get_presigned_url,
    upload_photo,
)
from app.api.photos import get_photo

spec = importlib.util.spec_from_file_location("migration", "/migration/migrate.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
source = Minio(
    "garage-rehearsal-minio:9000",
    "test-access-key",
    "test-secret-key-long",
    secure=False,
)
settings.minio_endpoint = "garage:3900"
settings.minio_root_user = (
    Path("/run/garage-secrets/garage_access_key").read_text().strip()
)
settings.minio_root_password = (
    Path("/run/garage-secrets/garage_secret_key").read_text().strip()
)
settings.jwt_secret = "local-rehearsal-signing-key-at-least-32-bytes"
settings.minio_region = "garage"
settings.minio_bucket = "listing-photos"
target = get_minio_client()
ensure_bucket(target)
if not source.bucket_exists(settings.minio_bucket):
    source.make_bucket(settings.minio_bucket)
fixtures = {
    "photos/_placeholder.jpg": b"placeholder",
    "photos/spaces and unicode-é.png": b"png-fixture",
    "photos/empty.jpg": b"",
    "photos/multipart.jpg": bytes(range(256)) * 25000,
}
for key, content in fixtures.items():
    source.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(content),
        len(content),
        content_type="image/jpeg",
        metadata={
            "x-amz-meta-origin": "rehearsal",
            "Cache-Control": "private, max-age=3600",
        },
    )
# Persist photo references through the storage-only migration and rollback.
db = sqlite3.connect("/evidence/references.sqlite")
db.execute("CREATE TABLE IF NOT EXISTS listing_photos (s3_key TEXT PRIMARY KEY)")
db.executemany(
    "INSERT OR IGNORE INTO listing_photos VALUES (?)", ((key,) for key in fixtures)
)
db.commit()
for verify in (False, True):
    migration.migrate(source, target, Path("/evidence/local-manifest.json"), verify)
for (key,) in db.execute("SELECT s3_key FROM listing_photos"):
    assert target.stat_object(settings.minio_bucket, key).size == len(fixtures[key])
    assert source.stat_object(settings.minio_bucket, key).size == len(fixtures[key])
# Existing URL route, authenticated response, preserved MIME type.
token = jwt.encode(
    {"sub": "1", "exp": int(time.time()) + 300},
    settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
)
response = asyncio.run(get_photo("photos/_placeholder.jpg", token))
assert response.body == fixtures["photos/_placeholder.jpg"]
assert response.media_type == "image/jpeg"
url = get_presigned_url(target, "photos/_placeholder.jpg")
assert requests.get(url, timeout=10).content == response.body
key = upload_photo(target, b"new-upload")
assert target.get_object(settings.minio_bucket, key).read() == b"new-upload"
target.remove_object(settings.minio_bucket, key)
# Fail closed on corrupted destination, then recover by recopying.
target.put_object(
    settings.minio_bucket, "photos/_placeholder.jpg", io.BytesIO(b"bad"), 3
)
try:
    migration.migrate(source, target, Path("/evidence/should-not-exist.json"), True)
except RuntimeError:
    pass
else:
    raise AssertionError("Corruption was not detected")
migration.migrate(source, target, Path("/evidence/local-manifest.json"))
# Rollback: switch the same application client back to original MinIO.
settings.minio_endpoint = "garage-rehearsal-minio:9000"
settings.minio_root_user = "test-access-key"
settings.minio_root_password = "test-secret-key-long"
settings.minio_region = "us-east-1"
assert (
    asyncio.run(get_photo("photos/_placeholder.jpg", token)).body
    == fixtures["photos/_placeholder.jpg"]
)
from app.main import app, lifespan

settings.scheduler_enabled = False


async def paused_start():
    with (
        patch("app.scheduler.start_scheduler", new_callable=AsyncMock) as start,
        patch("app.scheduler.stop_scheduler") as stop,
    ):
        async with lifespan(app):
            pass
        start.assert_not_called()
        stop.assert_not_called()


asyncio.run(paused_start())
print(
    json.dumps(
        {
            "migration": "pass",
            "multipart": "pass",
            "metadata": "pass",
            "db_references": len(fixtures),
            "photo_route": "pass",
            "presign": "pass",
            "upload_delete": "pass",
            "corruption_detection": "pass",
            "rollback": "pass",
            "scheduler_paused": "pass",
        }
    )
)
