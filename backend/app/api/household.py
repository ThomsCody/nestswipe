from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import Household, HouseholdInvite, InviteStatus, User
from app.schemas.household import (
    HouseholdMember,
    HouseholdResponse,
    InviteRequest,
    InviteResponse,
)

router = APIRouter()


@router.get("", response_model=HouseholdResponse)
async def get_household(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Household).options(selectinload(Household.members)).where(Household.id == user.household_id)
    )
    household = result.scalar_one()
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        members=[
            HouseholdMember(id=m.id, name=m.name, email=m.email, picture=m.picture)
            for m in household.members
        ],
    )


@router.post("/invite", response_model=InviteResponse)
async def invite(
    body: InviteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.email == user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot invite yourself")

    # Check for existing pending invite
    existing = await db.execute(
        select(HouseholdInvite).where(
            HouseholdInvite.invitee_email == body.email,
            HouseholdInvite.household_id == user.household_id,
            HouseholdInvite.status == InviteStatus.pending,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite already pending")

    # Check if invitee already exists as a user
    invitee_result = await db.execute(select(User).where(User.email == body.email))
    invitee = invitee_result.scalar_one_or_none()

    invite = HouseholdInvite(
        inviter_id=user.id,
        invitee_email=body.email,
        invitee_id=invitee.id if invitee else None,
        household_id=user.household_id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    household = await db.execute(select(Household).where(Household.id == user.household_id))
    h = household.scalar_one()

    return InviteResponse(
        id=invite.id,
        inviter_name=user.name,
        invitee_email=invite.invitee_email,
        household_name=h.name,
        status=invite.status.value,
        created_at=invite.created_at.isoformat(),
    )


@router.get("/invites", response_model=list[InviteResponse])
async def get_invites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HouseholdInvite)
        .where(
            HouseholdInvite.invitee_email == user.email,
            HouseholdInvite.status == InviteStatus.pending,
        )
    )
    invites = result.scalars().all()

    responses = []
    for inv in invites:
        inviter = await db.execute(select(User).where(User.id == inv.inviter_id))
        inviter_user = inviter.scalar_one()
        household = await db.execute(select(Household).where(Household.id == inv.household_id))
        h = household.scalar_one()
        responses.append(InviteResponse(
            id=inv.id,
            inviter_name=inviter_user.name,
            invitee_email=inv.invitee_email,
            household_name=h.name,
            status=inv.status.value,
            created_at=inv.created_at.isoformat(),
        ))
    return responses


@router.get("/invites/sent", response_model=list[InviteResponse])
async def get_sent_invites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HouseholdInvite)
        .where(HouseholdInvite.inviter_id == user.id)
        .order_by(HouseholdInvite.created_at.desc())
    )
    invites = result.scalars().all()

    household = await db.execute(select(Household).where(Household.id == user.household_id))
    h = household.scalar_one()

    return [
        InviteResponse(
            id=inv.id,
            inviter_name=user.name,
            invitee_email=inv.invitee_email,
            household_name=h.name,
            status=inv.status.value,
            created_at=inv.created_at.isoformat(),
        )
        for inv in invites
    ]


@router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HouseholdInvite).where(
            HouseholdInvite.id == invite_id,
            HouseholdInvite.invitee_email == user.email,
            HouseholdInvite.status == InviteStatus.pending,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    # Move user to inviter's household
    old_household_id = user.household_id
    user.household_id = invite.household_id
    invite.status = InviteStatus.accepted
    invite.invitee_id = user.id

    await db.commit()

    # Clean up old empty household
    members_result = await db.execute(select(User).where(User.household_id == old_household_id))
    if not members_result.scalars().first():
        old_h = await db.execute(select(Household).where(Household.id == old_household_id))
        h = old_h.scalar_one_or_none()
        if h:
            await db.delete(h)
            await db.commit()

    return {"status": "ok"}


@router.post("/invites/{invite_id}/decline")
async def decline_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HouseholdInvite).where(
            HouseholdInvite.id == invite_id,
            HouseholdInvite.invitee_email == user.email,
            HouseholdInvite.status == InviteStatus.pending,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    invite.status = InviteStatus.declined
    await db.commit()
    return {"status": "ok"}
