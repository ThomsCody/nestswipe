from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.settings import SettingsResponse, SettingsUpdate

router = APIRouter()


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "..." + key[-4:]


@router.get("", response_model=SettingsResponse)
async def get_settings(user: User = Depends(get_current_user)):
    return SettingsResponse(
        openai_api_key_set=bool(user.openai_api_key),
        openai_api_key_masked=_mask_key(user.openai_api_key),
        gmail_connected=bool(user.gmail_refresh_token),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.openai_api_key is not None:
        user.openai_api_key = body.openai_api_key if body.openai_api_key else None
    await db.commit()
    await db.refresh(user)
    return SettingsResponse(
        openai_api_key_set=bool(user.openai_api_key),
        openai_api_key_masked=_mask_key(user.openai_api_key),
        gmail_connected=bool(user.gmail_refresh_token),
    )
