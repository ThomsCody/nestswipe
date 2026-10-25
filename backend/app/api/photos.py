from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
import jwt

from app.config import settings
from app.services.photo_storage import get_minio_client

router = APIRouter()


@router.get("/{s3_key:path}")
async def get_photo(s3_key: str, token: str = Query()):
    """Serve photos using a token query param (since <img> tags can't send Authorization headers)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        if int(payload["sub"]) <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
            )
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        )

    client = get_minio_client()
    response = client.get_object(settings.minio_bucket, s3_key)
    data = response.read()
    response.close()
    response.release_conn()

    content_type = response.headers.get("Content-Type", "image/jpeg")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
