"""Extract listing URLs from email HTML.

Strategy: parse all <a> tags from the email, build a compact numbered list of
(truncated_href, visible_text) pairs, then ask the LLM to return the indices of
links pointing to property listings.  One LLM call, small input, tiny output.
"""

import json
import logging

from bs4 import BeautifulSoup
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are given a numbered list of links extracted from a real-estate alert email.
Each line has the format:  INDEX | URL (may be truncated) | VISIBLE_TEXT

Identify links that point to **individual property listings** (apartments, houses, etc.).
Multiple links may point to the same listing (e.g. image link, title link, price link,
"Voir l'annonce" button).  For each *distinct* listing, return exactly ONE index.

Return a JSON object: {"indices": [3, 7, 15]}

Rules:
- Pick the most descriptive link for each listing (prefer the one with a title or
  "Voir l'annonce" / "Lire la suite" text over bare image links).
- If the only available link is a tracking/redirect URL (e.g. click.by.seloger.com),
  that is fine — return its index.
- Do NOT include: unsubscribe, manage alerts, social media, app store, promotional,
  mortgage calculator, homepage, or legal/privacy links.
- If no listing links are found, return {"indices": []}."""

# Max characters to show for each URL in the LLM table
_URL_DISPLAY_LEN = 90


def _extract_link_table(html: str) -> list[tuple[int, str, str]]:
    """Parse <a> tags from HTML and return (index, href, visible_text) tuples."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[int, str, str]] = []
    for i, tag in enumerate(soup.find_all("a", href=True)):
        href = tag["href"].strip()
        if not href or not href.startswith("http"):
            continue
        text = tag.get_text(separator=" ", strip=True)[:120]
        links.append((i, href, text))
    return links


def _format_link_table(links: list[tuple[int, str, str]]) -> str:
    """Format links as a compact text table for the LLM (URLs truncated)."""
    lines = []
    for idx, href, text in links:
        display_text = text if text else "(image/empty)"
        short_href = href[:_URL_DISPLAY_LEN] + ("..." if len(href) > _URL_DISPLAY_LEN else "")
        lines.append(f"{idx} | {short_href} | {display_text}")
    return "\n".join(lines)


async def extract_listing_urls(api_key: str, html: str, source: str) -> list[str]:
    """Extract listing URLs from email HTML.

    Parses all <a> tags, sends a compact link table to the LLM which returns
    indices of listing links, then maps indices back to full URLs.
    """
    links = _extract_link_table(html)
    if not links:
        logger.info("No <a> tags found in %s email", source)
        return []

    logger.info("Extracted %d <a> tags from %s email", len(links), source)

    # Build index→href lookup
    href_by_idx: dict[int, str] = {idx: href for idx, href, _ in links}

    link_table = _format_link_table(links)

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Source: {source}\n\nLinks:\n{link_table}",
                },
            ],
            temperature=0,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM returned empty response for %s email", source)
            return []

        data = json.loads(content)
        indices = data.get("indices", [])

        # Map indices back to full URLs, deduplicate
        seen: set[str] = set()
        urls: list[str] = []
        for idx in indices:
            if not isinstance(idx, int):
                continue
            href = href_by_idx.get(idx)
            if href and href not in seen:
                seen.add(href)
                urls.append(href)

        logger.info(
            "LLM selected %d listing URL(s) from %d links in %s email",
            len(urls),
            len(links),
            source,
        )
        return urls

    except Exception:
        logger.exception("LLM URL extraction failed for %s email", source)
        return []
