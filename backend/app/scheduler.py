import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models.user import User
from app.services.email_processor import process_emails_for_user

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def poll_emails_job():
    logger.info("Starting email poll job")
    async with async_session() as db:
        result = await db.execute(
            select(User).where(
                User.gmail_refresh_token.isnot(None),
                User.openai_api_key.isnot(None),
            )
        )
        users = result.scalars().all()
        for user in users:
            try:
                count = await process_emails_for_user(user, db)
                if count > 0:
                    logger.info("Processed %d emails for user %s", count, user.email)
            except Exception:
                logger.exception("Failed to process emails for user %s", user.id)


async def _get_last_poll_time() -> datetime | None:
    """Return the most recent last_email_poll across all users."""
    async with async_session() as db:
        result = await db.execute(select(func.max(User.last_email_poll)))
        return result.scalar()


async def start_scheduler():
    interval = timedelta(minutes=settings.email_poll_interval_minutes)
    now = datetime.now(timezone.utc)

    last_poll = await _get_last_poll_time()
    if last_poll and (now - last_poll) < interval:
        # Last poll was recent — schedule next run based on elapsed time
        next_run = last_poll + interval
    else:
        # Never polled or overdue — run immediately
        next_run = now

    scheduler.add_job(
        poll_emails_job,
        "interval",
        minutes=settings.email_poll_interval_minutes,
        next_run_time=next_run,
        id="poll_emails",
        replace_existing=True,
    )
    scheduler.start()

    job = scheduler.get_job("poll_emails")
    next_run_str = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job and job.next_run_time else "unknown"
    last_poll_str = last_poll.strftime("%Y-%m-%d %H:%M:%S") if last_poll else "never"
    logger.info(
        "Scheduler started, polling every %d minutes (last poll: %s, next run: %s)",
        settings.email_poll_interval_minutes, last_poll_str, next_run_str,
    )


def stop_scheduler():
    scheduler.shutdown(wait=False)
