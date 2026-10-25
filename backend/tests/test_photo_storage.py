"""Synthetic pre-upgrade fixtures guard image decoding and stored photo hashes."""

import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.services import photo_storage

FIXTURES = Path(__file__).parent / "fixtures" / "security-images"
HASHES = json.loads((FIXTURES / "hashes.json").read_text())


@pytest.mark.parametrize("filename,expected", HASHES.items())
def test_existing_photo_hashes_are_stable(filename, expected):
    assert photo_storage.compute_phash((FIXTURES / filename).read_bytes()) == expected


@pytest.mark.parametrize("filename", HASHES)
async def test_supported_listing_photo_is_downloaded(monkeypatch, filename):
    content = (FIXTURES / filename).read_bytes()
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=content, headers={"Content-Type": "image/jpeg"}
        )
    )
    monkeypatch.setattr(
        photo_storage.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=transport, **kwargs),
    )
    assert (
        await photo_storage.download_photo("https://images.example.test/photo")
        == content
    )


@pytest.mark.parametrize("small", [False, True])
async def test_corrupt_and_tiny_photos_are_rejected(monkeypatch, small):
    content = b"not-a-valid-image"
    if small:
        output = io.BytesIO()
        Image.new("RGB", (10, 10)).save(output, format="PNG")
        content = output.getvalue()
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=content, headers={"Content-Type": "image/png"}
        )
    )
    monkeypatch.setattr(
        photo_storage.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=transport, **kwargs),
    )
    assert (
        await photo_storage.download_photo("https://images.example.test/photo") is None
    )
