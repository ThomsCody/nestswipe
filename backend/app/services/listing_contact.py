"""Extract listing-owned contact data without mixing in portal/recommendation phones."""

import json
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


def normalize_phone(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[+\d\s().-]+", value.strip()):
        return None
    number = re.sub(r"[\s().-]", "", value)
    if number.startswith("0033"):
        number = "+33" + number[4:]
    if number.startswith("+33"):
        number = "0" + number[3:]
    if re.fullmatch(r"0[1-9]\d{8}", number):
        return " ".join(number[i : i + 2] for i in range(0, 10, 2))
    if re.fullmatch(r"\+[1-9]\d{7,14}", number):
        return number
    return None


def extract_contact(html: str, url: str) -> dict[str, str]:
    host = urlparse(url).hostname
    soup = BeautifulSoup(html, "html.parser")
    if host in {"bellesdemeures.com", "www.bellesdemeures.com"}:
        # Only the revealed link is authoritative: data-phone can be replaced
        # by /GetNumber when the site displays its listing contact number.
        # SoupSieve's lazy CSS regex lock can deadlock with the production
        # profiler's lock-name inspection. Direct tree searches avoid that lock.
        contact = soup.find(class_="js_agencyContact")
        if contact is None:
            return {}
        result = {}
        phone = contact.find(class_="js_phoneNumber", href=re.compile(r"^tel:"))
        if phone and (number := normalize_phone(unquote(phone["href"][4:]))):
            result["contact_phone"] = number
        agency = contact.find("a", href=re.compile(r"/annuaire-agences-immobilieres/"))
        if agency:
            name = agency.get_text(" ", strip=True)
            if not name and (logo := agency.find("img", alt=True)):
                match = re.fullmatch(r"Agence immobilière (.+) à .+", logo["alt"])
                name = match[1] if match else ""
            if name:
                result["agency_name"] = name
        return result
    if host not in {"seloger.com", "www.seloger.com"}:
        return {}
    script = soup.find("script", id="__UFRN_LIFECYCLE_SERVERREQUEST__")
    if script is None:
        return {}
    try:
        # Decode JavaScript's JSON string literal, then the JSON it contains.
        # Never evaluate JavaScript or scan arbitrary telephone-looking values.
        text = script.string or ""
        start = text.index("JSON.parse(") + len("JSON.parse(")
        encoded, _ = json.JSONDecoder().raw_decode(text[start:].lstrip())
        data = json.loads(encoded)
        listing = data["app_cldp"]["data"]["classified"]
        contact = listing["contactSections"]
        url_id = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].split(".")[0]
        ids = {str(contact.get("id", "")), str(contact.get("legacyId", ""))}
        if not url_id or url_id not in ids or contact.get("brand") != "seloger":
            return {}
        card = contact["contactCard"]
        result = {}
        phones = card.get("phoneNumbers", [])
        if isinstance(phones, list):
            for value in phones:
                if phone := normalize_phone(value):
                    result["contact_phone"] = phone
                    break
        if card.get("isPrivateOwner") is False:
            for field, key in [("agency_name", "title"), ("agent_name", "subtitle")]:
                value = card.get(key)
                if isinstance(value, str) and value.strip():
                    result[field] = value.strip()
        return result
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}
