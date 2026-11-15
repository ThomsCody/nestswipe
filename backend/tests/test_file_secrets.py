"""Secret files override legacy environments and fail closed when unavailable."""

import pytest

from app.config import Settings, SECRET_FIELDS


@pytest.mark.parametrize("field", sorted(SECRET_FIELDS))
def test_file_overrides_environment_and_preserves_bytes(tmp_path, monkeypatch, field):
    value = " test-only-$value-with-spaces \r\n"
    secret = tmp_path / field
    secret.write_text(value)
    monkeypatch.setenv(field.upper(), "stale-environment-value")
    monkeypatch.setenv(field.upper() + "_FILE", str(secret))
    settings = Settings(_env_file=None)
    actual = getattr(settings, field)
    if hasattr(actual, "get_secret_value"):
        actual = actual.get_secret_value()
    assert actual == value


@pytest.mark.parametrize("kind", ["missing", "directory", "empty-path"])
def test_unreadable_file_never_falls_back_to_environment(tmp_path, monkeypatch, kind):
    path = tmp_path / "missing"
    if kind == "directory":
        path.mkdir()
    monkeypatch.setenv("JWT_SECRET", "must-not-be-used")
    monkeypatch.setenv("JWT_SECRET_FILE", "" if kind == "empty-path" else str(path))
    with pytest.raises(
        RuntimeError, match="Cannot read secret configured by JWT_SECRET_FILE"
    ):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "field", ["jwt_secret", "database_url", "minio_root_user", "minio_root_password"]
)
def test_required_files_cannot_be_empty(tmp_path, monkeypatch, field):
    secret = tmp_path / field
    secret.touch()
    monkeypatch.setenv(field.upper() + "_FILE", str(secret))
    with pytest.raises(RuntimeError, match="must not be empty"):
        Settings(_env_file=None)


def test_optional_file_can_disable_an_integration(tmp_path, monkeypatch):
    secret = tmp_path / "sendgrid"
    secret.touch()
    monkeypatch.setenv("SENDGRID_API_KEY", "stale-value")
    monkeypatch.setenv("SENDGRID_API_KEY_FILE", str(secret))
    assert Settings(_env_file=None).sendgrid_api_key == ""
