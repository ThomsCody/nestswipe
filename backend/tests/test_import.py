from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.interaction import Comment, Favorite, FavoriteStatus
from app.models.listing import Listing
from app.services.browser_scraper import ScrapedListing, detect_source_from_url
from app.services.import_listing import import_listing_from_url
from app.services.llm_extractor import ExtractedListing


class TestDetectSourceFromUrl:
    def test_seloger(self):
        assert (
            detect_source_from_url(
                "https://www.seloger.com/annonces/achat/appartement/paris/228288697.htm"
            )
            == "seloger"
        )

    def test_seloger_no_www(self):
        assert (
            detect_source_from_url("https://seloger.com/annonces/123.htm") == "seloger"
        )

    def test_bellesdemeures(self):
        assert (
            detect_source_from_url(
                "https://www.bellesdemeures.com/annonces/vente/256203535/"
            )
            == "seloger"
        )

    def test_pap(self):
        assert (
            detect_source_from_url("https://www.pap.fr/annonces/-r461702551") == "pap"
        )

    def test_consultantsimmobilier(self):
        assert (
            detect_source_from_url("https://www.consultantsimmobilier.com/listing/123")
            == "consultantsimmobilier"
        )

    def test_ap_immo(self):
        assert (
            detect_source_from_url("https://ap.immo/p/86783633?u=foo")
            == "consultantsimmobilier"
        )

    def test_barnes(self):
        assert (
            detect_source_from_url("https://www.barnes-international.com/en/123")
            == "barnes"
        )

    def test_leboncoin(self):
        assert (
            detect_source_from_url("https://www.leboncoin.fr/vi/3173154827.htm")
            == "leboncoin"
        )

    def test_leboncoin_ad_url(self):
        assert (
            detect_source_from_url(
                "https://www.leboncoin.fr/ad/ventes_immobilieres/3183368834"
            )
            == "leboncoin"
        )

    def test_unknown_domain(self):
        assert detect_source_from_url("https://www.example.com/listing/123") is None

    def test_empty_string(self):
        assert detect_source_from_url("") is None

    def test_invalid_url(self):
        assert detect_source_from_url("not-a-url") is None


async def test_import_unknown_domain_400(client, auth_headers):
    resp = await client.post(
        "/api/v1/listings/import",
        json={"url": "https://www.example.com/listing/123"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Unsupported domain" in resp.json()["detail"]


async def test_import_no_api_key_in_household_400(client, auth_headers):
    resp = await client.post(
        "/api/v1/listings/import",
        json={"url": "https://www.leboncoin.fr/vi/123.htm"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "No OpenAI API key available" in resp.json()["detail"]


async def test_import_existing_favorite_resets_only_status(db_session, test_user):
    url = "https://www.pap.fr/annonces/appartement-paris-16e-75016-r463500277"
    test_user.openai_api_key = "sk-test-key"
    listing = Listing(
        household_id=test_user.household_id,
        user_id=test_user.id,
        source="pap",
        source_id="463500277",
        external_url=url,
        title="Appartement Paris 16e",
        price=900000,
        sqm=80,
        price_per_sqm=11250,
        bedrooms=2,
        rooms=3,
        city="Paris",
        district="16e",
    )
    db_session.add(listing)
    await db_session.flush()

    favorite = Favorite(
        household_id=test_user.household_id,
        listing_id=listing.id,
        status=FavoriteStatus.nogo,
        owner_id=test_user.id,
        location="12 rue de Test",
        seller_name="Agence Test",
        seller_phone="01 23 45 67 89",
        seller_is_agency=True,
    )
    db_session.add(favorite)
    await db_session.flush()
    comment = Comment(
        favorite_id=favorite.id,
        user_id=test_user.id,
        body="Commentaire existant",
    )
    db_session.add(comment)
    await db_session.commit()

    scraped = ScrapedListing(
        resolved_url=url,
        source_id="463500277",
        page_text="Appartement Paris 16e, 80 m2, 3 pieces",
    )
    extracted = ExtractedListing(
        is_listing=True,
        title="Appartement Paris 16e",
        price=900000,
        sqm=80,
        bedrooms=2,
        rooms=3,
        city="Paris",
        district="16e",
    )

    with (
        patch(
            "app.services.import_listing.scrape_listing",
            AsyncMock(return_value=scraped),
        ),
        patch(
            "app.services.import_listing.extract_listing_from_page",
            AsyncMock(return_value=(extracted, 10, 5)),
        ),
    ):
        result = await import_listing_from_url(url, test_user, db_session)

    assert result.created is False
    assert result.already_favorited is True
    assert result.favorite.id == favorite.id
    assert result.favorite.status == FavoriteStatus.to_contact
    assert result.favorite.owner_id == test_user.id
    assert result.favorite.location == "12 rue de Test"
    assert result.favorite.seller_name == "Agence Test"
    assert result.favorite.seller_phone == "01 23 45 67 89"
    assert result.favorite.seller_is_agency is True
    comments = await db_session.execute(
        select(Comment).where(Comment.favorite_id == result.favorite.id)
    )
    assert [existing.body for existing in comments.scalars()] == [
        "Commentaire existant"
    ]


@pytest.mark.parametrize(
    ("existing_key", "download_succeeds", "expected_keys"),
    [
        (None, True, ["photos/restored.jpg"]),
        ("photos/_placeholder.jpg", True, ["photos/restored.jpg"]),
        ("photos/real.jpg", True, ["photos/restored.jpg"]),
        ("photos/real.jpg", False, ["photos/real.jpg"]),
        ("photos/_placeholder.jpg", False, ["photos/_placeholder.jpg"]),
    ],
)
async def test_reimport_refreshes_photos(
    db_session, test_user, existing_key, download_succeeds, expected_keys
):
    from app.models.listing import ListingPhoto

    url = "https://www.bellesdemeures.com/annonces/vente/280623435/"
    test_user.openai_api_key = "test-key"
    listing = Listing(
        household_id=test_user.household_id,
        user_id=test_user.id,
        source="seloger",
        source_id="280623435",
        external_url="https://www.bellesdemeures.com/old-listing/",
        title="Appartement",
    )
    db_session.add(listing)
    await db_session.flush()
    if existing_key:
        db_session.add(
            ListingPhoto(listing_id=listing.id, s3_key=existing_key, position=0)
        )
    await db_session.commit()
    photo_url = "https://v.seloger.com/property.jpg"
    photo_data = [(b"image", "1234", photo_url)] if download_succeeds else []
    with (
        patch(
            "app.services.import_listing.scrape_listing",
            AsyncMock(
                return_value=ScrapedListing(
                    resolved_url=url,
                    source_id="280623435",
                    page_text="Appartement",
                    photo_urls=[photo_url],
                )
            ),
        ),
        patch(
            "app.services.import_listing.extract_listing_from_page",
            AsyncMock(
                return_value=(
                    ExtractedListing(is_listing=True, title="Appartement"),
                    0,
                    0,
                )
            ),
        ),
        patch(
            "app.services.import_listing.download_photo",
            AsyncMock(return_value=b"image" if download_succeeds else None),
        ),
        patch("app.services.import_listing.compute_phash", return_value="1234"),
        patch(
            "app.services.import_listing.classify_photos",
            AsyncMock(return_value=(photo_data, 0, 0)),
        ),
        patch("app.services.import_listing.get_minio_client") as minio,
        patch("app.services.import_listing.ensure_bucket"),
        patch(
            "app.services.import_listing.upload_photo",
            return_value="photos/restored.jpg",
        ) as upload,
    ):
        result = await import_listing_from_url(url, test_user, db_session)
    photos = (
        await db_session.scalars(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        )
    ).all()
    assert result.listing.id == listing.id
    assert result.listing.external_url == url
    assert result.created is False
    assert [photo.s3_key for photo in photos] == expected_keys
    assert upload.call_count == (1 if expected_keys == ["photos/restored.jpg"] else 0)
    if existing_key == "photos/real.jpg" and download_succeeds:
        minio.return_value.remove_object.assert_called_once()
    else:
        minio.return_value.remove_object.assert_not_called()
    if upload.called:
        assert photos[0].original_url == photo_url
        assert photos[0].phash == "1234"
        assert photos[0].position == 0
