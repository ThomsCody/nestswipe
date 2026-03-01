from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    picture: str | None
    household_id: int
    has_api_key: bool
    has_gmail_token: bool

    model_config = {"from_attributes": True}
