from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.listing import ListingResponse


class CommentResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    body: str
    created_at: str

    model_config = {"from_attributes": True}


class FavoriteOwner(BaseModel):
    id: int
    name: str
    picture: str | None

    model_config = {"from_attributes": True}


class FavoriteListItem(BaseModel):
    id: int
    listing: ListingResponse
    comment_count: int
    has_visit_date: bool
    status: str
    owner: FavoriteOwner | None
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
    status: str
    owner: FavoriteOwner | None
    created_at: str
    offer_price: Decimal | None = None
    renovation_budget: Decimal | None = None

    @field_serializer("offer_price", "renovation_budget")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return format(value, ".2f") if value is not None else None

    model_config = {"from_attributes": True}


class FavoriteUpdateRequest(BaseModel):
    visit_date: str | None = None
    location: str | None = None
    seller_name: str | None = None
    seller_phone: str | None = None
    seller_is_agency: bool | None = None
    status: str | None = None
    owner_id: int | None = None
    offer_price: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    renovation_budget: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )


class CommentCreateRequest(BaseModel):
    body: str


class FavoritesListResponse(BaseModel):
    favorites: list[FavoriteListItem]
    total: int
