"""Mechanical URL extraction from email HTML — no LLM needed."""

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Domains (and subdomains) that host actual listing pages per source
SOURCE_DOMAINS = {
    "seloger": ["seloger.com"],
    "pap": ["pap.fr"],
    "consultantsimmobilier": ["consultantsimmobilier.com", "apimo.net"],
}

# Known tracking / redirect domains that wrap listing URLs
TRACKING_DOMAINS = [
    "mailing.seloger.com",
    "click.pap.fr",
    "email.pap.fr",
    "track.",
    "click.",
    "redirect.",
    "lnk.",
    "trk.",
    "r.mail.",
]

# Schemes and prefixes to always exclude
EXCLUDE_PREFIXES = [
    "mailto:",
    "tel:",
    "javascript:",
    "data:",
    "#",
]

# Domains to always exclude (social, unsubscribe, generic)
EXCLUDE_DOMAINS = [
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "google.com/maps",
    "apple.com",
    "play.google.com",
    "apps.apple.com",
]

# Path patterns to exclude
EXCLUDE_PATH_PATTERNS = [
    "/unsubscribe",
    "/desabonnement",
    "/desinscription",
    "/preferences",
    "/mes-alertes",
    "/mes-recherches",
    "/login",
    "/signup",
    "/contact",
    "/cgu",
    "/politique-de-confidentialite",
    "/privacy",
]


def _is_from_source_domain(url: str, source: str) -> bool:
    """Check if URL belongs to a known domain for this source."""
    domains = SOURCE_DOMAINS.get(source, [])
    hostname = urlparse(url).hostname or ""
    return any(hostname == d or hostname.endswith("." + d) for d in domains)


def _is_tracking_url(url: str) -> bool:
    """Check if URL is from a known tracking/redirect domain."""
    hostname = urlparse(url).hostname or ""
    return any(t in hostname for t in TRACKING_DOMAINS)


def _should_exclude(url: str) -> bool:
    """Check if URL should be excluded."""
    lower = url.lower().strip()
    if any(lower.startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    hostname = urlparse(lower).hostname or ""
    if any(d in hostname for d in EXCLUDE_DOMAINS):
        return True
    path = urlparse(lower).path
    if any(p in path for p in EXCLUDE_PATH_PATTERNS):
        return True
    # Exclude image files
    if re.search(r"\.(png|gif|jpg|jpeg|svg|ico|webp|bmp)(\?|$)", path):
        return True
    return False


def _base_url(url: str) -> str:
    """Normalize URL for deduplication: strip fragment and common tracking params."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def extract_listing_urls(html: str, source: str) -> list[str]:
    """Extract candidate listing URLs from email HTML.

    Returns deduplicated URLs from the source domain or known tracking domains.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or _should_exclude(href):
            continue
        if not href.startswith("http"):
            continue
        if not (_is_from_source_domain(href, source) or _is_tracking_url(href)):
            continue

        base = _base_url(href)
        if base in seen:
            continue
        seen.add(base)
        urls.append(href)

    logger.info("Extracted %d candidate listing URL(s) from %s email", len(urls), source)
    return urls
