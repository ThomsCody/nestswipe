#!/usr/bin/env python3
"""Local-only OpenDAL/Garage regression; use a disposable Garage installation."""

import asyncio
import hashlib
import json
import time
import uuid

import httpx
import jwt

from app.api.photos import get_photo
from app.config import settings
from app.services.photo_storage import get_storage, get_presigned_url, upload_photo


async def main():
    storage = get_storage()
    prefix = f"sdk-rehearsal/{uuid.uuid4().hex}/"
    fixtures = {
        "empty.jpg": b"",
        "spaces and unicode-é.jpg": b"image",
        "multipart.jpg": bytes(range(256)) * 40000,
    }
    written = []
    try:
        for name, content in fixtures.items():
            key = prefix + name
            written.append(key)
            storage.write(
                key,
                content,
                content_type="image/jpeg",
                user_metadata={"origin": "rehearsal"},
            )
            stat = storage.stat(key)
            assert stat.content_type == "image/jpeg"
            assert stat.user_metadata == {"origin": "rehearsal"}
            assert (
                hashlib.sha256(storage.read(key)).digest()
                == hashlib.sha256(content).digest()
            )
        token = jwt.encode(
            {"sub": "1", "exp": int(time.time()) + 300},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        key = prefix + "spaces and unicode-é.jpg"
        response = await get_photo(key, token)
        assert response.body == b"image"
        assert response.media_type == "image/jpeg"
        url = await get_presigned_url(storage, key)
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            assert response.status_code == 200 and response.content == b"image"
        key = upload_photo(storage, b"upload-test")
        written.append(key)
        assert storage.read(key) == b"upload-test"
    finally:
        for key in written:
            storage.delete(key)
            assert not storage.exists(key)
    print(
        json.dumps(
            {
                "roundtrip": "pass",
                "metadata": "pass",
                "presign": "pass",
                "authenticated_photo": "pass",
                "upload_delete": "pass",
                "objects": len(fixtures),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
