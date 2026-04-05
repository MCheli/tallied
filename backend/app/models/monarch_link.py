from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MonarchLink(Base):
    __tablename__ = "monarch_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    account_configs: Mapped[list["MonarchAccountConfig"]] = relationship(
        "MonarchAccountConfig", back_populates="link", cascade="all, delete-orphan"
    )


class MonarchAccountConfig(Base):
    __tablename__ = "monarch_account_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monarch_link_id: Mapped[int] = mapped_column(Integer, ForeignKey("monarch_links.id"), nullable=False)
    monarch_account_id: Mapped[str] = mapped_column(String, nullable=False)
    account_name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[Optional[str]] = mapped_column(String)
    institution: Mapped[Optional[str]] = mapped_column(String)
    sync_balances: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    local_account_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    link: Mapped["MonarchLink"] = relationship(
        "MonarchLink", back_populates="account_configs"
    )
