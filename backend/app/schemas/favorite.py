from pydantic import BaseModel

from app.schemas.listing import ListingResponse


class CommentResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    body: str
    created_at: str

    model_config = {"from_attributes": True}


class FavoriteListItem(BaseModel):
    id: int
    listing: ListingResponse
    comment_count: int
    has_visit_date: bool
    created_at: str

    model_config = {"from_attributes": True}


class FavoriteDetailResponse(BaseModel):
    id: int
    listing: ListingResponse
    comments: list[CommentResponse]
    price_history: list[dict]
    visit_date: str | None
    location: str | None
    seller_name: str | None
    seller_phone: str | None
    seller_is_agency: bool | None
    created_at: str

    model_config = {"from_attributes": True}


class FavoriteUpdateRequest(BaseModel):
    visit_date: str | None = None
    location: str | None = None
    seller_name: str | None = None
    seller_phone: str | None = None
    seller_is_agency: bool | None = None


class CommentCreateRequest(BaseModel):
    body: str


class FavoritesListResponse(BaseModel):
    favorites: list[FavoriteListItem]
    total: int
