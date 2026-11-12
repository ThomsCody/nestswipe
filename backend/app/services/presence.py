"""Serialize authenticated activity with the host's maintenance reservation."""

from fastapi import HTTPException
from sqlalchemy import text


async def record_activity(db):
    # This row lock also serializes with the reboot watcher's conditional UPDATE.
    # A request arriving after reservation must not enter an application handler.
    result = await db.execute(
        text("""
            UPDATE maintenance_presence SET last_activity = CURRENT_TIMESTAMP
            WHERE id = 1
              AND (reboot_until IS NULL OR reboot_until < CURRENT_TIMESTAMP)
            RETURNING id
        """)
    )
    admitted = result.scalar_one_or_none() is not None
    await db.commit()
    if not admitted:
        raise HTTPException(
            status_code=503,
            detail="Brief overnight maintenance; please retry in a few minutes.",
            headers={"Retry-After": "60"},
        )
