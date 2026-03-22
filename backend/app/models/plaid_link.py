from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlaidLink(Base):
    __tablename__ = "plaid_links"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    institution_name: Mapped[Optional[str]] = mapped_column(String)
    institution_id: Mapped[Optional[str]] = mapped_column(String)
    cursor: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
