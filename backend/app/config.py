from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database — set DATABASE_URL for Postgres, or leave empty for SQLite
    database_url: str = ""
    db_path: Path = Path(__file__).resolve().parents[2] / "data" / "finance.db"

    # AI & External Services
    anthropic_api_key: str = ""
    plaid_client_id: str = ""
    plaid_secret: str = ""

    # Auth
    secret_key: str = "tallied-dev-secret-change-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    dev_mode: bool = False  # When True, allows local email/password login. Must be explicitly enabled.

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # App
    base_url: str = "http://localhost:8000"  # Used for OAuth redirect URLs

    @property
    def effective_database_url(self) -> str:
        """Use DATABASE_URL if set (Postgres), otherwise fall back to SQLite."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"

    @property
    def is_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite")

    model_config = {"env_prefix": "FINANCE_", "env_file": ".env"}


settings = Settings()
