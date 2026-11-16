import json
import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


SECRET_FIELDS = {
    "database_url",
    "storage_access_key",
    "storage_secret_key",
    "jwt_secret",
    "proxy_user",
    "proxy_password",
    "decodo_api_key",
    "sendgrid_api_key",
    "google_client_secret",
}
REQUIRED_SECRETS = {
    "database_url",
    "storage_access_key",
    "storage_secret_key",
    "jwt_secret",
}


def file_secrets() -> dict[str, str]:
    """Explicit *_FILE settings take precedence and never fall back on read errors."""
    values = {}
    for field in SECRET_FIELDS:
        variable = field.upper() + "_FILE"
        if variable not in os.environ:
            continue
        try:
            value = Path(os.environ[variable]).read_bytes().decode("utf-8")
        except (OSError, ValueError):
            raise RuntimeError(f"Cannot read secret configured by {variable}") from None
        if not value and field in REQUIRED_SECRETS:
            raise RuntimeError(f"Secret configured by {variable} must not be empty")
        values[field] = value
    return values


class Settings(BaseSettings):
    # Database
    database_url: str = (
        "postgresql+psycopg://rosen:rosen_secret@postgres:5432/nestswipe"
    )

    # Provider-neutral storage; Garage uses the S3 backend.
    storage_backend: str = "s3"
    storage_options_file: str | None = None
    storage_root: str = "/"
    storage_endpoint: str = "garage:3900"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "listing-photos"
    storage_secure: bool = False
    storage_region: str = "garage"
    scheduler_enabled: bool = True

    # JWT
    jwt_secret: str = "change-me-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # CORS / Frontend
    allowed_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    # Proxy (rotating residential, used for seloger.com only)
    proxy_host: str = ""
    proxy_user: str = ""
    proxy_password: str = ""
    # Reporting API only; never used as proxy credentials.
    decodo_api_key: SecretStr = SecretStr("")

    # Internal persistent Chromium service; no public port or paid scraping API.
    # Legacy env name; shared renderer handles SeLoger, PAP and Leboncoin.
    seloger_browser_url: str = ""

    @property
    def proxy_url(self) -> str:
        if self.proxy_host and self.proxy_user and self.proxy_password:
            return f"http://{self.proxy_user}:{self.proxy_password}@{self.proxy_host}"
        return ""

    # SendGrid
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""

    # Email polling
    email_poll_interval_minutes: int = 5

    # Periodic access probes run only in production. No LLM or listing writes.
    listing_probes_enabled: bool = False

    # OAuth JSON path
    oauth_json_path: str = "/app/oauth.json"

    model_config = {"env_file": ".env"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        return (
            init_settings,
            file_secrets,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    def load_oauth_json(self) -> None:
        """Load Google OAuth credentials from oauth.json if not set via env."""
        path = Path(self.oauth_json_path)
        if path.exists() and (
            not self.google_client_id or not self.google_client_secret
        ):
            data = json.loads(path.read_text())
            web = data.get("web", {})
            self.google_client_id = web.get("client_id", self.google_client_id)
            self.google_client_secret = web.get(
                "client_secret", self.google_client_secret
            )
            redirect_uris = web.get("redirect_uris", [])
            if redirect_uris and "GOOGLE_REDIRECT_URI" not in os.environ:
                self.google_redirect_uri = redirect_uris[0]


settings = Settings()
settings.load_oauth_json()
