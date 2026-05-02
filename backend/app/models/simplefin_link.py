from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SimpleFinLink(Base):
    """Stored SimpleFIN access URL for a tenant.

    SimpleFIN tokens are claimed once (single-use) to mint a permanent
    access URL containing basic-auth credentials. We never store the
    setup token, only the resulting access URL.
    """

    __tablename__ = "simplefin_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    access_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    account_configs: Mapped[list["SimpleFinAccountConfig"]] = relationship(
        "SimpleFinAccountConfig", back_populates="link", cascade="all, delete-orphan"
    )


class SimpleFinAccountConfig(Base):
    __tablename__ = "simplefin_account_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simplefin_link_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("simplefin_links.id"), nullable=False
    )
    simplefin_account_id: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[Optional[str]] = mapped_column(String)
    institution: Mapped[Optional[str]] = mapped_column(String)
    sync_balances: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    local_account_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    link: Mapped["SimpleFinLink"] = relationship(
        "SimpleFinLink", back_populates="account_configs"
    )
