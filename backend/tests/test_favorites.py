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
