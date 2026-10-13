import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.browser_scraper import ScrapedListing
from app.services.llm_extractor import (
    ExtractedListing,
    extract_listing,
    extract_listing_from_page,
    extract_listings,
)
from scripts.backfill_listings import backfill


@pytest.mark.parametrize("toilets", [None, 0, 2])
@pytest.mark.parametrize(
    "action,section", [("like", "favorites"), ("pass", "archives")]
)
async def test_wc_count_in_queue_and_sections(
    client, auth_headers, db_session, sample_listing, toilets, action, section
):
    sample_listing.toilets = toilets
    await db_session.commit()
    queue = await client.get("/api/v1/listings/queue", headers=auth_headers)
    assert queue.status_code == 200
    assert queue.json()["listings"][0]["toilets"] == toilets
    swipe = await client.post(
        f"/api/v1/listings/{sample_listing.id}/swipe",
        json={"action": action},
        headers=auth_headers,
    )
    assert swipe.status_code == 200
    response = await client.get(f"/api/v1/{section}", headers=auth_headers)
    assert response.status_code == 200
    item = response.json()[section][0]
    assert item["listing"]["toilets"] == toilets
    item_id = item["id"] if section == "favorites" else sample_listing.id
    detail = await client.get(f"/api/v1/{section}/{item_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["listing"]["toilets"] == toilets


@pytest.mark.parametrize("toilets", [None, 0, 2])
@pytest.mark.parametrize("mode", ["email", "digest", "page"])
async def test_wc_count_survives_extraction(mode, toilets):
    payload = {"is_listing": True, "title": "Apartment", "toilets": toilets}
    if mode == "digest":
        payload = {"listings": [payload]}
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=None,
    )
    with patch("app.services.llm_extractor.AsyncOpenAI") as client:
        client.return_value.chat.completions.create = AsyncMock(return_value=response)
        if mode == "page":
            extracted, _, _ = await extract_listing_from_page(
                "test", "Apartment", "pap"
            )
        elif mode == "digest":
            extracted = (await extract_listings("test", "Apartment", "pap"))[0]
        else:
            extracted = await extract_listing("test", "Apartment", "pap")
    assert extracted.toilets == toilets


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("toilets", [None, 0, 2])
async def test_manual_import_persists_wc_count(
    client, auth_headers, db_session, test_user, sample_listing, existing, toilets
):
    test_user.openai_api_key = "test-key"
    await db_session.commit()
    url = "https://www.pap.fr/annonces/-r123456"
    with (
        patch(
            "app.services.import_listing.scrape_listing",
            AsyncMock(
                return_value=ScrapedListing(
                    resolved_url=url, source_id="123456", page_text="Apartment"
                )
            ),
        ),
        patch(
            "app.services.import_listing.extract_listing_from_page",
            AsyncMock(
                return_value=(
                    ExtractedListing(
                        is_listing=True, title="Apartment", toilets=toilets
                    ),
                    0,
                    0,
                )
            ),
        ),
        patch(
            "app.services.import_listing.find_duplicate",
            AsyncMock(return_value=sample_listing if existing else None),
        ),
    ):
        response = await client.post(
            "/api/v1/listings/import", json={"url": url}, headers=auth_headers
        )
    assert response.status_code == 200
    assert response.json()["listing"]["toilets"] == toilets
    assert response.json()["created"] is (not existing)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("extracted_count", [None, 0, 2])
async def test_backfill_selects_missing_wc_and_handles_extraction_tuple(
    db_session, test_user, sample_listing, dry_run, extracted_count
):
    test_user.openai_api_key = "test-key"
    sample_listing.floor = 1
    sample_listing.external_url = "https://www.pap.fr/annonces/-r123456"
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    with (
        patch("scripts.backfill_listings.async_session", session),
        patch(
            "scripts.backfill_listings.scrape_listing",
            AsyncMock(return_value=ScrapedListing(page_text="Apartment")),
        ),
        patch(
            "scripts.backfill_listings.extract_listing_from_page",
            AsyncMock(
                return_value=(
                    ExtractedListing(is_listing=True, toilets=extracted_count),
                    10,
                    5,
                )
            ),
        ) as extract,
    ):
        await backfill(dry_run=dry_run)
    extract.assert_awaited_once()
    await db_session.refresh(sample_listing)
    assert sample_listing.toilets == (None if dry_run else extracted_count)
