import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

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


def start_scheduler():
    scheduler.add_job(
        poll_emails_job,
        "interval",
        minutes=settings.email_poll_interval_minutes,
        id="poll_emails",
        replace_existing=True,
    )
    scheduler.start()
    job = scheduler.get_job("poll_emails")
    next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job and job.next_run_time else "unknown"
    logger.info("Scheduler started, polling every %d minutes (next run: %s)", settings.email_poll_interval_minutes, next_run)


def stop_scheduler():
    scheduler.shutdown(wait=False)
