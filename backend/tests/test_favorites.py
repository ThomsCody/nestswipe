import pytest


async def _like_listing(client, auth_headers, listing_id: int):
    """Swipe like on a listing to create a favorite."""
    resp = await client.post(
        f"/api/v1/listings/{listing_id}/swipe",
        json={"action": "like"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


async def test_list_favorites(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    resp = await client.get("/api/v1/favorites", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["favorites"][0]["listing"]["id"] == sample_listing.id


async def test_get_favorite_detail(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    list_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = list_resp.json()["favorites"][0]["id"]

    resp = await client.get(f"/api/v1/favorites/{favorite_id}", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == favorite_id
    assert data["listing"]["id"] == sample_listing.id
    assert data["listing"]["title"] == "Test Apartment"


async def test_update_favorite_seller_name(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    list_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = list_resp.json()["favorites"][0]["id"]

    resp = await client.patch(
        f"/api/v1/favorites/{favorite_id}",
        json={"seller_name": "Jean Dupont"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["seller_name"] == "Jean Dupont"


async def test_add_comment(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    list_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = list_resp.json()["favorites"][0]["id"]

    resp = await client.post(
        f"/api/v1/favorites/{favorite_id}/comments",
        json={"body": "Great location!"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["body"] == "Great location!"
    assert data["user_name"] == "Test User"


async def test_delete_comment(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    list_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = list_resp.json()["favorites"][0]["id"]

    comment_resp = await client.post(
        f"/api/v1/favorites/{favorite_id}/comments",
        json={"body": "To be removed"},
        headers=auth_headers,
    )
    comment_id = comment_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/favorites/{favorite_id}/comments/{comment_id}",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_delete_favorite(client, auth_headers, sample_listing):
    await _like_listing(client, auth_headers, sample_listing.id)

    list_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = list_resp.json()["favorites"][0]["id"]

    resp = await client.delete(f"/api/v1/favorites/{favorite_id}", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Verify it was removed
    check_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    assert check_resp.json()["total"] == 0


async def test_offer_roundtrip_partial_update_and_clear(
    client, auth_headers, sample_listing
):
    await _like_listing(client, auth_headers, sample_listing.id)
    favorites = await client.get("/api/v1/favorites", headers=auth_headers)
    url = f"/api/v1/favorites/{favorites.json()['favorites'][0]['id']}"
    initial = await client.get(url, headers=auth_headers)
    assert initial.json()["offer_price"] is None
    assert initial.json()["renovation_budget"] is None

    response = await client.patch(
        url,
        headers=auth_headers,
        json={
            "offer_price": "500000.25",
            "renovation_budget": "50000.50",
        },
    )
    assert response.status_code == 200
    assert response.json()["offer_price"] == "500000.25"
    assert response.json()["renovation_budget"] == "50000.50"

    # An unrelated PATCH must preserve saved budgets.
    await client.patch(url, headers=auth_headers, json={"seller_name": "Alice"})
    persisted = await client.get(url, headers=auth_headers)
    assert persisted.json()["offer_price"] == "500000.25"
    assert persisted.json()["renovation_budget"] == "50000.50"

    zero = await client.patch(
        url, headers=auth_headers, json={"renovation_budget": "0"}
    )
    assert zero.status_code == 200
    assert zero.json()["renovation_budget"] == "0.00"
    assert zero.json()["offer_price"] == "500000.25"

    cleared = await client.patch(
        url,
        headers=auth_headers,
        json={
            "offer_price": None,
            "renovation_budget": None,
        },
    )
    assert cleared.status_code == 200
    persisted = await client.get(url, headers=auth_headers)
    assert persisted.json()["offer_price"] is None
    assert persisted.json()["renovation_budget"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"offer_price": "-1"},
        {"offer_price": "0"},
        {"offer_price": "123.456"},
        {"offer_price": "10000000000"},
        {"offer_price": "NaN"},
        {"renovation_budget": "-1"},
        {"renovation_budget": "1.234"},
        {"renovation_budget": "Infinity"},
        {"renovation_budget": "10000000000"},
    ],
)
async def test_offer_rejects_invalid_money(
    client, auth_headers, sample_listing, payload
):
    await _like_listing(client, auth_headers, sample_listing.id)
    favorites = await client.get("/api/v1/favorites", headers=auth_headers)
    favorite_id = favorites.json()["favorites"][0]["id"]
    response = await client.patch(
        f"/api/v1/favorites/{favorite_id}", headers=auth_headers, json=payload
    )
    assert response.status_code == 422


async def test_offer_cannot_be_updated_by_another_household(
    client, auth_headers, sample_listing, db_session
):
    from app.api.auth import create_access_token

    from app.models.user import Household, User

    await _like_listing(client, auth_headers, sample_listing.id)
    favorites = await client.get("/api/v1/favorites", headers=auth_headers)
    url = f"/api/v1/favorites/{favorites.json()['favorites'][0]['id']}"
    household = Household(name="Other household")
    db_session.add(household)
    await db_session.flush()
    outsider = User(
        google_id="outsider",
        email="outsider@example.com",
        name="Other",
        household_id=household.id,
    )
    db_session.add(outsider)
    await db_session.commit()
    token = create_access_token(outsider.id)
    response = await client.patch(
        url, headers={"Authorization": f"Bearer {token}"}, json={"offer_price": "1"}
    )
    assert response.status_code == 404
    own_response = await client.get(url, headers=auth_headers)
    assert own_response.json()["offer_price"] is None
