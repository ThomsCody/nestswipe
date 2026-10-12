"""Choose URLs that remain usable outside the scraper's authenticated session."""

from urllib.parse import urlsplit


def reusable_listing_url(original: str, resolved: str | None, source: str) -> str:
    if source in {"junot", "barnes", "consultantsimmobilier"} and any(
        urlsplit(url).hostname == "ap.immo" for url in (original, resolved or "")
    ):
        # Apimo consumes u/p authentication, sets a cookie, then redirects to a
        # bare URL. Keep the email entry point, including Junot's tracking wrapper.
        return original
    return resolved or original
