"""JWT migration compatibility and rejection at both protected entry points."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.api.auth import create_access_token
from app.config import settings


def legacy_token(subject):
    # Independent HS256 encoder matching the previously issued JOSE tokens.
    def segment(value):
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode()
        ).rstrip(b"=")

    body = (
        segment({"alg": "HS256", "typ": "JWT"})
        + b"."
        + segment({"sub": str(subject), "exp": int(time.time()) + 3600})
    )
    signature = hmac.new(settings.jwt_secret.encode(), body, hashlib.sha256).digest()
    return (body + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


async def test_existing_hs256_token_still_authenticates(client, test_user):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {legacy_token(test_user.id)}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == test_user.id


async def test_existing_hs256_photo_token_still_works(client, test_user):
    storage = MagicMock()
    storage.get_object.return_value.read.return_value = b"fixture-photo"
    storage.get_object.return_value.headers = {"Content-Type": "image/jpeg"}
    with patch("app.api.photos.get_minio_client", return_value=storage):
        response = await client.get(
            "/api/v1/photos/photos/fixture.jpg",
            params={"token": legacy_token(test_user.id)},
        )
    assert response.status_code == 200
    assert response.content == b"fixture-photo"
    storage.get_object.return_value.release_conn.assert_called_once()


@pytest.mark.parametrize(
    "case",
    [
        "expired",
        "wrong-key",
        "wrong-algorithm",
        "unsigned",
        "missing-exp",
        "missing-sub",
        "invalid-sub",
        "numeric-sub",
        "invalid-exp",
        "malformed",
    ],
)
async def test_invalid_tokens_rejected_before_storage(client, test_user, case):
    claims = {"sub": str(test_user.id), "exp": int(time.time()) + 3600}
    secret = settings.jwt_secret
    algorithm = "HS256"
    if case == "expired":
        claims["exp"] = int(time.time()) - 60
    elif case == "wrong-key":
        secret = "different-test-only-signing-key-32-bytes"
    elif case == "wrong-algorithm":
        algorithm = "HS384"
    elif case == "unsigned":
        secret, algorithm = "", "none"
    elif case == "missing-exp":
        del claims["exp"]
    elif case == "missing-sub":
        del claims["sub"]
    elif case == "invalid-sub":
        claims["sub"] = "not-a-user-id"
    elif case == "numeric-sub":
        claims["sub"] = test_user.id
    elif case == "invalid-exp":
        claims["exp"] = []
    token = (
        "not.a.jwt"
        if case == "malformed"
        else jwt.encode(claims, secret, algorithm=algorithm)
    )
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    with patch("app.api.photos.get_minio_client") as storage:
        response = await client.get(
            "/api/v1/photos/photos/fixture.jpg", params={"token": token}
        )
    assert response.status_code == 403
    storage.assert_not_called()


def test_new_tokens_require_expiry_and_string_subject():
    token = create_access_token(123)
    claims = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        options={"require": ["exp", "sub"]},
    )
    assert claims["sub"] == "123"
    assert claims["exp"] > time.time()
