from pydantic import BaseModel


class PhotoResponse(BaseModel):
    id: int
    s3_key: str
    position: int

    model_config = {"from_attributes": True}


class PriceHistoryItem(BaseModel):
    price: float
    observed_at: str

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: int
    source: str
    title: str
    description: str | None
    price: float | None
    sqm: float | None
    price_per_sqm: float | None
    bedrooms: int | None
    rooms: int | None = None
    floor: int | None = None
    city: str | None
    district: str | None
    location_detail: str | None
    external_url: str | None
    contact_phone: str | None = None
    agency_name: str | None = None
    agent_name: str | None = None
    photos: list[PhotoResponse]
    price_history: list[PriceHistoryItem] = []
    last_seen_at: str | None = None

    model_config = {"from_attributes": True}


class QueueResponse(BaseModel):
    listings: list[ListingResponse]
    remaining: int


class SwipeRequest(BaseModel):
    action: str  # "like" or "pass"


class ArchiveListItem(BaseModel):
    listing: ListingResponse
    passed_at: str


class ArchivesListResponse(BaseModel):
    archives: list[ArchiveListItem]
    total: int


class ArchiveDetailResponse(BaseModel):
    listing: ListingResponse
    price_history: list[PriceHistoryItem]
    passed_at: str


class ImportUrlRequest(BaseModel):
    url: str


class ImportUrlResponse(BaseModel):
    favorite_id: int
    listing: ListingResponse
    created: bool
    already_favorited: bool
