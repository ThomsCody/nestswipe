from datetime import UTC, datetime, timedelta

from sqlalchemy import text


async def test_heartbeat_records_activity(client, auth_headers, db_session):
    await db_session.execute(
        text("UPDATE maintenance_presence SET last_activity = :stamp"),
        {"stamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(sep=" ")},
    )
    await db_session.commit()
    response = await client.post("/api/v1/auth/presence", headers=auth_headers)
    assert response.status_code == 204
    assert response.content == b""
    stamp = await db_session.scalar(
        text("SELECT last_activity FROM maintenance_presence")
    )
    assert datetime.fromisoformat(stamp).replace(tzinfo=UTC) > (
        datetime.now(UTC) - timedelta(seconds=5)
    )


async def test_heartbeat_requires_authentication(client):
    assert (await client.post("/api/v1/auth/presence")).status_code == 401


async def test_reservation_blocks_heartbeat_and_user_requests(
    client, auth_headers, db_session
):
    await db_session.execute(
        text("UPDATE maintenance_presence SET reboot_until = :stamp"),
        {"stamp": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(sep=" ")},
    )
    await db_session.commit()
    for method, path in [("POST", "/api/v1/auth/presence"), ("GET", "/api/v1/auth/me")]:
        response = await client.request(method, path, headers=auth_headers)
        assert response.status_code == 503
        assert response.headers["retry-after"] == "60"
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_expired_reservation_allows_requests(client, auth_headers, db_session):
    await db_session.execute(
        text("UPDATE maintenance_presence SET reboot_until = :stamp"),
        {"stamp": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(sep=" ")},
    )
    await db_session.commit()
    assert (
        await client.get("/api/v1/auth/me", headers=auth_headers)
    ).status_code == 200


async def test_missing_presence_state_fails_closed(client, auth_headers, db_session):
    await db_session.execute(text("DELETE FROM maintenance_presence"))
    await db_session.commit()
    assert (
        await client.post("/api/v1/auth/presence", headers=auth_headers)
    ).status_code == 503
