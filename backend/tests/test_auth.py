async def test_me_returns_user_info(client, test_user, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_user.id
    assert data["email"] == "test@example.com"
    assert data["name"] == "Test User"
    assert data["household_id"] == test_user.household_id


async def test_me_without_token_returns_401(client):
    resp = await client.get("/api/v1/auth/me")

    assert resp.status_code == 403  # HTTPBearer returns 403 when no credentials


async def test_refresh_returns_new_token(client, test_user, auth_headers):
    resp = await client.post("/api/v1/auth/refresh", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
