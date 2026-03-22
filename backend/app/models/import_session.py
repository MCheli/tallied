"""Import session model — tracks file uploads through AI parsing to confirmation."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportSession(Base):
    __tablename__ = "import_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploading")
    # Status: uploading → processing → review → confirmed | rejected | expired
    context: Mapped[str] = mapped_column(String, nullable=False, default="general")
    # Context: income | retirement | property | rsu | general

    # File info
    filename: Mapped[Optional[str]] = mapped_column(String)
    file_type: Mapped[Optional[str]] = mapped_column(String)

    # AI results (stored as JSON strings)
    raw_ai_response: Mapped[Optional[str]] = mapped_column(Text)
    parsed_findings: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    missing_fields: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    proposed_changes: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    accepted_change_ids: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of IDs

    # Chat history (JSON array of {role, content, timestamp})
    chat_messages: Mapped[Optional[str]] = mapped_column(Text)

    # Result
    changes_applied: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
