import json
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
            if redirect_uris:
                self.google_redirect_uri = redirect_uris[0]


settings = Settings()
settings.load_oauth_json()
