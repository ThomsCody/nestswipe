"""Household-scoped activity for the in-process email parser."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone


_active: dict[int, dict[object, tuple[str, int]]] = {}


def get_polling_state(household_id: int) -> dict:
    tasks = _active.get(household_id, {})
    return {
        "is_polling": bool(tasks),
        "started_at": next((started for started, _ in tasks.values()), None),
        "remaining_emails": sum(remaining for _, remaining in tasks.values()),
    }


@contextmanager
def track_email_processing(
    household_id: int, remaining_emails: int = 1
) -> Iterator[None]:
    """Track actual parsing, cleaning up on success, failure, or cancellation."""
    token = object()
    tasks = _active.setdefault(household_id, {})
    tasks[token] = (datetime.now(timezone.utc).isoformat(), remaining_emails)
    try:
        yield
    finally:
        del tasks[token]
        if not tasks:
            del _active[household_id]
