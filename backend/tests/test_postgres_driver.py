"""Opt-in driver regression tests against a disposable PostgreSQL database."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


async def test_psycopg_transactions_and_types():
    engine = create_async_engine(POSTGRES_URL)
    try:
        async with engine.connect() as conn:
            assert conn.dialect.driver == "psycopg"
            assert conn.dialect.is_async
            await conn.execute(
                text("CREATE TYPE pg_temp.dbm_status AS ENUM ('new', 'done')")
            )
            await conn.execute(
                text("""
                CREATE TEMP TABLE dbm_driver_test (
                    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    amount numeric(12, 2), happened timestamptz,
                    payload jsonb, status pg_temp.dbm_status
                )
            """)
            )
            await conn.commit()
            timestamp = datetime(2026, 10, 24, 12, 30, tzinfo=UTC)
            payload = {"message": "L'appartement à Paris", "items": [1, 2]}
            row_id = await conn.scalar(
                text("""
                    INSERT INTO dbm_driver_test(amount, happened, payload, status)
                    VALUES (:amount, :happened, CAST(:payload AS jsonb), 'new') RETURNING id
                """),
                {
                    "amount": Decimal("123456.78"),
                    "happened": timestamp,
                    "payload": json.dumps(payload),
                },
            )
            await conn.commit()
            row = (
                await conn.execute(
                    text("SELECT * FROM dbm_driver_test WHERE id = :id"), {"id": row_id}
                )
            ).one()
            assert row.amount == Decimal("123456.78")
            assert row.happened == timestamp
            assert row.payload == payload
            assert row.status == "new"
            await conn.execute(
                text("UPDATE dbm_driver_test SET status = 'done' WHERE id = :id"),
                {"id": row_id},
            )
            await conn.rollback()
            assert (
                await conn.scalar(text("SELECT status FROM dbm_driver_test")) == "new"
            )
            # Reuse the parameterized statement beyond Psycopg's preparation threshold.
            for value in range(8):
                assert (
                    await conn.scalar(
                        text("SELECT CAST(:value AS integer)"), {"value": value}
                    )
                    == value
                )
            await conn.execute(
                text("DELETE FROM dbm_driver_test WHERE id = :id"), {"id": row_id}
            )
            await conn.commit()
            assert await conn.scalar(text("SELECT count(*) FROM dbm_driver_test")) == 0
    finally:
        await engine.dispose()


def test_psycopg_sends_trace_context_to_postgres():
    backend = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "DATABASE_URL": POSTGRES_URL,
        "DD_TRACE_ENABLED": "true",
        "DD_DBM_PROPAGATION_MODE": "full",
        "DD_SERVICE": "nestswipe-backend",
        "DD_ENV": "test",
        "DD_PSYCOPG_SERVICE": "nestswipe-db",
        "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
    }
    result = subprocess.run(
        [
            str(Path(sys.executable).parent / "ddtrace-run"),
            sys.executable,
            "scripts/verify_dbm_correlation.py",
        ],
        cwd=backend,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["traceparent_verified"]
