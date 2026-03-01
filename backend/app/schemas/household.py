from pydantic import BaseModel


class HouseholdMember(BaseModel):
    id: int
    name: str
    email: str
    picture: str | None

    model_config = {"from_attributes": True}


class HouseholdResponse(BaseModel):
    id: int
    name: str
    members: list[HouseholdMember]


class InviteRequest(BaseModel):
    email: str


class InviteResponse(BaseModel):
    id: int
    inviter_name: str
    invitee_email: str
    household_name: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}
