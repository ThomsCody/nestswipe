from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.interaction import Favorite, SwipeAction, SwipeDirection
from app.models.listing import Listing
from app.models.user import User
from app.schemas.listing import ArchiveListItem, ArchivesListResponse, ListingResponse, PhotoResponse, PriceHistoryItem

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
        price_history=[
            PriceHistoryItem(price=ph.price, observed_at=ph.observed_at.isoformat())
            for ph in sorted(listing.price_history, key=lambda ph: ph.observed_at)
        ],
    )


@router.get("", response_model=ArchivesListResponse)
async def get_archives(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    sort: str = Query(default="newest"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Exclude listings already in household favorites
    fav_subq = select(Favorite.listing_id).where(Favorite.household_id == user.household_id).subquery()

    base_query = (
        select(SwipeAction)
        .where(SwipeAction.user_id == user.id, SwipeAction.action == SwipeDirection.pass_)
        .join(Listing, SwipeAction.listing_id == Listing.id)
        .where(Listing.household_id == user.household_id)
        .where(SwipeAction.listing_id.notin_(select(fav_subq)))
    )

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0

    order = SwipeAction.created_at.desc() if sort == "newest" else SwipeAction.created_at.asc()

    query = (
        base_query.options(
            selectinload(SwipeAction.listing).selectinload(Listing.photos),
            selectinload(SwipeAction.listing).selectinload(Listing.price_history),
        )
        .order_by(order)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    swipes = result.scalars().unique().all()

    return ArchivesListResponse(
        archives=[
            ArchiveListItem(
                listing=_listing_response(s.listing),
                passed_at=s.created_at.isoformat(),
            )
            for s in swipes
        ],
        total=total,
    )


@router.post("/{listing_id}/restore")
async def restore_archive(
    listing_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Find the pass swipe action
    result = await db.execute(
        select(SwipeAction).where(
            SwipeAction.user_id == user.id,
            SwipeAction.listing_id == listing_id,
            SwipeAction.action == SwipeDirection.pass_,
        )
    )
    swipe = result.scalar_one_or_none()
    if not swipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archived listing not found")

    # Flip the pass swipe to a like so it doesn't reappear in queue
    swipe.action = SwipeDirection.like

    # Create favorite if not already exists
    existing_fav = await db.execute(
        select(Favorite).where(
            Favorite.household_id == user.household_id,
            Favorite.listing_id == listing_id,
        )
    )
    if not existing_fav.scalar_one_or_none():
        fav = Favorite(household_id=user.household_id, listing_id=listing_id)
        db.add(fav)

    await db.commit()
    return {"status": "ok"}
