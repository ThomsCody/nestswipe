"""Verify actual SQL trace propagation with a read-only PostgreSQL query.

Run with ddtrace-run, DD_DBM_PROPAGATION_MODE=full, DD_TRACE_ENABLED=true,
and DATABASE_URL set to a Psycopg SQLAlchemy URL. Prints identifiers only.
Use --seconds 12 when validating Datadog's activity sampling in production.
"""

import argparse
import asyncio
import json
import os
import re

from ddtrace import tracer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def verify(seconds: float) -> dict:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as query_connection, engine.connect() as observer:
            pid = await query_connection.scalar(text("SELECT pg_backend_pid()"))
            await query_connection.rollback()
            with tracer.trace(
                "dbm.correlation.verify", service="nestswipe-backend"
            ) as root:
                root.context.sampling_priority = 2

                async def observe():
                    await asyncio.sleep(0.25)
                    query = await observer.scalar(
                        text("SELECT query FROM pg_stat_activity WHERE pid = :pid"),
                        {"pid": pid},
                    )
                    match = re.match(
                        r"/\*.*traceparent='00-([0-9a-f]{32})-([0-9a-f]{16})-01'.*\*/",
                        query,
                    )
                    assert match, "PostgreSQL did not receive the SQL trace comment"
                    assert int(match[1], 16) == root.trace_id, "Wrong propagated trace"
                    return {
                        "trace_id": match[1],
                        "span_id": str(int(match[2], 16)),
                        "traceparent_verified": True,
                    }

                _, result = await asyncio.gather(
                    query_connection.execute(
                        text("SELECT pg_sleep(:duration), CAST(:marker AS TEXT)"),
                        {"duration": seconds, "marker": "dbm-correlation-verification"},
                    ),
                    observe(),
                )
                return result
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=1)
    args = parser.parse_args()
    if not 0.5 <= args.seconds <= 30:
        parser.error("--seconds must be between 0.5 and 30")
    try:
        print(json.dumps(asyncio.run(verify(args.seconds))))
    finally:
        tracer.shutdown()
