import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/")
def list_transactions(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    category: str | None = Query(None),
    category_group: str | None = Query(None),
    account_id: str | None = Query(None),
    merchant: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    base = select(Transaction).where(Transaction.source != "plaid")

    if from_date:
        base = base.where(Transaction.date >= from_date)
    if to_date:
        base = base.where(Transaction.date <= to_date)
    if category:
        base = base.where(Transaction.category == category)
    if category_group:
        base = base.where(Transaction.category_group == category_group)
    if account_id:
        base = base.where(Transaction.account_id == account_id)
    if merchant:
        base = base.where(Transaction.merchant.ilike(f"%{merchant}%"))
    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(
                Transaction.merchant.ilike(pattern),
                Transaction.category.ilike(pattern),
                Transaction.notes.ilike(pattern),
            )
        )

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    stmt = base.order_by(Transaction.date.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return {
        "items": [TransactionResponse.model_validate(r) for r in rows],
        "total": total,
    }


@router.post("/", response_model=TransactionResponse, status_code=201)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    txn = Transaction(
        id=str(uuid.uuid4()),
        account_id=payload.account_id,
        date=payload.date,
        amount=payload.amount,
        merchant=payload.merchant,
        category=payload.category,
        category_group=payload.category_group,
        is_recurring=payload.is_recurring,
        notes=payload.notes,
        source=payload.source,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/bulk", status_code=201)
def bulk_create_transactions(
    payloads: list[TransactionCreate],
    db: Session = Depends(get_db),
):
    created = []
    for payload in payloads:
        txn = Transaction(
            id=str(uuid.uuid4()),
            account_id=payload.account_id,
            date=payload.date,
            amount=payload.amount,
            merchant=payload.merchant,
            category=payload.category,
            category_group=payload.category_group,
            is_recurring=payload.is_recurring,
            notes=payload.notes,
            source=payload.source,
        )
        db.add(txn)
        created.append(txn)
    db.commit()
    return {"created": len(created)}


@router.get("/large")
def large_transactions(
    threshold: float = Query(500),
    days: int = Query(30),
    limit: int = Query(20),
    db: Session = Depends(get_db),
):
    """Return recent transactions above a threshold amount (absolute value)."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(Transaction)
        .where(Transaction.date >= cutoff)
        .where(or_(Transaction.amount >= threshold, Transaction.amount <= -threshold))
        .where(Transaction.source != "plaid")
        .order_by(Transaction.date.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()

    # Look up account names
    from app.models.account import Account
    account_map = {}
    acct_ids = {t.account_id for t in rows if t.account_id}
    if acct_ids:
        accts = db.execute(select(Account).where(Account.id.in_(acct_ids))).scalars().all()
        account_map = {a.id: a.name for a in accts}

    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "amount": float(t.amount),
            "merchant": t.merchant,
            "category": t.category,
            "source": t.source,
            "account_name": account_map.get(t.account_id, t.source or "Unknown"),
        }
        for t in rows
    ]
