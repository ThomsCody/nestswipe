"""Force-reprocess specific Gmail messages, bypassing the already-processed guard.

Used to recover listings from emails whose first attempt failed for a transient
reason (e.g. SeLoger anti-bot rate limiting) that has since been fixed.

Run from the backend container:

    # Reprocess every email that had a failed ParseAttempt in a time window
    python -m scripts.reprocess_emails --source seloger --since "2026-07-27 00:00" --until "2026-07-28 00:00"

    # Or reprocess specific Gmail message IDs directly
    python -m scripts.reprocess_emails --email-ids 19fa501bd80e9ca8 19fa500a3cee4710
"""

import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.database import async_session
from app.models.parse_attempt import ParseAttempt
from app.models.user import User
from app.services.email_processor import reprocess_emails

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _find_failed_email_ids(source: str | None, since: datetime | None, until: datetime | None) -> list[str]:
    query = select(ParseAttempt.email_id).where(
        ParseAttempt.status == "failed",
        ParseAttempt.email_id.isnot(None),
    ).distinct()
    if source:
        query = query.where(ParseAttempt.source == source)
    if since:
        query = query.where(ParseAttempt.created_at >= since)
    if until:
        query = query.where(ParseAttempt.created_at < until)

    async with async_session() as db:
        result = await db.execute(query)
        return [row[0] for row in result.all()]


async def main(args: argparse.Namespace) -> None:
    if args.email_ids:
        email_ids = args.email_ids
    else:
        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None
        email_ids = await _find_failed_email_ids(args.source, since, until)

    if not email_ids:
        logger.info("Nothing to reprocess")
        return

    logger.info("Reprocessing %d email(s): %s", len(email_ids), email_ids)

    async with async_session() as db:
        result = await db.execute(select(User).where(User.gmail_refresh_token.isnot(None)))
        users = result.scalars().all()
        if not users:
            logger.error("No user with a Gmail refresh token found")
            return

        total = 0
        for user in users:
            count = await reprocess_emails(user, db, email_ids)
            logger.info("User %s: reprocessed into %d listing(s)", user.email, count)
            total += count

    logger.info("Done. %d listing(s) created/updated.", total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email-ids", nargs="+", help="Specific Gmail message IDs to reprocess")
    parser.add_argument("--source", help="Only reprocess failed attempts from this source (e.g. seloger)")
    parser.add_argument("--since", help="Only reprocess attempts at/after this time, e.g. '2026-07-27 00:00'")
    parser.add_argument("--until", help="Only reprocess attempts before this time, e.g. '2026-07-28 00:00'")
    args = parser.parse_args()

    asyncio.run(main(args))
