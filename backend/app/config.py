import json
import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://rosen:rosen_secret@postgres:5432/nestswipe"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "listing-photos"
    minio_secure: bool = False

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

    @property
    def proxy_url(self) -> str:
        if self.proxy_host and self.proxy_user and self.proxy_password:
            return f"http://{self.proxy_user}:{self.proxy_password}@{self.proxy_host}"
        return ""

    # Email polling
    email_poll_interval_minutes: int = 5

    # OAuth JSON path
    oauth_json_path: str = "/app/oauth.json"

    model_config = {"env_file": ".env"}

    def load_oauth_json(self) -> None:
        """Load Google OAuth credentials from oauth.json if not set via env."""
        path = Path(self.oauth_json_path)
        if path.exists() and (not self.google_client_id or not self.google_client_secret):
            data = json.loads(path.read_text())
            web = data.get("web", {})
            self.google_client_id = web.get("client_id", self.google_client_id)
            self.google_client_secret = web.get("client_secret", self.google_client_secret)
            redirect_uris = web.get("redirect_uris", [])
            if redirect_uris and "GOOGLE_REDIRECT_URI" not in os.environ:
                self.google_redirect_uri = redirect_uris[0]


settings = Settings()
settings.load_oauth_json()
