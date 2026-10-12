import pytest
from urllib.parse import parse_qs, urlsplit

from app.services.listing_urls import reusable_listing_url
from scripts.repair_junot_urls import authenticated_listing_url


@pytest.mark.parametrize("source", ["junot", "barnes", "consultantsimmobilier"])
def test_apimo_authentication_survives_redirects(source):
    original = "https://ap.immo/p/123?u=test-user&p=test-secret"
    assert reusable_listing_url(original, "https://ap.immo/p/123", source) == original


def test_junot_tracking_entry_point_survives_cookie_authentication():
    original = "https://r.info.junot.fr/tr/cl/test-email-token"
    assert reusable_listing_url(original, "https://ap.immo/p/123", "junot") == original


def test_non_apimo_redirects_still_use_resolved_destination():
    original = "https://r.info.junot.fr/tr/cl/test-email-token"
    resolved = "https://www.junot.fr/annonce/123"
    assert reusable_listing_url(original, resolved, "junot") == resolved


def test_apimo_in_query_is_not_an_authenticated_apimo_host():
    original = "https://www.junot.fr/annonce/123?utm_source=ap.immo"
    resolved = "https://www.junot.fr/annonce/123"
    assert reusable_listing_url(original, resolved, "junot") == resolved


def test_repair_keeps_target_identity_and_preserves_encoded_credentials():
    result = authenticated_listing_url(
        "https://ap.immo/p/123", "https://ap.immo/p/456?u=test%2Buser&p=test%26secret"
    )
    assert urlsplit(result).path == "/p/123"
    assert parse_qs(urlsplit(result).query) == {
        "u": ["test+user"],
        "p": ["test&secret"],
    }


@pytest.mark.parametrize(
    "target", ["https://other.example/p/123", "http://ap.immo/p/123"]
)
def test_repair_does_not_send_credentials_to_other_destinations(target):
    with pytest.raises(ValueError):
        authenticated_listing_url(target, "https://ap.immo/p/456?u=test&p=test")
