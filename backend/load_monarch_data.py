"""
Load existing Monarch Money export files into the finance database.

Usage: cd backend && source .venv/bin/activate && python load_monarch_data.py
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.database import engine, Base, SessionLocal
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.transaction import Transaction

DATA_DIR = Path(__file__).parent.parent / "data"

# Monarch type.name → our account_type
TYPE_MAP = {
    "depository": "cash",
    "credit": "credit_card",
    "brokerage": "investment_stock",
    "investment": "investment_stock",
    "loan": "loan_student",
    "real_estate": "real_estate",
    "other_asset": "cash",
    "other_liability": "loan_student",
}

# Our account_type → display_group
GROUP_MAP = {
    "cash": "Cash",
    "credit_card": "Credit Cards",
    "investment_stock": "Investments",
    "investment_401k": "Retirement",
    "loan_mortgage": "Home Equity",
    "loan_student": "Other Loans",
    "real_estate": "Home Equity",
}

# Override specific accounts by name patterns
def classify_account(acct: dict) -> tuple[str, str]:
    """Return (account_type, display_group) based on Monarch data."""
    name = acct.get("displayName", "").lower()
    type_name = acct.get("type", {}).get("name", "").lower()
    subtype_name = acct.get("subtype", {}).get("name", "").lower()

    # Retirement accounts
    if any(k in name for k in ["401k", "401(k)", "ira", "roth", "retirement"]):
        return "investment_401k", "Retirement"
    if subtype_name in ("401k", "401a", "ira", "roth_ira", "roth"):
        return "investment_401k", "Retirement"

    # Mortgage
    if "mortgage" in name or subtype_name == "mortgage":
        return "loan_mortgage", "Home Equity"

    # Student loans
    if "student" in name or "loan" in name:
        return "loan_student", "Other Loans"

    # Use type map
    acct_type = TYPE_MAP.get(type_name, "cash")
    group = GROUP_MAP.get(acct_type, "Cash")
    return acct_type, group


def load_accounts(db):
    data = json.loads((DATA_DIR / "accounts.json").read_text())
    accounts = data.get("accounts", data) if isinstance(data, dict) else data

    count = 0
    for acct in accounts:
        acct_id = str(acct["id"])
        existing = db.get(Account, acct_id)
        if existing:
            continue

        acct_type, display_group = classify_account(acct)
        is_active = not acct.get("syncDisabled", False) and acct.get("deactivatedAt") is None

        db.add(Account(
            id=acct_id,
            name=acct.get("displayName", "Unknown"),
            institution=acct.get("institution", {}).get("name") if isinstance(acct.get("institution"), dict) else None,
            account_type=acct_type,
            display_group=display_group,
            include_in_nw=acct.get("includeInNetWorth", True),
            is_active=is_active,
        ))
        count += 1

    db.commit()
    print(f"  Loaded {count} accounts")
    return count


def load_balance_history(db):
    data = json.loads((DATA_DIR / "account_history.json").read_text())
    if isinstance(data, dict):
        data = data.get("snapshots", data.get("history", []))

    # Filter to only post-Jan-2025 data (pre-2025 is unreliable per user preference)
    cutoff = date(2025, 1, 1)

    count = 0
    batch = []
    for snap in data:
        snap_date = date.fromisoformat(snap["date"])
        if snap_date < cutoff:
            continue

        acct_id = str(snap.get("accountId", snap.get("account_id", "")))
        if not acct_id:
            continue

        batch.append(BalanceSnapshot(
            account_id=acct_id,
            snapshot_date=snap_date,
            balance=float(snap.get("signedBalance", snap.get("balance", 0))),
            source="monarch",
        ))
        count += 1

        if len(batch) >= 500:
            db.add_all(batch)
            db.commit()
            batch = []

    if batch:
        db.add_all(batch)
        db.commit()

    print(f"  Loaded {count} balance snapshots (post-2025-01-01)")
    return count


def load_transactions(db):
    data = json.loads((DATA_DIR / "transactions.json").read_text())
    if isinstance(data, dict):
        data = data.get("transactions", [])

    cutoff = date(2025, 1, 1)

    count = 0
    batch = []
    for txn in data:
        txn_date = date.fromisoformat(txn["date"])
        if txn_date < cutoff:
            continue

        txn_id = str(txn["id"])
        acct_id = txn.get("account", {}).get("id") if isinstance(txn.get("account"), dict) else txn.get("account_id")

        category = None
        category_group = None
        if isinstance(txn.get("category"), dict):
            category = txn["category"].get("name")
            if isinstance(txn["category"].get("group"), dict):
                category_group = txn["category"]["group"].get("name")

        merchant = None
        if isinstance(txn.get("merchant"), dict):
            merchant = txn["merchant"].get("name")
        elif isinstance(txn.get("merchant"), str):
            merchant = txn["merchant"]

        # Fall back to plaidName if no merchant
        if not merchant:
            merchant = txn.get("plaidName")

        batch.append(Transaction(
            id=txn_id,
            account_id=str(acct_id) if acct_id else None,
            date=txn_date,
            amount=txn.get("amount"),
            merchant=merchant,
            category=category,
            category_group=category_group,
            is_recurring=txn.get("isRecurring", False),
            notes=txn.get("notes"),
            source="monarch",
        ))
        count += 1

        if len(batch) >= 500:
            db.add_all(batch)
            db.commit()
            batch = []

    if batch:
        db.add_all(batch)
        db.commit()

    print(f"  Loaded {count} transactions (post-2025-01-01)")
    return count


def main():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Loading Monarch data from", DATA_DIR)
        print()

        acct_count = load_accounts(db)
        snap_count = load_balance_history(db)
        txn_count = load_transactions(db)

        print()
        print(f"Done! {acct_count} accounts, {snap_count} snapshots, {txn_count} transactions")
        print()
        print("Start the backend:  uvicorn app.main:app --reload")
        print("Start the frontend: cd ../frontend && npm run dev")
        print("Open: http://localhost:5173")
    finally:
        db.close()


if __name__ == "__main__":
    main()
