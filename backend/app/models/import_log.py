from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    capture_mode: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="received")
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    raw_data: Mapped[Optional[str]] = mapped_column(Text)
    parsed_summary: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )
