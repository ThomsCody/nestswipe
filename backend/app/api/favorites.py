import re
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.interaction import Comment, Favorite, FavoriteStatus
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.user import Household, User
from app.services.email import send_assignment_email
from app.schemas.favorite import (
    CommentCreateRequest,
    CommentResponse,
    FavoriteDetailResponse,
    FavoriteListItem,
    FavoriteOwner,
    FavoritesListResponse,
    FavoriteUpdateRequest,
)
from app.schemas.listing import ListingResponse, PhotoResponse, PriceHistoryItem
from app.services.email import send_mention_email

router = APIRouter()


def _listing_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        source=listing.source,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        sqm=listing.sqm,
        price_per_sqm=listing.price_per_sqm,
        bedrooms=listing.bedrooms,
        rooms=listing.rooms,
        floor=listing.floor,
        city=listing.city,
        district=listing.district,
        location_detail=listing.location_detail,
        external_url=listing.external_url,
        contact_phone=listing.contact_phone,
        agency_name=listing.agency_name,
        agent_name=listing.agent_name,
        photos=[PhotoResponse.model_validate(p) for p in sorted(listing.photos, key=lambda p: p.position)],
        price_history=[
            PriceHistoryItem(price=ph.price, observed_at=ph.observed_at.isoformat())
            for ph in sorted(listing.price_history, key=lambda ph: ph.observed_at)
        ],
        last_seen_at=listing.last_seen_at.isoformat() if listing.last_seen_at else None,
    )


@router.get("", response_model=FavoritesListResponse)
async def get_favorites(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=200),
    sort: str = Query(default="newest"),
    owner_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base_query = select(Favorite).where(Favorite.household_id == user.household_id)
    if owner_id is not None:
        base_query = base_query.where(Favorite.owner_id == owner_id)

    # Count
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0

    # Sort
    order = Favorite.created_at.desc() if sort == "newest" else Favorite.created_at.asc()

    query = (
        base_query
        .options(
            selectinload(Favorite.listing).selectinload(Listing.photos),
            selectinload(Favorite.listing).selectinload(Listing.price_history),
            selectinload(Favorite.comments),
            selectinload(Favorite.owner),
        )
        .order_by(order)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    favorites = result.scalars().unique().all()

    return FavoritesListResponse(
        favorites=[
            FavoriteListItem(
                id=f.id,
                listing=_listing_response(f.listing),
                comment_count=len(f.comments),
                has_visit_date=f.visit_date is not None,
                status=f.status.value,
                owner=FavoriteOwner(id=f.owner.id, name=f.owner.name, picture=f.owner.picture) if f.owner else None,
                created_at=f.created_at.isoformat(),
            )
            for f in favorites
        ],
        total=total,
    )


@router.get("/{favorite_id}", response_model=FavoriteDetailResponse)
async def get_favorite(
    favorite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite)
        .options(
            selectinload(Favorite.listing).selectinload(Listing.photos),
            selectinload(Favorite.listing).selectinload(Listing.price_history),
            selectinload(Favorite.comments).selectinload(Comment.user),
            selectinload(Favorite.owner),
        )
        .where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    price_history = sorted(fav.listing.price_history, key=lambda ph: ph.observed_at)

    return FavoriteDetailResponse(
        id=fav.id,
        listing=_listing_response(fav.listing),
        comments=[
            CommentResponse(
                id=c.id,
                user_id=c.user_id,
                user_name=c.user.name,
                body=c.body,
                created_at=c.created_at.isoformat(),
            )
            for c in sorted(fav.comments, key=lambda c: c.created_at)
        ],
        price_history=[
            {"price": ph.price, "observed_at": ph.observed_at.isoformat()}
            for ph in price_history
        ],
        visit_date=fav.visit_date.isoformat() if fav.visit_date else None,
        location=fav.location,
        seller_name=fav.seller_name,
        seller_phone=fav.seller_phone,
        seller_is_agency=fav.seller_is_agency,
        status=fav.status.value,
        owner=FavoriteOwner(id=fav.owner.id, name=fav.owner.name, picture=fav.owner.picture) if fav.owner else None,
        created_at=fav.created_at.isoformat(),
    )


@router.patch("/{favorite_id}", response_model=FavoriteDetailResponse)
async def update_favorite(
    favorite_id: int,
    body: FavoriteUpdateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite)
        .options(
            selectinload(Favorite.listing).selectinload(Listing.photos),
            selectinload(Favorite.listing).selectinload(Listing.price_history),
            selectinload(Favorite.comments).selectinload(Comment.user),
            selectinload(Favorite.owner),
        )
        .where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    if body.visit_date is not None:
        fav.visit_date = datetime.fromisoformat(body.visit_date)
    if body.location is not None:
        fav.location = body.location
    if body.seller_name is not None:
        fav.seller_name = body.seller_name
    if body.seller_phone is not None:
        fav.seller_phone = body.seller_phone
    if body.seller_is_agency is not None:
        fav.seller_is_agency = body.seller_is_agency
    if body.status is not None:
        fav.status = FavoriteStatus(body.status)

    # Handle owner assignment + notification
    new_owner_id = None
    if "owner_id" in body.model_fields_set:
        old_owner_id = fav.owner_id
        fav.owner_id = body.owner_id
        if body.owner_id is not None and body.owner_id != old_owner_id:
            new_owner_id = body.owner_id

    await db.flush()

    if new_owner_id is not None and new_owner_id != user.id:
        listing_title = fav.listing.title or "a listing"
        message = f"{user.name} t'a assign\u00e9 {listing_title}"
        db.add(Notification(
            user_id=new_owner_id,
            favorite_id=fav.id,
            message=message,
        ))
        # Send email if the assignee has email notifications enabled
        assignee_result = await db.execute(select(User).where(User.id == new_owner_id))
        assignee = assignee_result.scalar_one_or_none()
        if assignee and assignee.email_notifications:
            background_tasks.add_task(
                send_assignment_email,
                to_email=assignee.email,
                to_name=assignee.name.split()[0] if assignee.name else "",
                assigner_name=user.name,
                listing_title=listing_title,
                favorite_id=fav.id,
            )

    await db.commit()
    await db.refresh(fav, attribute_names=["owner"])

    price_history = sorted(fav.listing.price_history, key=lambda ph: ph.observed_at)

    return FavoriteDetailResponse(
        id=fav.id,
        listing=_listing_response(fav.listing),
        comments=[
            CommentResponse(
                id=c.id,
                user_id=c.user_id,
                user_name=c.user.name,
                body=c.body,
                created_at=c.created_at.isoformat(),
            )
            for c in sorted(fav.comments, key=lambda c: c.created_at)
        ],
        price_history=[
            {"price": ph.price, "observed_at": ph.observed_at.isoformat()}
            for ph in price_history
        ],
        visit_date=fav.visit_date.isoformat() if fav.visit_date else None,
        location=fav.location,
        seller_name=fav.seller_name,
        seller_phone=fav.seller_phone,
        seller_is_agency=fav.seller_is_agency,
        status=fav.status.value,
        owner=FavoriteOwner(id=fav.owner.id, name=fav.owner.name, picture=fav.owner.picture) if fav.owner else None,
        created_at=fav.created_at.isoformat(),
    )


@router.delete("/{favorite_id}")
async def delete_favorite(
    favorite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite).where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")
    await db.delete(fav)
    await db.commit()
    return {"status": "ok"}


@router.post("/{favorite_id}/comments", response_model=CommentResponse)
async def add_comment(
    favorite_id: int,
    body: CommentCreateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite)
        .options(selectinload(Favorite.listing))
        .where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    comment = Comment(favorite_id=fav.id, user_id=user.id, body=body.body)
    db.add(comment)
    await db.flush()

    # Parse @mentions and create notifications for household members
    mentioned_names = set(re.findall(r"@(\w+)", body.body))
    if mentioned_names:
        hh_result = await db.execute(
            select(Household).options(selectinload(Household.members)).where(Household.id == user.household_id)
        )
        household = hh_result.scalar_one()
        listing_title = fav.listing.title or "a listing"
        for member in household.members:
            if member.id == user.id:
                continue
            first_name = member.name.split()[0] if member.name else ""
            if any(first_name.lower() == name.lower() for name in mentioned_names):
                db.add(Notification(
                    user_id=member.id,
                    comment_id=comment.id,
                    favorite_id=fav.id,
                ))
                if member.email_notifications:
                    background_tasks.add_task(
                        send_mention_email,
                        to_email=member.email,
                        to_name=first_name,
                        commenter_name=user.name,
                        comment_body=body.body,
                        listing_title=listing_title,
                        favorite_id=fav.id,
                    )

    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=comment.id,
        user_id=comment.user_id,
        user_name=user.name,
        body=comment.body,
        created_at=comment.created_at.isoformat(),
    )


@router.delete("/{favorite_id}/comments/{comment_id}")
async def delete_comment(
    favorite_id: int,
    comment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment).where(
            Comment.id == comment_id,
            Comment.favorite_id == favorite_id,
            Comment.user_id == user.id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    await db.delete(comment)
    await db.commit()
    return {"status": "ok"}
