async def test_list_archives_after_pass(client, auth_headers, sample_listing):
    await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "pass"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/archives", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["archives"][0]["listing"]["id"] == sample_listing.id


async def test_restore_archive_creates_favorite(client, auth_headers, sample_listing):
    await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": "pass"},
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/archives/{sample_listing.id}/restore",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Listing should now appear in favorites
    fav_resp = await client.get("/api/v1/favorites", headers=auth_headers)
    fav_listing_ids = [f["listing"]["id"] for f in fav_resp.json()["favorites"]]
    assert sample_listing.id in fav_listing_ids

    # Listing should no longer appear in archives
    archive_resp = await client.get("/api/v1/archives", headers=auth_headers)
    assert archive_resp.json()["total"] == 0
