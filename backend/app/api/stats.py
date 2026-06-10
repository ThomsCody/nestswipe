from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# GPT-4o-mini pricing (USD per token)
GPT4O_MINI_INPUT_COST = 0.15 / 1_000_000
GPT4O_MINI_OUTPUT_COST = 0.60 / 1_000_000

from app.api.deps import get_current_user
from app.database import get_db
from app.models.parse_attempt import ParseAttempt
from app.models.user import User

router = APIRouter()


def _period_bounds(period: str, offset: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)

    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
        end = start + timedelta(days=1)

    elif period == "week":
        # Monday of current week
        monday = now - timedelta(days=now.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        start = monday + timedelta(weeks=offset)
        end = start + timedelta(weeks=1)

    else:  # month
        year = now.year
        month = now.month
        # Add offset months manually to avoid an external dependency on dateutil
        total_months = year * 12 + (month - 1) + offset
        start_year = total_months // 12
        start_month = total_months % 12 + 1
        start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)
        # End is first day of the following month
        end_total = total_months + 1
        end_year = end_total // 12
        end_month = end_total % 12 + 1
        end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)

    return start, end


def _period_label(period: str, offset: int, period_start: datetime) -> str:
    if period == "day":
        if offset == 0:
            return "Today"
        if offset == -1:
            return "Yesterday"
        return period_start.strftime("%-d %b")  # e.g. "3 Jun"

    if period == "week":
        if offset == 0:
            return "This week"
        if offset == -1:
            return "Last week"
        return "Week of " + period_start.strftime("%-d %b")  # e.g. "Week of 2 Jun"

    # month
    if offset == 0:
        return "This month"
    if offset == -1:
        return "Last month"
    return period_start.strftime("%B %Y")  # e.g. "June 2026"


@router.get("")
async def get_stats(
    period: str = Query(default="week", pattern="^(day|week|month)$"),
    offset: int = Query(default=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # offset must be <= 0 — disallow querying future periods
    offset = min(offset, 0)

    period_start, period_end = _period_bounds(period, offset)
    label = _period_label(period, offset, period_start)

    base_filter = (
        ParseAttempt.household_id == user.household_id,
        ParseAttempt.created_at >= period_start,
        ParseAttempt.created_at < period_end,
    )

    # Aggregate totals in a single query
    totals_result = await db.execute(
        select(
            func.count(distinct(ParseAttempt.email_id)).filter(
                ParseAttempt.email_id.is_not(None)
            ).label("emails_parsed"),
            func.count().filter(ParseAttempt.status == "success").label("listings_success"),
            func.count().filter(ParseAttempt.result == "new").label("listings_new"),
            func.count().filter(ParseAttempt.result == "updated").label("listings_updated"),
            func.count().filter(
                ParseAttempt.status == "failed",
                ParseAttempt.url.is_not(None),
            ).label("listings_failed"),
            func.coalesce(func.sum(ParseAttempt.llm_input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(ParseAttempt.llm_output_tokens), 0).label("total_output_tokens"),
        ).where(*base_filter)
    )
    totals = totals_result.one()

    total_cost = round(
        totals.total_input_tokens * GPT4O_MINI_INPUT_COST
        + totals.total_output_tokens * GPT4O_MINI_OUTPUT_COST,
        6,
    )

    # Per-source breakdown
    source_result = await db.execute(
        select(
            ParseAttempt.source,
            func.count(distinct(ParseAttempt.email_id)).filter(
                ParseAttempt.email_id.is_not(None)
            ).label("emails"),
            func.count().filter(ParseAttempt.status == "success").label("success"),
            func.count().filter(ParseAttempt.result == "new").label("new"),
            func.count().filter(ParseAttempt.result == "updated").label("updated"),
            func.count().filter(
                ParseAttempt.status == "failed",
                ParseAttempt.url.is_not(None),
            ).label("failed"),
            func.coalesce(func.sum(ParseAttempt.llm_input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(ParseAttempt.llm_output_tokens), 0).label("output_tokens"),
        )
        .where(*base_filter)
        .group_by(ParseAttempt.source)
        .order_by(ParseAttempt.source)
    )

    by_source = {
        row.source: {
            "emails": row.emails,
            "success": row.success,
            "new": row.new,
            "updated": row.updated,
            "failed": row.failed,
            "cost_usd": round(
                row.input_tokens * GPT4O_MINI_INPUT_COST
                + row.output_tokens * GPT4O_MINI_OUTPUT_COST,
                6,
            ),
        }
        for row in source_result
    }

    return {
        "period": period,
        "offset": offset,
        "period_label": label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "emails_parsed": totals.emails_parsed,
        "listings_success": totals.listings_success,
        "listings_new": totals.listings_new,
        "listings_updated": totals.listings_updated,
        "listings_failed": totals.listings_failed,
        "total_cost_usd": total_cost,
        "by_source": by_source,
    }
