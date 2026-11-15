"""The maintenance refactor must retain redirect restrictions and its hop limit."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from scripts.repair_junot_urls import resolve_email_authentication


@pytest.mark.parametrize(
    "target",
    ["http://ap.immo/p/1?u=test&p=test", "https://example.com/private"],
)
async def test_redirect_outside_allowed_https_hosts_is_not_followed(target):
    client = AsyncMock()
    client.get.return_value = Mock(status_code=302, headers={"location": target})
    with patch("scripts.repair_junot_urls.AsyncSession") as session:
        session.return_value.__aenter__.return_value = client
        assert (
            await resolve_email_authentication("https://r.info.junot.fr/link") is None
        )
    client.get.assert_awaited_once()


async def test_authenticated_destination_is_returned_without_requesting_it():
    target = "https://ap.immo/p/1?u=test&p=test"
    client = AsyncMock()
    client.get.return_value = Mock(status_code=302, headers={"location": target})
    with patch("scripts.repair_junot_urls.AsyncSession") as session:
        session.return_value.__aenter__.return_value = client
        assert (
            await resolve_email_authentication("https://r.info.junot.fr/link") == target
        )
    client.get.assert_awaited_once_with(
        "https://r.info.junot.fr/link", allow_redirects=False, timeout=30
    )


async def test_redirect_loop_stops_after_six_requests():
    client = AsyncMock()
    client.get.return_value = Mock(status_code=302, headers={"location": "/loop"})
    with patch("scripts.repair_junot_urls.AsyncSession") as session:
        session.return_value.__aenter__.return_value = client
        assert (
            await resolve_email_authentication("https://r.info.junot.fr/loop") is None
        )
    assert client.get.await_count == 6
