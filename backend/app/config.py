from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database — PostgreSQL connection string
    database_url: str = "postgresql://tallied:tallied_dev@localhost/tallied"

    # AI & External Services
    anthropic_api_key: str = ""
    rapidapi_key: str = ""  # RapidAPI key for Realtor.com property data
    plaid_client_id: str = ""
    plaid_secret_sandbox: str = ""
    plaid_secret_production: str = ""
    plaid_env: str = "sandbox"  # "sandbox" or "production"
    email_webhook_secret: str = ""  # Shared secret for Cloudflare Email Worker
    email_receipts_address: str = ""  # e.g. receipts@markcheli.com

    # Auth
    secret_key: str = "tallied-dev-secret-change-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    dev_mode: bool = False  # When True, allows local email/password login. Must be explicitly enabled.
    dev_user_email: str = "admin@tallied.dev"
    dev_user_password: str = "tallied-admin-change-me"
    api_key_pepper: str = "tallied-api-key-pepper-change-in-production"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Rate limiting
    rate_limit_per_hour: int = 1000  # Max requests per hour per API key / IP

    # App
    base_url: str = "http://localhost:8000"  # Used for OAuth redirect URLs

    model_config = {"env_prefix": "FINANCE_", "env_file": ".env"}


settings = Settings()
