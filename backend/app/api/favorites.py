from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.interaction import Comment, Favorite
from app.models.listing import Listing, PriceHistory
from app.models.user import User
from app.schemas.favorite import (
    CommentCreateRequest,
    CommentResponse,
    FavoriteDetailResponse,
    FavoriteListItem,
    FavoritesListResponse,
    FavoriteUpdateRequest,
)
from app.schemas.listing import ListingResponse, PhotoResponse

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
        photos=[PhotoResponse.model_validate(p) for p in sorted(listing.photos, key=lambda p: p.position)],
    )


@router.get("", response_model=FavoritesListResponse)
async def get_favorites(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    sort: str = Query(default="newest"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base_query = select(Favorite).where(Favorite.household_id == user.household_id)

    # Count
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0

    # Sort
    order = Favorite.created_at.desc() if sort == "newest" else Favorite.created_at.asc()

    query = (
        base_query
        .options(
            selectinload(Favorite.listing).selectinload(Listing.photos),
            selectinload(Favorite.comments),
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
            selectinload(Favorite.comments).selectinload(Comment.user),
        )
        .where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    # Get price history
    ph_result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.listing_id == fav.listing_id)
        .order_by(PriceHistory.observed_at)
    )
    price_history = ph_result.scalars().all()

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
        created_at=fav.created_at.isoformat(),
    )


@router.patch("/{favorite_id}", response_model=FavoriteDetailResponse)
async def update_favorite(
    favorite_id: int,
    body: FavoriteUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite)
        .options(
            selectinload(Favorite.listing).selectinload(Listing.photos),
            selectinload(Favorite.comments).selectinload(Comment.user),
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

    await db.commit()
    await db.refresh(fav)

    # Get price history
    ph_result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.listing_id == fav.listing_id)
        .order_by(PriceHistory.observed_at)
    )
    price_history = ph_result.scalars().all()

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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite).where(Favorite.id == favorite_id, Favorite.household_id == user.household_id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    comment = Comment(favorite_id=fav.id, user_id=user.id, body=body.body)
    db.add(comment)
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
