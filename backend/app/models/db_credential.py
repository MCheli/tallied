"""Database credential model for direct Postgres access."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DbCredential(Base):
    """Database credentials live in the public schema (platform table).
    Each credential grants direct Postgres access to a tenant schema."""
    __tablename__ = "db_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    pg_username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    access_level: Mapped[str] = mapped_column(String, default="read")  # read, readwrite
    name: Mapped[str] = mapped_column(String, nullable=False)  # user-chosen label
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
