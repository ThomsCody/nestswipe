"""Restore bare Junot/Apimo URLs using the listing owner's emailed authentication.

Dry run by default; pass --apply to save only independently verified replacements.
No listing contents, photos, favorites, or timestamps are modified.
"""

import argparse
import asyncio
import json
import logging
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from curl_cffi.requests import AsyncSession
from sqlalchemy import select

from app.database import async_session
from app.models.listing import Listing
from app.models.user import User
from app.services.browser_scraper import _extract_page_text, _extract_source_id
from app.services.email_processor import _extract_html_body, _get_gmail_service
from app.services.email_url_extractor import _extract_link_table


def authenticated_listing_url(bare: str, authenticated: str) -> str:
    """Use only credentials received by this same owner, never guessed values."""
    target, entry = urlsplit(bare), urlsplit(authenticated)
    params = parse_qs(entry.query)
    if (
        target.scheme != "https"
        or target.hostname != "ap.immo"
        or entry.hostname != "ap.immo"
        or not params.get("u")
        or not params.get("p")
    ):
        raise ValueError("Not an authenticated Apimo listing link")
    return urlunsplit(
        target._replace(
            query=urlencode({k: params[k] for k in ("u", "p")}, doseq=True), fragment=""
        )
    )


async def email_authentication(service):
    page = None
    while True:
        response = await asyncio.to_thread(
            service.users()
            .messages()
            .list(
                userId="me",
                q="in:anywhere from:junot.fr",
                includeSpamTrash=True,
                maxResults=100,
                pageToken=page,
            )
            .execute
        )
        for meta in response.get("messages", []):
            msg = await asyncio.to_thread(
                service.users()
                .messages()
                .get(userId="me", id=meta["id"], format="full")
                .execute
            )
            for _, url, text in _extract_link_table(_extract_html_body(msg["payload"])):
                if text.casefold() not in {"lire la suite", "découvrir le bien"}:
                    continue
                # Only listing buttons, never preference/unsubscribe actions.
                async with AsyncSession(impersonate="chrome") as client:
                    for _ in range(6):
                        parsed = urlsplit(url)
                        if parsed.scheme != "https" or parsed.hostname not in {
                            "r.info.junot.fr",
                            "ap.immo",
                        }:
                            break
                        params = parse_qs(parsed.query)
                        if (
                            parsed.hostname == "ap.immo"
                            and params.get("u")
                            and params.get("p")
                        ):
                            yield url
                            break
                        r = await client.get(url, allow_redirects=False, timeout=30)
                        if r.status_code not in {
                            301,
                            302,
                            303,
                            307,
                            308,
                        } or not r.headers.get("location"):
                            break
                        url = urljoin(url, r.headers["location"])
        page = response.get("nextPageToken")
        if not page:
            break


async def repair(apply: bool):
    # Imported scraper/HTTP libraries can log authenticated URLs. Only print
    # explicit, token-free summaries in this maintenance command.
    logging.disable(logging.CRITICAL)
    async with async_session() as db:
        rows = (
            (
                await db.execute(
                    select(Listing).where(
                        Listing.source == "junot", Listing.external_url.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        pending = [
            r
            for r in rows
            if urlsplit(r.external_url).hostname == "ap.immo"
            and not urlsplit(r.external_url).query
        ]
        users = (
            (
                await db.execute(
                    select(User).where(User.id.in_({r.user_id for r in pending}))
                )
            )
            .scalars()
            .all()
        )
        repaired = []
        for user in users:
            if not user.gmail_refresh_token:
                continue
            service = await asyncio.to_thread(
                _get_gmail_service, user.gmail_refresh_token
            )
            owner_rows = [r for r in pending if r.user_id == user.id]
            async for entry in email_authentication(service):
                for listing in owner_rows[:]:
                    url = authenticated_listing_url(listing.external_url, entry)
                    expected = _extract_source_id(listing.external_url, "junot")
                    if not expected or (
                        listing.source_id and listing.source_id != expected
                    ):
                        continue
                    async with AsyncSession(impersonate="chrome") as client:
                        r = await client.get(url, allow_redirects=True, timeout=30)
                    if (
                        r.status_code == 200
                        and urlsplit(str(r.url)).hostname == "ap.immo"
                        and _extract_source_id(str(r.url), "junot") == expected
                        and _extract_page_text(r.text)
                    ):
                        if apply:
                            listing.external_url = url
                        repaired.append(listing.id)
                        owner_rows.remove(listing)
                if not owner_rows:
                    break
        if apply:
            await db.commit()
        print(
            json.dumps(
                {
                    "applied": apply,
                    "verified_listing_ids": repaired,
                    "unrepaired_listing_ids": [
                        r.id for r in pending if r.id not in repaired
                    ],
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    try:
        asyncio.run(repair(parser.parse_args().apply))
    except Exception as exc:
        # HTTP/DB exception strings may contain authentication URLs.
        print(json.dumps({"error_type": type(exc).__name__, "completed": False}))
        raise SystemExit(1) from None
