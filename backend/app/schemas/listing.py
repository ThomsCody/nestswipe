from pydantic import BaseModel


class PhotoResponse(BaseModel):
    id: int
    s3_key: str
    position: int

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
    photos: list[PhotoResponse]

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
