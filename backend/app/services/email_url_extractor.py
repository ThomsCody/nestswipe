"""Extract listing URLs from email HTML using LLM."""

import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract property listing URLs from email HTML content.
The email is an alert from a real estate website containing one or more property listings.

Return a JSON object with a single key "urls" containing an array of URL strings.

Rules:
- Return exactly ONE URL per property listing (the main link to view the listing).
- If the only link available is a tracking/redirect URL (e.g. click.by.seloger.com/?qs=...), use that.
- Do NOT include: unsubscribe, social media, app store, image, alert management, login, or homepage links.
- If no listing URLs are found, return {"urls": []}.
- If a listing has multiple links (title link, image link, "see more" link), pick just ONE."""


async def extract_listing_urls(api_key: str, html: str, source: str) -> list[str]:
    """Extract listing URLs from email HTML using LLM.

    Returns a list of candidate URLs pointing to individual listing pages.
    """
    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Source: {source}\n\nEmail HTML:\n{html[:50000]}",
                },
            ],
            temperature=0,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        if not content:
            return []
        data = json.loads(content)
        urls = data.get("urls", [])
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if isinstance(url, str) and url not in seen:
                seen.add(url)
                unique.append(url)
        logger.info("LLM extracted %d listing URL(s) from %s email", len(unique), source)
        return unique
    except Exception:
        logger.exception("LLM URL extraction failed")
        return []
