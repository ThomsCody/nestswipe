import json
import logging

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract structured housing listing data from email HTML content.
Return a JSON object with the following fields (use null for missing values):
- title: string — short listing title
- price: number — total price in euros (no currency symbol)
- sqm: number — square meters
- bedrooms: integer — number of bedrooms
- city: string — city name
- district: string — district/neighborhood
- location_detail: string — more specific location info
- external_url: string — link to the listing on the source website
- source_id: string — unique identifier from the source (extract from URL if possible)
- floor: integer — floor number (0 for ground floor, null if unknown)
- rooms: integer — total number of rooms (pièces), distinct from bedrooms
- photo_urls: list of strings — URLs of listing photos found in the email
- description: string — brief description of the property

IMPORTANT: Only extract data for residential property listings (apartments/houses for sale).
If the email doesn't contain a listing, return {"is_listing": false}.
If it does, include "is_listing": true along with all extracted fields."""

MULTI_SYSTEM_PROMPT = """You extract structured housing listing data from email HTML content.
An email may contain ONE or MULTIPLE property listings (e.g. digest/alert emails).

Return a JSON object with a single key "listings" containing an array.
Each element should have these fields (use null for missing values):
- title: string — short listing title
- price: number — total price in euros (no currency symbol)
- sqm: number — square meters
- bedrooms: integer — number of bedrooms
- city: string — city name
- district: string — district/neighborhood
- location_detail: string — more specific location info
- external_url: string — link to the listing on the source website (use tracking/redirect URLs if no direct URL is available)
- source_id: string — unique identifier from the source (extract from URL if possible)
- floor: integer — floor number (0 for ground floor, null if unknown)
- rooms: integer — total number of rooms (pièces), distinct from bedrooms
- photo_urls: list of strings — URLs of listing photos found in the email for THIS listing
- description: string — brief description of the property

IMPORTANT:
- Only extract residential property listings (apartments/houses for sale).
- Extract ALL listings present in the email, not just the first one.
- If the email contains no listings at all, return {"listings": []}.
- Each listing should be a separate element in the array."""


PAGE_SYSTEM_PROMPT = """You extract structured housing listing data from a property listing web page.
The text below is the readable content of a listing page on a real estate website.

Return a JSON object with the following fields (use null for missing values):
- is_listing: boolean — true if this page contains a property listing, false otherwise
- title: string — short listing title
- price: number — total price in euros (no currency symbol)
- sqm: number — square meters (surface)
- bedrooms: integer — number of bedrooms (chambres)
- city: string — city name (e.g. "Paris", "Boulogne-Billancourt")
- district: string — the most precise neighborhood or quartier name. For Paris: combine arrondissement + quartier when both are available (e.g. "16e - Auteuil Nord", "9e - Batignolles", "11e - Oberkampf"). Look in breadcrumbs, page headings, URL path, and the description text for quartier names like Auteuil, Passy, Trocadéro, Batignolles, Montmartre, Marais, Bastille, Saint-Germain, etc. For other cities: use the neighborhood or area name.
- location_detail: string — additional location info: street name, nearby metro station, landmarks
- floor: integer — floor number (0 for ground floor / rez-de-chaussée, null if unknown)
- rooms: integer — total number of rooms (pièces), distinct from bedrooms
- description: string — brief description of the property (2-3 sentences max)

IMPORTANT:
- Only extract data for residential property listings (apartments/houses for sale).
- If the page is not a listing (error page, search results, homepage), return {"is_listing": false}.
- Pay close attention to bedrooms vs rooms: "chambres" = bedrooms, "pièces" = rooms.
- Floor: "rez-de-chaussée" / "RDC" = 0, "1er étage" = 1, etc.
- For location: extract the MOST SPECIFIC neighborhood name available. Do not just say "Paris 16e" if the page mentions "Auteuil" or "Auteuil Nord" — include the quartier name.
- LOCATION vs AGENCY ADDRESS: The page will often show BOTH the property location AND the agency/agent office address. These are DIFFERENT. For city, district, and location_detail, use ONLY the property location (where the apartment/house is), NEVER the agency office address. The agency address typically appears near the agent name, phone number, or in a "contact" / "about the agency" section. Ignore it for location fields.
- contact_phone: string — phone number of the agent or agency (formatted as found on page)
- agency_name: string — name of the real estate agency
- agent_name: string — name of the individual agent/contact person"""


class ExtractedListing(BaseModel):
    is_listing: bool
    title: str | None = None
    price: float | None = None
    sqm: float | None = None
    bedrooms: int | None = None
    floor: int | None = None
    rooms: int | None = None
    city: str | None = None
    district: str | None = None
    location_detail: str | None = None
    external_url: str | None = None
    source_id: str | None = None
    photo_urls: list[str] = []
    description: str | None = None
    contact_phone: str | None = None
    agency_name: str | None = None
    agent_name: str | None = None


@task(name="extract_listing")
async def extract_listing(api_key: str, email_html: str, source: str) -> ExtractedListing | None:
    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Source: {source}\n\nEmail HTML:\n{email_html[:15000]}"},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        data = json.loads(content)
        return ExtractedListing(**data)
    except Exception:
        logger.exception("LLM extraction failed")
        return None


@task(name="extract_listings")
async def extract_listings(api_key: str, email_html: str, source: str) -> list[ExtractedListing]:
    """Extract all listings from an email that may contain multiple properties."""
    try:
        client = AsyncOpenAI(api_key=api_key)
        # Use a larger context window for multi-listing emails
        max_chars = 50000
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": MULTI_SYSTEM_PROMPT},
                {"role": "user", "content": f"Source: {source}\n\nEmail HTML:\n{email_html[:max_chars]}"},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            return []
        data = json.loads(content)
        raw_listings = data.get("listings", [])
        results = []
        for item in raw_listings:
            item["is_listing"] = True
            results.append(ExtractedListing(**item))
        return results
    except Exception:
        logger.exception("LLM multi-listing extraction failed")
        return []


@task(name="extract_listing_from_page")
async def extract_listing_from_page(
    api_key: str, page_text: str, source: str
) -> tuple[ExtractedListing | None, int, int]:
    """Extract a single listing from scraped page text using the LLM.

    Returns (listing_or_none, input_tokens, output_tokens).
    """
    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PAGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Source: {source}\n\nPage text:\n{page_text[:30000]}",
                },
            ],
            temperature=0,
        )
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        LLMObs.annotate(
            metadata={"model": "gpt-4o-mini", "source": source},
            metrics={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )
        content = response.choices[0].message.content
        if not content:
            return None, input_tokens, output_tokens
        data = json.loads(content)
        result = ExtractedListing(**data)
        if not result.is_listing:
            return None, input_tokens, output_tokens
        return result, input_tokens, output_tokens
    except Exception:
        logger.exception("LLM page extraction failed")
        return None, 0, 0
