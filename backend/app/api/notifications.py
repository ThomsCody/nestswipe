from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.interaction import Comment, Favorite
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationCountResponse, NotificationResponse

router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification)
        .options(
            selectinload(Notification.comment).selectinload(Comment.user),
        )
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifications = result.scalars().all()

    # Load favorites + listings for titles
    favorite_ids = {n.favorite_id for n in notifications}
    if favorite_ids:
        fav_result = await db.execute(
            select(Favorite)
            .options(selectinload(Favorite.listing))
            .where(Favorite.id.in_(favorite_ids))
        )
        fav_map = {f.id: f for f in fav_result.scalars().all()}
    else:
        fav_map = {}

    return [
        NotificationResponse(
            id=n.id,
            comment_body=n.comment.body[:200] if n.comment else None,
            commenter_name=n.comment.user.name if n.comment else None,
            message=n.message,
            favorite_id=n.favorite_id,
            listing_title=fav_map[n.favorite_id].listing.title if n.favorite_id in fav_map else "",
            created_at=n.created_at.isoformat(),
            is_read=n.is_read,
        )
        for n in notifications
    ]


@router.get("/count", response_model=NotificationCountResponse)
async def get_notification_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
    )
    count = result.scalar() or 0
    return NotificationCountResponse(unread=count)


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    await db.commit()
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import update

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return {"status": "ok"}
