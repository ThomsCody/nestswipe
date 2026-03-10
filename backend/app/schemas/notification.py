from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    comment_body: str
    commenter_name: str
    favorite_id: int
    listing_title: str
    created_at: str
    is_read: bool

    model_config = {"from_attributes": True}


class NotificationCountResponse(BaseModel):
    unread: int
