from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: Path = Path(__file__).resolve().parents[2] / "data" / "finance.db"
    anthropic_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    plaid_client_id: str = ""
    plaid_secret: str = ""

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    model_config = {"env_prefix": "FINANCE_", "env_file": ".env"}


settings = Settings()
