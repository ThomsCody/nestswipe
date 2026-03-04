from unittest.mock import AsyncMock, patch


async def test_get_settings_defaults(client, auth_headers, test_user):
    resp = await client.get("/api/v1/settings", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["openai_api_key_set"] is False
    assert data["openai_api_key_masked"] is None
    assert data["gmail_connected"] is False


async def test_update_openai_api_key(client, auth_headers, test_user):
    mock_models = AsyncMock()
    mock_models.list = AsyncMock(return_value=[])

    mock_client_instance = AsyncMock()
    mock_client_instance.models = mock_models

    with patch("app.api.settings.AsyncOpenAI", return_value=mock_client_instance):
        resp = await client.put(
            "/api/v1/settings",
            json={"openai_api_key": "sk-test123456"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["openai_api_key_set"] is True
    assert data["openai_api_key_masked"].startswith("sk-t")
