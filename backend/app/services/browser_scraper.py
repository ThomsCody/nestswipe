import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30

# Tracking / UTM params to strip from final URLs
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ci", "si", "pi", "at_medium", "at_campaign", "at_creation",
    "at_platform", "at_variant", "at_channel", "xtor",
    "a", "email", "md5",
}

# Known CDN domains for property photos
SELOGER_PHOTO_CDNS = ["mms.seloger.com"]
PAP_PHOTO_CDNS = ["cdn.pap.fr/photos"]
CI_PHOTO_CDNS = ["media.apimo.pro/cache"]

# Patterns to exclude (logos, icons, tracking pixels, etc.)
EXCLUDE_PATTERNS = [
    "logo", "icon", "pixel", "tracking", "spacer", "blank",
    "badge", "favicon", "sprite", "arrow", "button", "banner",
    "footer", "header", "social", "facebook", "twitter",
    "instagram", "linkedin", "google", "apple", "play-store",
    "app-store", "avatar", "profile", "tampon", "contact",
    "1x1", "transparent", "emails/images",
]

# Warm-up URLs per source (visit homepage first to establish trust)
WARMUP_URLS = {
    "seloger": "https://www.seloger.com/",
    "pap": "https://www.pap.fr/",
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


PAGE_TEXT_MAX_CHARS = 30_000


@dataclass
class ScrapedListing:
    resolved_url: str | None = None
    source_id: str | None = None
    photo_urls: list[str] = field(default_factory=list)
    page_text: str | None = None


def _clean_url(url: str) -> str:
    """Strip tracking/UTM parameters from a URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k.lower() not in STRIP_PARAMS}
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query, fragment=""))


def _extract_source_id(url: str, source: str) -> str | None:
    """Extract the listing source ID from a resolved URL."""
    if source == "seloger":
        # URL like: https://www.seloger.com/annonces/achat/.../228288697.htm
        match = re.search(r"/(\d{6,})\.htm", url)
        return match.group(1) if match else None
    elif source == "pap":
        # URL like: https://www.pap.fr/annonces/-r461702551
        match = re.search(r"-r(\d+)", url)
        if match:
            return match.group(1)
        # Resolved URL like: https://www.pap.fr/annonce/vente-...-g37783
        match = re.search(r"-g(\d+)$", url.rstrip("/"))
        if match:
            return match.group(1)
        return None
    return None


def _is_valid_photo(url: str, source: str) -> bool:
    """Check if a URL looks like a valid property photo."""
    lower = url.lower()
    if not lower.startswith("http"):
        return False
    if not re.search(r"\.(jpe?g|png|webp)", lower):
        return False
    if any(p in lower for p in EXCLUDE_PATTERNS):
        return False
    # Must be from a known CDN for the source
    cdns = {
        "seloger": SELOGER_PHOTO_CDNS,
        "pap": PAP_PHOTO_CDNS,
        "consultantsimmobilier": CI_PHOTO_CDNS,
    }.get(source, [])
    if not any(cdn in lower for cdn in cdns):
        return False
    return True


def _normalize_photo_url(url: str) -> str:
    """Remove size constraints from URLs to get higher resolution images."""
    url = re.sub(r"[&?]h=\d+", "", url)
    url = re.sub(r"[&?]w=\d+", "", url)
    url = re.sub(r"&&+", "&", url)
    url = re.sub(r"[&?]$", "", url)
    # Apimo: prefer -original over -medium/-big variants
    url = re.sub(r"-(?:medium|big)\.(jpe?g|png|webp)", r"-original.\1", url)
    return url


def _extract_photos_from_html(html: str, source: str) -> list[str]:
    """Extract property photo URLs from rendered listing page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    seen_base: set[str] = set()
    photos: list[str] = []

    # Collect candidate URLs from various HTML attributes
    candidate_urls: list[str] = []

    # img src / data-src attributes
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy", "data-original"):
            val = img.get(attr, "")
            if val:
                candidate_urls.append(val)
        # srcset
        srcset = img.get("srcset", "")
        for part in srcset.split(","):
            url = part.strip().split(" ")[0]
            if url:
                candidate_urls.append(url)

    # picture > source srcset
    for source_tag in soup.find_all("source"):
        srcset = source_tag.get("srcset", "")
        for part in srcset.split(","):
            url = part.strip().split(" ")[0]
            if url:
                candidate_urls.append(url)

    # Background images in style attributes
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        urls = re.findall(r'url\(["\']?(https?://[^"\')\s]+)', style)
        candidate_urls.extend(urls)

    # og:image meta tags (main photo)
    for meta in soup.find_all("meta", property="og:image"):
        content = meta.get("content", "")
        if content:
            candidate_urls.insert(0, content)

    # Filter, deduplicate, normalize
    for url in candidate_urls:
        if not _is_valid_photo(url, source):
            continue
        normalized = _normalize_photo_url(url)
        base = normalized.split("?")[0]
        if base in seen_base:
            continue
        seen_base.add(base)
        photos.append(normalized)

    return photos[:20]


def _extract_page_text(html: str) -> str | None:
    """Extract readable text from listing page HTML, stripping nav/scripts."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text or len(text) < 50:
        return None
    return text[:PAGE_TEXT_MAX_CHARS]



async def scrape_listing(tracking_url: str, source: str) -> ScrapedListing:
    """
    Fetch a listing URL using curl-impersonate (Chrome TLS fingerprint),
    follow redirects, capture the final permanent URL and scrape photos.
    """
    result = ScrapedListing()

    try:
        async with AsyncSession(impersonate="chrome") as session:
            # Warm up: visit the homepage to establish cookies/trust score
            warmup_url = WARMUP_URLS.get(source)
            if warmup_url:
                try:
                    await session.get(
                        warmup_url,
                        headers=HEADERS,
                        timeout=REQUEST_TIMEOUT,
                    )
                    logger.debug("Warm-up request to %s completed", warmup_url)
                except Exception:
                    logger.debug("Warm-up request to %s failed (non-critical)", warmup_url)

            # Fetch the actual listing page (follows redirects automatically)
            resp = await session.get(
                tracking_url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            # Capture the final URL after all redirects
            final_url = str(resp.url)
            if final_url and final_url != tracking_url:
                logger.info("Resolved URL: %s -> %s", tracking_url, final_url)

            result.resolved_url = _clean_url(final_url)
            result.source_id = _extract_source_id(final_url, source)

            if resp.status_code == 200:
                result.photo_urls = _extract_photos_from_html(resp.text, source)
                result.page_text = _extract_page_text(resp.text)
                logger.info(
                    "Scraped listing: url=%s source_id=%s photos=%d page_text=%d chars",
                    result.resolved_url, result.source_id, len(result.photo_urls),
                    len(result.page_text) if result.page_text else 0,
                )
            else:
                logger.warning(
                    "Page load failed (status %d) for %s",
                    resp.status_code, tracking_url,
                )

    except Exception:
        logger.exception("Failed to scrape listing from %s", tracking_url)

    return result
