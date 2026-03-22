from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text, func, select
from sqlalchemy.orm import Session

from app.database import get_db, engine, Base
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.transaction import Transaction

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Known date columns per table for "most recent record" queries
_DATE_COLS = {
    "accounts": "created_at",
    "balance_snapshots": "snapshot_date",
    "transactions": "date",
    "w2_records": "created_at",
    "rsu_grants": "grant_date",
    "vest_events": "vest_date",
    "stock_prices": "price_date",
    "mortgages": "created_at",
    "property_valuations": "valuation_date",
    "plan_versions": "created_at",
    "plan_assumptions": "created_at",
    "plan_projections": "year",
    "import_logs": "imported_at",
    "plaid_links": "created_at",
}


def _coerce(value: Any) -> Any:
    """Make a value JSON-serialisable."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except Exception:
            pass
    return str(value)


@router.get("/tables")
def list_tables(db: Session = Depends(get_db)):
    """Return all tables with row counts and most recent record date."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    results = []
    for table in sorted(table_names):
        try:
            row_count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        except Exception:
            row_count = None

        most_recent = None
        date_col = _DATE_COLS.get(table)
        if date_col:
            try:
                cols = [c["name"] for c in inspector.get_columns(table)]
                if date_col in cols:
                    most_recent = db.execute(
                        text(f"SELECT MAX({date_col}) FROM {table}")
                    ).scalar()
                    if most_recent and hasattr(most_recent, "isoformat"):
                        most_recent = most_recent.isoformat()
                    elif most_recent:
                        most_recent = str(most_recent)
            except Exception:
                pass

        results.append(
            {
                "table": table,
                "row_count": row_count,
                "date_column": date_col,
                "most_recent_date": most_recent,
            }
        )
    return results


@router.get("/tables/{table_name}")
def get_table_rows(
    table_name: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return paginated rows from any table with all columns."""
    inspector = inspect(engine)
    valid_tables = inspector.get_table_names()
    if table_name not in valid_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    columns = [c["name"] for c in inspector.get_columns(table_name)]

    total = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
    rows_raw = db.execute(
        text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset"),
        {"limit": limit, "offset": offset},
    ).fetchall()

    rows = [
        {col: _coerce(val) for col, val in zip(columns, row)} for row in rows_raw
    ]

    return {
        "table": table_name,
        "columns": columns,
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": rows,
    }


@router.get("/accounts/{account_id}/related")
def get_account_related(account_id: str, db: Session = Depends(get_db)):
    """Return all balance snapshots and transactions for an account."""
    account = db.get(Account, account_id)
    if not account is not None:
        pass  # proceed even if not found — return empty related data

    snapshots = (
        db.execute(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.account_id == account_id)
            .order_by(BalanceSnapshot.snapshot_date.desc())
        )
        .scalars()
        .all()
    )

    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.date.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )

    def snapshot_dict(s):
        return {
            "id": s.id,
            "account_id": s.account_id,
            "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
            "balance": float(s.balance) if s.balance is not None else None,
            "source": s.source,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    def txn_dict(t):
        return {
            "id": t.id,
            "date": t.date.isoformat() if t.date else None,
            "amount": float(t.amount) if t.amount is not None else None,
            "merchant": t.merchant,
            "category": t.category,
            "category_group": t.category_group,
            "is_recurring": t.is_recurring,
            "notes": t.notes,
            "source": t.source,
        }

    return {
        "account_id": account_id,
        "balance_snapshots": [snapshot_dict(s) for s in snapshots],
        "balance_snapshot_count": len(snapshots),
        "transactions": [txn_dict(t) for t in transactions],
        "transaction_count": len(transactions),
    }
