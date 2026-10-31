from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database — PostgreSQL connection string
    database_url: str = "postgresql://tallied:tallied_dev@localhost/tallied"

    # AI & External Services
    anthropic_api_key: str = ""
    rapidapi_key: str = ""  # RapidAPI key for Realtor.com property data
    email_webhook_secret: str = ""  # Shared secret for Cloudflare Email Worker
    credential_key: str = ""  # Fernet key for provider credentials at rest (required outside dev mode)
    ai_model_import: str = "claude-opus-5-5"  # document import extraction
    ai_model_fast: str = "claude-sonnet-5-5"  # receipts, review chat, valuations

    # Auth
    secret_key: str = "tallied-dev-secret-change-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    dev_mode: bool = False  # When True, allows local email/password login. Must be explicitly enabled.
    dev_user_email: str = "admin@tallied.dev"
    dev_user_password: str = "tallied-admin-change-me"
    api_key_pepper: str = "tallied-api-key-pepper-change-in-production"

    # Public demo (money-demo.markcheli.com): a separate deployment holding only the Claudius seed.
    # Visitors sign in as demo_user_email with one click; nothing can be changed (app/demo.py).
    demo_mode: bool = False
    demo_user_email: str = "claudius@tallied.dev"
    demo_url: str = ""  # set on the real deployment to show "See a live demo" on the login page

    # RSU sell-today estimate (household tax assumptions, editable per deployment)
    ltcg_rate: float = 0.15  # federal long-term capital gains
    stcg_rate: float = 0.37  # short-term = ordinary income (top bracket estimate)
    state_tax_rate: float = 0.05  # state tax on gains (Massachusetts)

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Rate limiting
    rate_limit_per_hour: int = 1000  # Max requests per hour per API key / user
    login_rate_limit_per_hour: int = 100  # Max dev-login attempts per hour per IP (tours log in repeatedly)

    # App
    base_url: str = "http://localhost:8000"  # Used for OAuth redirect URLs

    # Public-facing DB host/port for connection strings shown to users.
    # Defaults to values parsed from database_url (works for local dev).
    # In production, set these to the externally reachable host/port.
    db_public_host: str = ""
    db_public_port: int = 0

    model_config = {"env_prefix": "FINANCE_", "env_file": ".env"}


settings = Settings()
