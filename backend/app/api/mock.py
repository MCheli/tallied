"""Mock data endpoints for development and testing. Only available in dev mode."""

from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(tags=["mock"], include_in_schema=False)


def _check_dev_mode():
    if not settings.dev_mode:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/mock-api/accounts")
def mock_accounts():
    """Mock account data using Claudius Banks test persona."""
    _check_dev_mode()
    return {
        "accounts": [
            {"id": "chk-001", "name": "Checking Account", "type": "checking", "balance": 12000.00, "institution": "First National Bank"},
            {"id": "sav-001", "name": "Savings Account", "type": "savings", "balance": 18000.00, "institution": "First National Bank"},
            {"id": "hysa-001", "name": "High-Yield Savings", "type": "savings", "balance": 5000.00, "institution": "Ally Bank"},
            {"id": "401k-001", "name": "Microsoft 401(k)", "type": "retirement", "balance": 185432.50, "institution": "Fidelity"},
            {"id": "inv-001", "name": "Microsoft Brokerage", "type": "investment", "balance": 49500.00, "institution": "E-Trade"},
            {"id": "mtg-001", "name": "Mortgage", "type": "mortgage", "balance": -362450.75, "institution": "First National Bank"},
            {"id": "cc-001", "name": "Visa Signature", "type": "credit_card", "balance": -789.35, "institution": "Chase"},
        ]
    }


@router.get("/mock-api/transactions")
def mock_transactions():
    """Mock transaction data."""
    _check_dev_mode()
    return {
        "transactions": [
            {"id": "t1", "date": "2026-03-13", "merchant": "Whole Foods", "amount": -87.43, "category": "Groceries"},
            {"id": "t2", "date": "2026-03-12", "merchant": "Shell Gas", "amount": -52.10, "category": "Gas"},
            {"id": "t3", "date": "2026-03-12", "merchant": "Amazon", "amount": -34.99, "category": "Shopping"},
            {"id": "t4", "date": "2026-03-11", "merchant": "Microsoft Payroll", "amount": 5576.92, "category": "Income"},
            {"id": "t5", "date": "2026-03-10", "merchant": "Netflix", "amount": -15.99, "category": "Entertainment"},
        ]
    }
