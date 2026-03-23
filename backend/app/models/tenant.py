"""Tenant and membership models for multi-tenancy."""
import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SCHEMA_NAME_PATTERN = re.compile(r'^tenant_[a-z0-9]{8,}$')


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    schema_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())

    @staticmethod
    def generate_schema_name() -> str:
        return f"tenant_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def validate_schema_name(name: str) -> bool:
        """Validate that a schema name matches the expected pattern.

        Prevents SQL injection via schema name interpolation in search_path.
        """
        return bool(SCHEMA_NAME_PATTERN.match(name))


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, default="owner")  # owner, viewer
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
