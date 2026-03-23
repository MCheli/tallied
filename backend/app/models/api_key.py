"""API key model for programmatic access."""
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApiKey(Base):
    """API keys live in the public schema (platform table).
    Each key is scoped to a specific tenant."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)  # user-chosen label
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)  # first 8 chars for identification
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # SHA-256 hash of full key
    permissions: Mapped[str] = mapped_column(String, default="read")  # read, write, admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())

    @staticmethod
    def generate_key() -> str:
        """Generate a new API key with a recognizable prefix."""
        return f"tld_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key using HMAC-SHA256 with a server-side pepper.

        NOTE: Changing the hash algorithm invalidates all existing API keys.
        Users will need to regenerate their keys after this change.
        """
        import hashlib
        import hmac
        from app.config import settings
        return hmac.new(settings.api_key_pepper.encode(), key.encode(), hashlib.sha256).hexdigest()
