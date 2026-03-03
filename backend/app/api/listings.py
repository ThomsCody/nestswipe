from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.interaction import Favorite, SwipeAction, SwipeDirection
from app.models.listing import Listing, ListingPhoto
from app.models.user import User
from app.schemas.listing import ListingResponse, PhotoResponse, PriceHistoryItem, QueueResponse, SwipeRequest

router = APIRouter()


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    limit: int = Query(default=10, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get listing IDs the user has already swiped on
    swiped_subq = select(SwipeAction.listing_id).where(SwipeAction.user_id == user.id).subquery()

    # Only show listings that have at least one photo
    has_photos_subq = select(ListingPhoto.listing_id).distinct().subquery()

    # Exclude listings already in household favorites
    fav_subq = select(Favorite.listing_id).where(Favorite.household_id == user.household_id).subquery()

    # Get unseen listings for this household
    queue_filters = [
        Listing.user_id == user.id,
        Listing.id.notin_(select(swiped_subq)),
        Listing.id.notin_(select(fav_subq)),
        Listing.id.in_(select(has_photos_subq)),
    ]
    query = (
        select(Listing)
        .options(selectinload(Listing.photos), selectinload(Listing.price_history))
        .where(*queue_filters)
        .order_by(Listing.first_seen_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    listings = result.scalars().unique().all()

    # Count remaining
    count_query = select(func.count(Listing.id)).where(*queue_filters)
    count_result = await db.execute(count_query)
    remaining = count_result.scalar() or 0

    return QueueResponse(
        listings=[
            ListingResponse(
                id=l.id,
                source=l.source,
                title=l.title,
                description=l.description,
                price=l.price,
                sqm=l.sqm,
                price_per_sqm=l.price_per_sqm,
                bedrooms=l.bedrooms,
                rooms=l.rooms,
                floor=l.floor,
                city=l.city,
                district=l.district,
                location_detail=l.location_detail,
                external_url=l.external_url,
                photos=[PhotoResponse.model_validate(p) for p in sorted(l.photos, key=lambda p: p.position)],
                price_history=[
                    PriceHistoryItem(price=ph.price, observed_at=ph.observed_at.isoformat())
                    for ph in sorted(l.price_history, key=lambda ph: ph.observed_at)
                ],
            )
            for l in listings
        ],
        remaining=remaining,
    )


@router.post("/{listing_id}/swipe")
async def swipe(
    listing_id: int,
    body: SwipeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("like", "pass"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be 'like' or 'pass'")

    # Verify listing belongs to user's household
    result = await db.execute(select(Listing).where(Listing.id == listing_id, Listing.user_id == user.id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    # Check if already swiped
    existing = await db.execute(
        select(SwipeAction).where(SwipeAction.user_id == user.id, SwipeAction.listing_id == listing_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already swiped")

    direction = SwipeDirection.like if body.action == "like" else SwipeDirection.pass_
    db.add(SwipeAction(user_id=user.id, listing_id=listing_id, action=direction))

    # If liked, create a household favorite (if not exists)
    if body.action == "like":
        fav_result = await db.execute(
            select(Favorite).where(Favorite.household_id == user.household_id, Favorite.listing_id == listing_id)
        )
        if not fav_result.scalar_one_or_none():
            db.add(Favorite(household_id=user.household_id, listing_id=listing_id))

    await db.commit()
    return {"status": "ok"}
