"""Reproduce the 500 from POST /api/v1/monarch/sync against real Postgres.

Calls the route handler directly with a mocked Monarch client and a real
tenant DB session. Postgres FK + uniqueness constraints behave differently
from SQLite (which conftest uses), so we need this to find the real bug.
"""
import asyncio
import sys
import traceback
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Make `app.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql://tallied:tallied_dev@localhost/tallied"
SCHEMA = "tenant_claudius"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _session():
    db = SessionLocal()
    db.execute(text(f'SET search_path TO "{SCHEMA}"'))
    return db


def _reset(db):
    """Wipe monarch + transactions/accounts (only monarch-prefixed) to get a clean slate."""
    db.execute(text("DELETE FROM monarch_account_configs"))
    db.execute(text("DELETE FROM monarch_links"))
    db.execute(text("DELETE FROM transactions WHERE id LIKE 'monarch-%'"))
    db.execute(text("DELETE FROM accounts WHERE id LIKE 'monarch-%' OR id = 'ghost-account'"))
    db.commit()


def _seed_link(db, *, sync_transactions=True, local_account_id=None):
    from app.models.monarch_link import MonarchLink, MonarchAccountConfig
    link = MonarchLink(email="claudius@tallied.dev", token="fake-token")
    db.add(link)
    db.flush()
    cfg = MonarchAccountConfig(
        monarch_link_id=link.id,
        monarch_account_id="999",
        account_name="Test Checking",
        account_type="Checking",
        institution="Test Bank",
        sync_balances=False,
        sync_transactions=sync_transactions,
        local_account_id=local_account_id,
    )
    db.add(cfg)
    db.commit()
    return link, cfg


def _mock_client(transactions):
    mm = AsyncMock()
    mm.set_token = lambda *a, **k: None
    mm._headers = {}
    mm.get_transactions = AsyncMock(return_value={
        "allTransactions": {
            "results": transactions,
            "totalCount": len(transactions),
        }
    })
    return mm


async def _run(name, txns, *, local_account_id=None):
    """Reset, seed, call route handler, capture result/traceback."""
    from app.api.monarch_routes import sync_monarch_transactions

    db = _session()
    try:
        _reset(db)
        _seed_link(db, local_account_id=local_account_id)
    finally:
        db.close()

    db = _session()
    try:
        mm = _mock_client(txns)
        with patch("app.api.monarch_routes._get_monarch_client", return_value=mm):
            try:
                result = await sync_monarch_transactions(db=db, ctx=None)  # ctx unused
                print(f"[{name}] OK → {result}")
            except Exception as e:
                print(f"[{name}] EXCEPTION → {type(e).__name__}: {e}")
                traceback.print_exc()
                print()
    finally:
        db.close()


def _txn(**overrides):
    base = {
        "id": "test-1",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "isRecurring": False,
        "account": {"id": "999", "displayName": "Test"},
    }
    base.update(overrides)
    return base


async def main():
    # 1. Stale local_account_id pointing at non-existent account → FK violation in PG
    await _run("stale-fk", [_txn(id="stale-1")], local_account_id="ghost-account")

    # 2. Two txns in one payload with the same id → PK violation
    dup = _txn(id="dup-1")
    await _run("dup-pk-same-payload", [dup, dict(dup)])

    # 3. txn id missing → both become "monarch-" → second is duplicate PK
    await _run("missing-id", [_txn(id=""), _txn(id="", date="2026-04-16")])

    # 4. txn id is None
    await _run("none-id", [_txn(id=None)])

    # 5. amount has too many decimal places (Numeric scale) — PG may truncate or error
    await _run("crazy-decimal", [_txn(id="dec-1", amount=-10.123456789)])

    # 6. extremely long merchant name → varchar truncation? (no length declared in DDL above)
    await _run("long-merchant", [_txn(id="long-1", merchant={"name": "X" * 5000})])

    # 7. Two txns same id but different account → identity-map collision in same flush
    a1 = _txn(id="cross-1", account={"id": "999"})
    a2 = _txn(id="cross-1", account={"id": "999"}, amount=-99.0)
    await _run("dup-pk-different-amount", [a1, a2])

    # 8. Well-formed sanity check
    await _run("happy-path", [_txn(id="happy-1")])


if __name__ == "__main__":
    asyncio.run(main())
