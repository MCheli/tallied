from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MonarchSyncJob(Base):
    """Tracks the lifecycle of a Monarch sync run.

    Inserted with status='running' before kicking off the async task; updated
    to 'succeeded' or 'failed' when the task finishes. The startup watchdog
    marks any 'running' rows older than 15 minutes as 'failed' so a worker
    SIGTERM mid-sync doesn't leave a permanently-stuck row.

    The unique partial index on (status) WHERE status='running' enforces at
    most one in-flight job per tenant schema, making POST /sync race-safe
    without a separate find-then-insert check.
    """

    __tablename__ = "monarch_sync_jobs"
    __table_args__ = (
        Index(
            "uq_monarch_sync_jobs_one_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # running|succeeded|failed
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual|scheduled
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    balances_synced: Mapped[int] = mapped_column(Integer, default=0)
    txn_added: Mapped[int] = mapped_column(Integer, default=0)
    txn_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
