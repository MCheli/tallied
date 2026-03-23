"""Webhook subscription model for event delivery."""
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# Supported webhook event types
WEBHOOK_EVENTS = [
    "transaction.created",
    "balance.updated",
    "import.completed",
    "account.created",
]


class WebhookSubscription(Base):
    """Webhook subscriptions live in the public schema (platform table).
    Each subscription is scoped to a specific tenant."""
    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)  # delivery URL
    events: Mapped[str] = mapped_column(String, nullable=False)  # comma-separated event types
    secret: Mapped[str] = mapped_column(String, nullable=False)  # HMAC signing secret
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    last_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    @staticmethod
    def generate_secret() -> str:
        """Generate a new HMAC signing secret."""
        return f"whsec_{secrets.token_urlsafe(32)}"

    def event_list(self) -> list[str]:
        """Return events as a list."""
        return [e.strip() for e in self.events.split(",") if e.strip()]

    def matches_event(self, event_type: str) -> bool:
        """Check if this subscription is interested in the given event."""
        return event_type in self.event_list()
