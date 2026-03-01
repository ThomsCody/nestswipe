import json
import logging

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
