async def test_queue_returns_unswiped_listings(client, auth_headers, sample_listing):
    resp = await client.get("/api/v1/listings/queue", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["remaining"] >= 1
    listing_ids = [l["id"] for l in data["listings"]]
    assert sample_listing.id in listing_ids


async def test_queue_excludes_swiped_listings(client, auth_headers, sample_listing):
    await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "pass"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/listings/queue", headers=auth_headers)

    assert resp.status_code == 200
    listing_ids = [l["id"] for l in resp.json()["listings"]]
    assert sample_listing.id not in listing_ids


async def test_swipe_like_creates_favorite(client, auth_headers, sample_listing):
    resp = await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "like"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Verify a favorite was created
    fav_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    assert fav_resp.status_code == 200
    fav_listing_ids = [f["listing"]["id"] for f in fav_resp.json()["favorites"]]
    assert sample_listing.id in fav_listing_ids


async def test_swipe_pass_does_not_create_favorite(client, auth_headers, sample_listing):
    resp = await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "pass"},
        headers=auth_headers,
    )

    assert resp.status_code == 200

    fav_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    assert fav_resp.status_code == 200
    assert fav_resp.json()["total"] == 0


async def test_swipe_duplicate_returns_409(client, auth_headers, sample_listing):
    await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "like"},
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "like"},
        headers=auth_headers,
    )

    assert resp.status_code == 409


async def test_swipe_nonexistent_listing_returns_404(client, auth_headers, sample_listing):
    resp = await client.post(
        "/api/v1/listings/999/swipe",
        json={"action": "like"},
        headers=auth_headers,
    )

    assert resp.status_code == 404
