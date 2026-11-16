"""Provider-independent operations and configuration safety."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config import settings
from app.services.photo_storage import get_storage, upload_photo, _operator


@pytest.mark.parametrize("backend", ["memory", "fs"])
def test_storage_backend_roundtrip(monkeypatch, tmp_path, backend):
    monkeypatch.setattr(settings, "storage_backend", backend)
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    storage = get_storage()
    assert get_storage() is storage
    key = upload_photo(storage, b"image-bytes")
    assert storage.read(key) == b"image-bytes"
    assert storage.stat(key).content_length == 11
    storage.delete(key)
    assert not storage.exists(key)


def test_provider_options_file(monkeypatch, tmp_path):
    path = tmp_path / "options.json"
    path.write_text(
        json.dumps(
            {"bucket": "fixture-bucket", "credential_path": "/run/secrets/cloud"}
        )
    )
    monkeypatch.setattr(settings, "storage_backend", "gcs")
    monkeypatch.setattr(settings, "storage_options_file", str(path))
    with patch("app.services.photo_storage._operator") as factory:
        get_storage()
        backend, options = factory.call_args.args
        assert backend == "gcs"
        assert dict(options)["credential_path"] == "/run/secrets/cloud"


def test_s3_never_uses_ambient_credentials(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    with patch("app.services.photo_storage._operator") as factory:
        get_storage()
        options = dict(factory.call_args.args[1])
        assert options["disable_config_load"] == "true"
        assert options["disable_ec2_metadata"] == "true"


def test_config_failure_does_not_echo_secret():
    with patch(
        "app.services.photo_storage.opendal.Operator",
        side_effect=ValueError("secret-credential"),
    ):
        with pytest.raises(RuntimeError, match="configuration is invalid") as error:
            _operator("s3", (("secret_access_key", "secret-credential"),))
    assert "secret-credential" not in str(error.value)


def test_placeholder_does_not_overwrite_on_access_error():
    from app.services.photo_cleanup import _ensure_placeholder

    storage = SimpleNamespace(stat=lambda key: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        _ensure_placeholder(storage)
