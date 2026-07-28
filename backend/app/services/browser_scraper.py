import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Sources that require proxy to bypass bot protection
PROXY_SOURCES = {"seloger", "leboncoin"}

REQUEST_TIMEOUT = 30
MAX_PHOTOS_PER_LISTING = 30

# Minimum delay between consecutive scrape requests to a bot-protected source.
# A backlog of queued emails processed back-to-back can otherwise fire dozens
# of requests within seconds and trip anti-bot rate limiting (e.g. SeLoger's
# DataDome returning 403 on click.by.seloger.com redirect resolution).
MIN_REQUEST_INTERVAL_SECONDS = {"seloger": 5.0, "leboncoin": 5.0}
_last_request_at: dict[str, float] = {}

# Response codes that indicate bot-detection/rate-limiting rather than a
# real "page doesn't exist" — worth a short retry instead of giving up.
THROTTLE_STATUS_CODES = {403, 429}
RETRY_DELAYS_SECONDS = [5.0, 15.0]

# Tracking / UTM params to strip from final URLs
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ci", "si", "pi", "at_medium", "at_campaign", "at_creation",
    "at_platform", "at_variant", "at_channel", "xtor",
    "a", "email", "md5",
}


# Patterns to exclude (logos, icons, tracking pixels, etc.)
EXCLUDE_PATTERNS = [
    "logo", "icon", "pixel", "tracking", "spacer", "blank",
    "badge", "favicon", "sprite", "arrow", "button", "banner",
    "footer", "header", "social", "facebook", "twitter",
    "instagram", "linkedin", "google", "apple", "play-store",
    "app-store", "avatar", "profile", "tampon", "contact",
    "1x1", "transparent", "emails/images",
]

# SeLoger's own site (the modern seloger.com template, not the older
# bellesdemeures.com one) runs an AWS SageMaker scene classifier on every
# photo and embeds the result in the page's hydration JSON. We reuse that
# instead of our own GPT-4o-mini vision call where we can.
#
# Only labels we've actually observed in the wild are listed here — anything
# else (including no label at all) falls back to vision classification, so
# an unrecognized label can never cause a real photo to be silently dropped
# or a bad one to be silently kept.
_SELOGER_CLASSIFICATION_RE = re.compile(
    r'classification\\?"\s*:\s*\{\\?"name\\?"\s*:\s*\\?"([A-Z_]+)\\?"'
)
SELOGER_PHOTO_ACCEPT_LABELS = {
    "LIVING_ROOM", "KITCHEN", "BEDROOM", "BATHROOM",
    "EXTERIOR_VIEW", "HALLWAY", "BUILDING_FACADE",
}
SELOGER_PHOTO_REJECT_LABELS = {"LOGO"}

# Warm-up URLs per source (visit homepage first to establish trust)
WARMUP_URLS = {
    "seloger": "https://www.seloger.com/",
    "pap": "https://www.pap.fr/",
    "leboncoin": "https://www.leboncoin.fr/",
}

# Referer to send when fetching a listing directly (not via an email redirect chain)
LISTING_REFERERS = {
    "seloger": "https://www.seloger.com/immobilier/achat/",
    "pap": "https://www.pap.fr/annonce/ventes-immobilieres",
    "leboncoin": "https://www.leboncoin.fr/recherche?category=9&real_estate_type=2",
}

URL_SOURCE_MAP = {
    "seloger.com": "seloger",
    "bellesdemeures.com": "seloger",
    "pap.fr": "pap",
    "consultantsimmobilier.com": "consultantsimmobilier",
    "ap.immo": "consultantsimmobilier",
    "barnes-international.com": "barnes",
    "junot.fr": "junot",
    "leboncoin.fr": "leboncoin",
}


def detect_source_from_url(url: str) -> str | None:
    """Detect listing source from a URL's hostname. Returns None for unknown domains."""
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return None
    hostname = hostname.lower().removeprefix("www.")
    for domain, source in URL_SOURCE_MAP.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return source
    return None


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
    # Maps a photo_urls entry to a pre-approved room label when SeLoger's own
    # scene classifier already confirmed it (see SELOGER_PHOTO_ACCEPT_LABELS).
    # Absence from this dict means "no confident signal, needs vision".
    photo_labels: dict[str, str] = field(default_factory=dict)
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
        if match:
            return match.group(1)
        # bellesdemeures.com redirects from seloger emails
        # URL like: https://www.bellesdemeures.com/annonces/vente/tt-2-tb-1-pl-48258/256203535/
        path = urlparse(url).path
        match = re.search(r"/(\d{6,})/?$", path)
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
    elif source in ("consultantsimmobilier", "barnes", "junot"):
        # ap.immo URL like: https://ap.immo/p/86783633?u=...&p=...
        match = re.search(r"/p/(\d+)", url)
        if match:
            return match.group(1)
        return None
    elif source == "leboncoin":
        # URL like: https://www.leboncoin.fr/vi/3173154827.htm
        # or: https://www.leboncoin.fr/ad/ventes_immobilieres/3183368834
        match = re.search(r"/(?:vi|ad/[^/]+)/(\d+)", url)
        return match.group(1) if match else None
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
    return True


def _normalize_photo_url(url: str) -> str:
    """Remove size constraints from URLs to get higher resolution images."""
    # SeLoger: replace /s/crop/NNNxNNN/ or /s/width/NNN/ with high-res variant
    url = re.sub(r"/s/crop/\d+x\d+/", "/s/width/1280/", url)
    url = re.sub(r"/s/width/\d+/", "/s/width/1280/", url)
    # Remove h=xxx&w=xxx query params
    url = re.sub(r"[&?]h=\d+", "", url)
    url = re.sub(r"[&?]w=\d+", "", url)
    url = re.sub(r"&&+", "&", url)
    url = re.sub(r"[&?]$", "", url)
    # Apimo: prefer -original over -medium/-big variants
    url = re.sub(r"-(?:medium|big)\.(jpe?g|png|webp)", r"-original.\1", url)
    return url


def _extract_photos_from_html(html: str, source: str) -> tuple[list[str], dict[str, str]]:
    """Extract property photo URLs (and any pre-approved room labels) from rendered listing page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove recommendation / cross-sell / similar listings sections
    # so we only get photos from the current listing.
    to_remove = []
    for tag in soup.find_all(["section", "div", "aside"], class_=True):
        classes = " ".join(tag["class"]).lower()
        if any(kw in classes for kw in ("crosslink", "cross-sell", "similar", "recommend", "suggestion")):
            to_remove.append(tag)
    for tag in to_remove:
        tag.decompose()

    seen_base: set[str] = set()
    photos: list[str] = []

    # Inline JSON/JS data — the modern seloger.com template embeds its full
    # photo gallery in a script tag with double-escaped JSON (\" becomes
    # \\"), alongside SeLoger's own scene classification label for each
    # photo.  When present, this JSON is the *only* source of real gallery
    # photos on that template — every plain <img>/<source>/og:image tag on
    # the page is a UI icon or map thumbnail, not a property photo, so we
    # skip the generic scan entirely to avoid sending junk to vision.
    mms_seloger_urls: list[str] = []
    raw_labels: dict[str, str] = {}
    for script in soup.find_all("script"):
        text = script.string or ""
        if "mms.seloger" not in text:
            continue
        for m in re.finditer(
            r"https?://mms\.seloger\.com/[^\"\s\\]+\.(?:jpe?g|png|webp)[^\"\s\\]*",
            text,
        ):
            url = m.group(0)
            mms_seloger_urls.append(url)
            window = text[m.end():m.end() + 300]
            label_match = _SELOGER_CLASSIFICATION_RE.search(window)
            if label_match:
                raw_labels[url] = label_match.group(1)

    if mms_seloger_urls:
        candidate_urls = mms_seloger_urls
    else:
        # Older templates (e.g. bellesdemeures.com) render their gallery as
        # plain HTML, so fall back to scanning generic image attributes.
        candidate_urls = []

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

    # Drop images SeLoger's own classifier already confirmed are not property
    # photos (e.g. agency logos) before they ever reach dedup/download.
    candidate_urls = [
        url for url in candidate_urls
        if raw_labels.get(url) not in SELOGER_PHOTO_REJECT_LABELS
    ]

    # Filter, deduplicate, normalize
    # Use the filename (last path segment) as dedup key so different sizes
    # of the same image (e.g. v.seloger.com/s/crop/48x48/.../HASH.jpg vs
    # /s/crop/933x645/.../HASH.jpg) are treated as one image.
    photo_labels: dict[str, str] = {}
    for url in candidate_urls:
        if not _is_valid_photo(url, source):
            continue
        normalized = _normalize_photo_url(url)
        base = normalized.split("?")[0]
        filename = base.rsplit("/", 1)[-1]
        if filename in seen_base:
            continue
        seen_base.add(filename)
        photos.append(normalized)
        label = raw_labels.get(url)
        if label in SELOGER_PHOTO_ACCEPT_LABELS:
            photo_labels[normalized] = label

    photos = photos[:MAX_PHOTOS_PER_LISTING]
    photo_labels = {url: label for url, label in photo_labels.items() if url in photos}
    return photos, photo_labels


async def _throttle(source: str) -> None:
    """Enforce a minimum gap since the last request to this source."""
    min_interval = MIN_REQUEST_INTERVAL_SECONDS.get(source)
    if not min_interval:
        return
    loop = asyncio.get_event_loop()
    last = _last_request_at.get(source)
    if last is not None:
        wait = min_interval - (loop.time() - last)
        if wait > 0:
            await asyncio.sleep(wait)
    _last_request_at[source] = loop.time()


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

    use_proxy = source in PROXY_SOURCES and settings.proxy_url
    proxy = settings.proxy_url if use_proxy else None
    if use_proxy:
        logger.info("Using residential proxy for source=%s", source)

    try:
        async with AsyncSession(impersonate="chrome", proxy=proxy) as session:
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
            listing_headers = HEADERS.copy()
            if referer := LISTING_REFERERS.get(source):
                listing_headers["Referer"] = referer

            for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
                await _throttle(source)
                resp = await session.get(
                    tracking_url,
                    headers=listing_headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                if resp.status_code not in THROTTLE_STATUS_CODES:
                    break
                if attempt == len(RETRY_DELAYS_SECONDS):
                    break
                delay = RETRY_DELAYS_SECONDS[attempt]
                logger.warning(
                    "Possible rate-limiting (status %d) for %s, retrying in %.0fs (attempt %d/%d)",
                    resp.status_code, tracking_url, delay, attempt + 1, len(RETRY_DELAYS_SECONDS),
                )
                await asyncio.sleep(delay)

            # Capture the final URL after all redirects
            final_url = str(resp.url)
            if final_url and final_url != tracking_url:
                logger.info("Resolved URL: %s -> %s", tracking_url, final_url)

            result.resolved_url = _clean_url(final_url)
            result.source_id = _extract_source_id(final_url, source)

            if resp.status_code == 200:
                result.photo_urls, result.photo_labels = _extract_photos_from_html(resp.text, source)
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
                # TEMPORARY diagnostics: figure out whether SeLoger's block is a
                # JS-challenge interstitial (DataDome headers/cookie present) vs
                # a hard IP-level block (plain WAF page, no DataDome markers).
                datadome_headers = {
                    k: v for k, v in resp.headers.items() if "datadome" in k.lower()
                }
                logger.warning(
                    "Diag for %s: final_url=%s datadome_headers=%s set_cookie=%s body_snippet=%r",
                    tracking_url,
                    final_url,
                    datadome_headers,
                    resp.headers.get("set-cookie", ""),
                    resp.text[:500] if resp.text else "",
                )

    except Exception:
        logger.exception("Failed to scrape listing from %s", tracking_url)

    return result
