"""Import session model — tracks file uploads through AI parsing to confirmation."""
from datetime import datetime

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
    filename: Mapped[str | None] = mapped_column(String)
    file_type: Mapped[str | None] = mapped_column(String)

    # AI results (stored as JSON strings)
    raw_ai_response: Mapped[str | None] = mapped_column(Text)
    parsed_findings: Mapped[str | None] = mapped_column(Text)  # JSON array
    ai_summary: Mapped[str | None] = mapped_column(Text)
    missing_fields: Mapped[str | None] = mapped_column(Text)  # JSON array
    proposed_changes: Mapped[str | None] = mapped_column(Text)  # JSON array
    accepted_change_ids: Mapped[str | None] = mapped_column(Text)  # JSON array of IDs

    # Chat history (JSON array of {role, content, timestamp})
    chat_messages: Mapped[str | None] = mapped_column(Text)

    # Result
    changes_applied: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
