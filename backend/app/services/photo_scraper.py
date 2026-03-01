import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Known CDN domains for property photos
PHOTO_CDNS = [
    "mms.seloger.com",
    "cdn.pap.fr/photos",
]

# Patterns to exclude (logos, icons, tracking pixels, etc.)
EXCLUDE_PATTERNS = [
    "logo", "icon", "pixel", "tracking", "spacer", "blank",
    "badge", "favicon", "sprite", "arrow", "button", "banner",
    "footer", "header", "social", "facebook", "twitter",
    "instagram", "linkedin", "google", "apple", "play-store",
    "app-store", "avatar", "profile", "tampon", "contact",
    "emails/images",
]


def _is_property_photo(url: str) -> bool:
    """Check if a URL looks like a property listing photo."""
    lower = url.lower()

    # Must be from a known photo CDN
    if not any(cdn in lower for cdn in PHOTO_CDNS):
        return False

    # Must look like an image
    if not re.search(r"\.(jpe?g|png|webp)", lower):
        return False

    # Exclude known non-photo patterns
    if any(p in lower for p in EXCLUDE_PATTERNS):
        return False

    return True


def _normalize_url(url: str) -> str:
    """Remove size constraints from URLs to get higher resolution images."""
    # SeLoger: remove h=xxx&w=xxx params to get full-size
    url = re.sub(r'[&?]h=\d+', '', url)
    url = re.sub(r'[&?]w=\d+', '', url)
    # Clean up double && or trailing &
    url = re.sub(r'&&+', '&', url)
    url = re.sub(r'[&?]$', '', url)
    return url


def extract_photos_from_html(html: str, source: str) -> list[str]:
    """Extract all property photo URLs from email HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    seen_base_urls: set[str] = set()
    photos: list[str] = []

    # Collect all candidate URLs from various sources
    candidate_urls: list[str] = []

    # 1. img src attributes
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy", "data-original"):
            url = img.get(attr, "")
            if url:
                candidate_urls.append(url)

    # 2. srcset attributes
    for img in soup.find_all("img"):
        srcset = img.get("srcset", "")
        for part in srcset.split(","):
            url = part.strip().split(" ")[0]
            if url:
                candidate_urls.append(url)

    # 3. Background images in style attributes
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        urls = re.findall(r'url\(["\']?(https?://[^"\')\s]+)', style)
        candidate_urls.extend(urls)

    # 4. Links to images
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if re.search(r"\.(jpe?g|png|webp)", href.lower()):
            candidate_urls.append(href)

    # Filter and deduplicate
    for url in candidate_urls:
        if not _is_property_photo(url):
            continue
        normalized = _normalize_url(url)
        # Deduplicate by base URL (without query params for CDN images)
        base = normalized.split("?")[0]
        if base in seen_base_urls:
            continue
        seen_base_urls.add(base)
        photos.append(normalized)

    logger.info("Extracted %d property photos from %s email HTML", len(photos), source)
    return photos
