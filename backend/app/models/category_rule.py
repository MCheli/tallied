from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CategoryRule(Base):
    """Merchant -> category rule, applied to new and uncategorized transactions.

    source says where the rule came from: "research" (merchant identified by Claude from
    its name and the owner's records), "email" (confirmed from a receipt), "manual".
    """

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    match: Mapped[str] = mapped_column(String, nullable=False, default="contains")  # exact | prefix | contains
    account_type: Mapped[str | None] = mapped_column(String)  # only accounts of this type
    direction: Mapped[str | None] = mapped_column(String)  # "out" (amount < 0) | "in" (amount > 0)
    category: Mapped[str] = mapped_column(String, nullable=False)
    category_group: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    note: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
