async def test_get_household(client, auth_headers, test_user):
    resp = await client.get("/api/v1/household", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == test_user.household_id
    member_emails = [m["email"] for m in data["members"]]
    assert "test@example.com" in member_emails


async def test_invite_creates_pending_invite(client, auth_headers, test_user):
    resp = await client.post(
        "/api/v1/household/invite",
        json={"email": "other@test.com"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["invitee_email"] == "other@test.com"
    assert data["status"] == "pending"
    assert data["inviter_name"] == "Test User"


async def test_invite_own_email_returns_400(client, auth_headers, test_user):
    resp = await client.post(
        "/api/v1/household/invite",
        json={"email": "test@example.com"},
        headers=auth_headers,
    )

    assert resp.status_code == 400


async def test_get_sent_invites(client, auth_headers, test_user):
    await client.post(
        "/api/v1/household/invite",
        json={"email": "other@test.com"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/household/invites/sent", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["invitee_email"] == "other@test.com"
