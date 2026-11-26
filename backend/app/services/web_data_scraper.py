"""Opt-in Decodo recovery with a persistent cache and application diagnostics."""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services import listing_metrics

if TYPE_CHECKING:
    from app.services.browser_scraper import ScrapedListing

logger = logging.getLogger(__name__)
API_URL = "https://data.decodo.com/v1/scrape"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_lock = asyncio.Lock()


def _key(url: str) -> str:
    from app.services.browser_scraper import _extract_source_id

    parsed = urlparse(url)
    identity = _extract_source_id(url, "seloger")
    value = f"{parsed.hostname.removeprefix('www.')}:{identity}" if identity else url
    return hashlib.sha256(value.encode()).hexdigest()


def _target(url: str) -> str | None:
    from app.services.browser_scraper import _browser_listing_url

    if not _browser_listing_url(url, "seloger", tracking=True):
        return None
    parsed = urlparse(url)
    # Signed tracking URLs must retain their query until they resolve.
    return urlunparse(
        parsed._replace(
            query=parsed.query if parsed.hostname == "click.by.seloger.com" else "",
            fragment="",
        )
    )


def _state(action: str, key: str, listing: dict | None = None):
    """Read/write parsed listings in a cache shared by backend workers."""
    path = Path(settings.decodo_web_data_state_path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    now = time.time()
    with closing(sqlite3.connect(path, timeout=5)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, expires REAL NOT NULL, listing TEXT NOT NULL)"
        )
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM cache WHERE expires <= ?", (now,))
        if action == "save":
            for cache_key in {key, _key(listing["resolved_url"])}:
                db.execute(
                    "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                    (
                        cache_key,
                        now + settings.decodo_web_data_cache_ttl_seconds,
                        json.dumps(listing),
                    ),
                )
            db.commit()
            return None
        cached = db.execute(
            "SELECT listing FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if cached:
            db.commit()
            return ("cache_hit", json.loads(cached[0]))
        db.commit()
        return ("miss", None)


def _restored(data: dict) -> "ScrapedListing":
    from app.services.browser_scraper import ScrapedListing

    result = ScrapedListing(**data)
    if not result.page_text or not _target(result.resolved_url or ""):
        raise ValueError("Invalid cached listing")
    return result


async def cached_listing(url: str) -> "ScrapedListing | None":
    if not settings.decodo_web_data_api_key.get_secret_value().strip() or not (
        target := _target(url)
    ):
        return None
    try:
        status, data = await asyncio.to_thread(_state, "read", _key(target))
        if status == "cache_hit":
            result = _restored(data)
            listing_metrics.web_data_event("cache_hit")
            return result
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        _failed("state_error", exc)
    return None


def _parse(data: dict, target: str) -> "ScrapedListing":
    from app.services.browser_scraper import (
        ScrapedListing,
        _browser_listing_url,
        _clean_url,
        _extract_page_text,
        _extract_photos_from_html,
        _extract_source_id,
        _is_challenge_html,
    )
    from app.services.listing_contact import extract_contact

    results = data["results"]
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("Unexpected API results")
    item = results[0]
    html = item["content"]
    if (
        item["status_code"] != 200
        or not isinstance(html, str)
        or _is_challenge_html(html)
    ):
        raise ValueError("Listing remained blocked")
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.find("link", rel="canonical")
    final_url = canonical.get("href", "") if canonical else ""
    if not _browser_listing_url(final_url, "seloger"):
        raise ValueError("Missing listing canonical URL")
    source_id = _extract_source_id(final_url, "seloger")
    expected_id = _extract_source_id(target, "seloger")
    if not source_id or (expected_id and source_id != expected_id):
        raise ValueError("Unexpected listing identity")
    if expected_id and urlparse(final_url).hostname.removeprefix("www.") != urlparse(
        target
    ).hostname.removeprefix("www."):
        raise ValueError("Unexpected listing host")
    text = _extract_page_text(html)
    if not text:
        raise ValueError("Empty listing")
    photos, labels = _extract_photos_from_html(html, "seloger")
    return ScrapedListing(
        resolved_url=_clean_url(final_url),
        source_id=source_id,
        page_text=text,
        photo_urls=photos,
        photo_labels=labels,
        **extract_contact(html, final_url),
    )


def _failed(event: str, exc: Exception):
    listing_metrics.web_data_event(event)
    # HTTP exceptions can contain credentials or a signed tracking URL.
    logger.warning(
        "Web Data recovery failed: event=%s error_type=%s",
        event,
        type(exc).__name__,
        extra={"event": "web_data_" + event, "listing_source": "seloger"},
    )


async def recover_listing(
    url: str, *, cache_url: str | None = None
) -> "ScrapedListing | None":
    key = settings.decodo_web_data_api_key.get_secret_value().strip()
    if not key or not (target := _target(url)):
        return None
    # Coalesce concurrent callers within a worker. Cache errors do not prevent
    # recovery, and failed attempts do not suppress subsequent calls.
    async with _lock:
        if cached := await cached_listing(target):
            return cached
        listing_metrics.web_data_event("requests")
        try:
            # No client retries, browser rendering, asset downloads or redirect
            # following. Bearer credentials only go to the fixed HTTPS endpoint.
            async with (
                asyncio.timeout(65),
                httpx.AsyncClient(
                    timeout=60, trust_env=False, follow_redirects=False
                ) as client,
                client.stream(
                    "POST",
                    API_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json={"url": target},
                ) as response,
            ):
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError("API response too large")
            result = _parse(json.loads(body), target)
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            TimeoutError,
        ) as exc:
            _failed("failure", exc)
            return None
        listing_metrics.web_data_event("success")
        try:
            alias = _target(cache_url or "") or target
            await asyncio.to_thread(_state, "save", _key(alias), asdict(result))
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            # A failed cache write must not discard a successfully recovered page.
            _failed("state_error", exc)
        return result
