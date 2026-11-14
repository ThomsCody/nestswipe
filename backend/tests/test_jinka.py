"""Jinka's public listing template renders five photos, with the full gallery in JSON-LD."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.listing import Listing
from app.services import browser_scraper as scraper
from app.services import listing_metrics
from app.services.email_processor import _build_query, _detect_source
from app.services.llm_extractor import ExtractedListing
from sqlalchemy import select

SOURCE_ID = "90281149-44de-4c1e-aad2-844f0ed5e33f"
URL = f"https://www.jinka.fr/ad/{SOURCE_ID}"
PHOTOS = [f"https://media.apimo.pro/cache/room-{i}-original.jpg" for i in range(18)]
LISTING_DATA = {
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    "@id": URL,
    "image": PHOTOS,
}


def listing_html(data=LISTING_DATA):
    rendered_photos = "".join(f'<img src="{url}">' for url in PHOTOS[:5])
    return f"""<html><head>
    <script type="application/ld+json">{json.dumps(data)}</script>
    <script type="application/ld+json">{{"@type":"Organization",
        "image":"https://example.com/agency.jpg"}}</script>
    </head><body><h1>Appartement Paris 15e</h1>
    <p>Appartement de 108 m², cinq pièces, trois chambres, troisième étage.
    Prix de vente : 1 390 000 euros.</p>{rendered_photos}
    <img src="https://example.com/agency.jpg">
    <div class="similar-listings"><img src="https://example.com/other-flat.jpg"></div>
    </body></html>"""


@pytest.mark.parametrize("host", ["jinka.fr", "www.jinka.fr"])
def test_source_and_stable_id(host):
    url = f"https://{host}/ad/{SOURCE_ID}/?utm_source=email#photos"
    assert scraper.detect_source_from_url(url) == "jinka"
    assert scraper._extract_source_id(url, "jinka") == SOURCE_ID


@pytest.mark.parametrize(
    "url",
    [
        "https://www.jinka.fr.evil.example/ad/" + SOURCE_ID,
        "https://www.jinka.fr@evil.example/ad/" + SOURCE_ID,
    ],
)
def test_similar_host_is_not_jinka(url):
    assert scraper.detect_source_from_url(url) is None


@pytest.mark.parametrize("path", ["/", "/ad/not-a-uuid", "/agency/barnes-mars"])
def test_non_listing_paths_have_no_source_id(path):
    assert scraper._extract_source_id("https://www.jinka.fr" + path, "jinka") is None


@pytest.mark.parametrize("data", [LISTING_DATA, [LISTING_DATA]])
def test_full_gallery_excludes_agency_and_recommendation_images(data):
    photos, labels = scraper._extract_photos_from_html(listing_html(data), "jinka")
    assert photos == PHOTOS
    assert labels == {}


def test_gallery_filters_duplicates_invalid_entries_and_limits_size():
    photos = [f"https://example.com/room-{i}.jpg" for i in range(40)]
    data = {**LISTING_DATA, "image": [None, 42, {}, PHOTOS[0], PHOTOS[0], *photos]}
    actual, _ = scraper._extract_photos_from_html(listing_html(data), "jinka")
    assert actual == [PHOTOS[0], *photos][: scraper.MAX_PHOTOS_PER_LISTING]


@pytest.mark.parametrize("data", [None, {}, {**LISTING_DATA, "image": None}])
def test_missing_gallery_falls_back_to_rendered_images(data):
    photos, _ = scraper._extract_photos_from_html(listing_html(data), "jinka")
    assert photos[:5] == PHOTOS[:5]


def test_invalid_json_does_not_break_scraping():
    html = listing_html().replace(json.dumps(LISTING_DATA), "{invalid-json")
    photos, _ = scraper._extract_photos_from_html(html, "jinka")
    assert photos[:5] == PHOTOS[:5]


def test_email_alerts_are_discovered_and_identified():
    assert "from:jinka.fr" in _build_query(None)
    assert _detect_source("Jinka <alertes@jinka.fr>") == "jinka"


def test_monitoring_identifies_real_jinka_imports(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(listing_metrics, "_client", lambda: client)
    listing_metrics.scrape_attempt("jinka", "import")
    client.increment.assert_called_once_with(
        "nestswipe.listing_access.attempts",
        1,
        tags=["listing_source:jinka", "purpose:import"],
    )


async def test_import_url_scrapes_and_reimports_same_jinka_listing(
    client, auth_headers, test_user, db_session
):
    test_user.openai_api_key = "test-key"
    await db_session.commit()
    http = MagicMock()
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=None)
    http.get = AsyncMock(
        return_value=SimpleNamespace(
            status_code=200, text=listing_html(), url=URL, headers={}
        )
    )
    extracted = ExtractedListing(
        is_listing=True,
        title="Appartement Paris 15e",
        price=1390000,
        sqm=108,
        bedrooms=3,
        rooms=5,
        floor=3,
        city="Paris",
        district="15e",
    )
    with (
        patch.object(scraper, "AsyncSession", return_value=http) as session_factory,
        patch(
            "app.services.import_listing.extract_listing_from_page",
            AsyncMock(return_value=(extracted, 10, 5)),
        ) as extract,
        patch(
            "app.services.import_listing.download_photo", AsyncMock(return_value=None)
        ) as download,
    ):
        first = await client.post(
            "/api/v1/listings/import", json={"url": URL}, headers=auth_headers
        )
        second = await client.post(
            "/api/v1/listings/import",
            json={"url": URL + "?utm_source=email"},
            headers=auth_headers,
        )

    assert first.status_code == second.status_code == 200
    result = first.json()
    assert result["created"] is True
    assert result["listing"]["source"] == "jinka"
    assert result["listing"]["external_url"] == URL
    assert result["listing"]["price"] == 1390000
    assert result["listing"]["rooms"] == 5
    assert second.json()["created"] is False
    assert second.json()["already_favorited"] is True
    assert result["favorite_id"] == second.json()["favorite_id"]
    stored = (await db_session.scalars(select(Listing))).all()
    assert len(stored) == 1
    assert stored[0].source_id == SOURCE_ID
    assert extract.await_args.args[2] == "jinka"
    assert "1 390 000" in extract.await_args.args[1]
    assert [call.args[0] for call in download.await_args_list] == PHOTOS * 2
    assert session_factory.call_args.kwargs["proxy"] is None
