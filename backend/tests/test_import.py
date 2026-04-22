import pytest

from app.services.browser_scraper import detect_source_from_url


class TestDetectSourceFromUrl:
    def test_seloger(self):
        assert detect_source_from_url("https://www.seloger.com/annonces/achat/appartement/paris/228288697.htm") == "seloger"

    def test_seloger_no_www(self):
        assert detect_source_from_url("https://seloger.com/annonces/123.htm") == "seloger"

    def test_bellesdemeures(self):
        assert detect_source_from_url("https://www.bellesdemeures.com/annonces/vente/256203535/") == "seloger"

    def test_pap(self):
        assert detect_source_from_url("https://www.pap.fr/annonces/-r461702551") == "pap"

    def test_consultantsimmobilier(self):
        assert detect_source_from_url("https://www.consultantsimmobilier.com/listing/123") == "consultantsimmobilier"

    def test_ap_immo(self):
        assert detect_source_from_url("https://ap.immo/p/86783633?u=foo") == "consultantsimmobilier"

    def test_barnes(self):
        assert detect_source_from_url("https://www.barnes-international.com/en/123") == "barnes"

    def test_leboncoin(self):
        assert detect_source_from_url("https://www.leboncoin.fr/vi/3173154827.htm") == "leboncoin"

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
