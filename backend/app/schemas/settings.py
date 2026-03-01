from pydantic import BaseModel


class SettingsResponse(BaseModel):
    openai_api_key_set: bool
    openai_api_key_masked: str | None
    gmail_connected: bool


class SettingsUpdate(BaseModel):
    openai_api_key: str | None = None
