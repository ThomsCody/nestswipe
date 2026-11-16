"""Maintenance startup must not run imports or cleanup before verification."""

from unittest.mock import AsyncMock, patch

import pytest

from app.main import app, lifespan


@pytest.mark.asyncio
async def test_maintenance_startup_does_not_start_or_stop_scheduler(monkeypatch):
    monkeypatch.setattr("app.main.settings.scheduler_enabled", False)
    with (
        patch("app.scheduler.start_scheduler", new_callable=AsyncMock) as start,
        patch("app.scheduler.stop_scheduler") as stop,
    ):
        async with lifespan(app):
            pass
        start.assert_not_called()
        stop.assert_not_called()
