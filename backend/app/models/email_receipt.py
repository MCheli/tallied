"""Email receipt model — stores raw email data and AI parse results."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailReceipt(Base):
    __tablename__ = "email_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_email: Mapped[str] = mapped_column(String, nullable=False)
    forwarded_by: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    body_html: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="received")  # received, parsed, failed
    parsed_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    transaction_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
