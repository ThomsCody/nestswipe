import json

import pytest

from app.services.listing_contact import extract_contact, normalize_phone

URL = "https://www.seloger.com/annonce/achat/paris/26GX2GLYEDPN"


def contact_page(listing_id="26GX2GLYEDPN", private=False):
    payload = {
        "app_cldp": {
            "data": {
                "classified": {
                    "contactSections": {
                        "id": listing_id,
                        "legacyId": "279885581",
                        "brand": "seloger",
                        "contactCard": {
                            "title": "IVA IMMOBILIER",
                            "subtitle": "Ethan Naim",
                            "phoneNumbers": ["invalid", "0614598704"],
                            "isPrivateOwner": private,
                        },
                    }
                }
            }
        }
    }
    return '<script type="application/ld+json">{"telephone":"0153382800"}</script>' + (
        '<script id="__UFRN_LIFECYCLE_SERVERREQUEST__">window["store"]=JSON.parse('
        + json.dumps(json.dumps(payload))
        + ");</script>"
    )


def test_listing_contact_in_double_encoded_page_data():
    assert extract_contact(contact_page(), URL) == {
        "contact_phone": "06 14 59 87 04",
        "agency_name": "IVA IMMOBILIER",
        "agent_name": "Ethan Naim",
    }
    assert (
        extract_contact(
            contact_page(), "https://www.seloger.com/annonces/achat/279885581.htm"
        )["contact_phone"]
        == "06 14 59 87 04"
    )


def test_different_listing_and_portal_numbers_are_not_used():
    assert extract_contact(contact_page("OTHER"), URL) == {}
    assert extract_contact('<script>{"telephone":"0153382800"}</script>', URL) == {}
    assert extract_contact(contact_page(), "https://example.com/26GX2GLYEDPN") == {}


def test_private_owner_is_not_labeled_as_an_agency():
    assert extract_contact(contact_page(private=True), URL) == {
        "contact_phone": "06 14 59 87 04"
    }


@pytest.mark.parametrize(
    "payload", ["broken", "null", "[]", "{}", 'JSON.parse("broken")']
)
def test_malformed_data_is_optional(payload):
    assert (
        extract_contact(
            f'<script id="__UFRN_LIFECYCLE_SERVERREQUEST__">{payload}</script>', URL
        )
        == {}
    )


def test_bellesdemeures_uses_only_revealed_agency_link():
    url = "https://www.bellesdemeures.com/annonces/vente/282384907/"
    html = """<aside class="js_agencyContact">
    <input data-phone="0142247700"><a class="js_phoneNumber" href=""></a>
    <a href="/annuaire-agences-immobilieres/france/test/1151/">La Grandière</a>
    </aside><a href="tel:0123456789">Suggested agency</a>"""
    assert extract_contact(html, url) == {"agency_name": "La Grandière"}
    revealed = html.replace('href=""', 'href="tel:01%2059%2013%2083%2047"')
    assert extract_contact(revealed, url) == {
        "contact_phone": "01 59 13 83 47",
        "agency_name": "La Grandière",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+33 1 59 13 83 47", "01 59 13 83 47"),
        ("0033159138347", "01 59 13 83 47"),
        ("0142247700", "01 42 24 77 00"),
        ("+442079460000", "+442079460000"),
        ("282384907", None),
        ("PhoneNumber", None),
        (None, None),
        ("foo0614598704", None),
    ],
)
def test_phone_validation(value, expected):
    assert normalize_phone(value) == expected
