from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncJob(Base):
    """Tracks the lifecycle of a provider sync run (SimpleFIN, ...).

    Inserted with status='running' before kicking off the async task; updated
    to 'succeeded' or 'failed' when the task finishes. The startup watchdog
    marks any 'running' rows older than 15 minutes as 'failed' so a worker
    SIGTERM mid-sync doesn't leave a permanently-stuck row.

    The unique partial index on (provider) WHERE status='running' enforces at
    most one in-flight job *per provider* per tenant schema — so two providers
    can run concurrently, but two syncs of the same provider
    cannot.
    """

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index(
            "uq_sync_jobs_one_running_per_provider",
            "provider",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)  # simplefin
    status: Mapped[str] = mapped_column(String, nullable=False)  # running|succeeded|failed
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual|scheduled
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    balances_synced: Mapped[int] = mapped_column(Integer, default=0)
    txn_added: Mapped[int] = mapped_column(Integer, default=0)
    txn_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list | None] = mapped_column(JSON)  # the provider's own warnings, e.g. a bank needing re-auth

