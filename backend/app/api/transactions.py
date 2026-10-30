import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db
from app.models.account import Account
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction
from app.schemas.transaction import (
    CategoryOption,
    CategoryRuleApplied,
    CategoryRuleCreate,
    CategoryRuleResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.services import categorize

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/")
def list_transactions(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    category: str | None = Query(None),
    category_group: str | None = Query(None),
    account_id: str | None = Query(None),
    account_types: str | None = Query(None, description="Comma-separated account_types to include"),
    merchant: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_tenant_db),
):
    base = select(Transaction)

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
    if account_types:
        types = [t.strip() for t in account_types.split(",") if t.strip()]
        if types:
            base = base.where(
                Transaction.account_id.in_(
                    select(Account.id).where(Account.account_type.in_(types))
                )
            )
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
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_tenant_db)):
    """Create a single transaction."""
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
    db: Session = Depends(get_tenant_db),
):
    """Create multiple transactions in a single request."""
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
    exclude_income: bool = Query(False, description="Drop positive amounts (paychecks, deposits)"),
    account_type: str | None = Query(None, description="Only accounts of this type, e.g. cash"),
    db: Session = Depends(get_tenant_db),
):
    """Return recent transactions above a threshold amount (absolute value)."""
    from datetime import timedelta

    from app.models.account import Account
    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(Transaction)
        .where(Transaction.date >= cutoff)
        .where(or_(Transaction.amount >= threshold, Transaction.amount <= -threshold))
        .order_by(Transaction.date.desc())
        .limit(limit)
    )
    if exclude_income:
        stmt = stmt.where(Transaction.amount < 0)
    if account_type:
        stmt = stmt.where(Transaction.account_id.in_(select(Account.id).where(Account.account_type == account_type)))
    rows = db.execute(stmt).scalars().all()

    # Look up account names
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


@router.get("/categories", response_model=list[CategoryOption])
def list_categories(db: Session = Depends(get_tenant_db)):
    """Categories in use (by transactions or rules), for the category picker."""
    return [CategoryOption(category=c, category_group=g) for c, g in categorize.category_options(db)]


@router.get("/category-rules", response_model=list[CategoryRuleResponse])
def list_category_rules(db: Session = Depends(get_tenant_db)):
    """Merchant rules that categorize synced transactions, newest first."""
    return db.execute(select(CategoryRule).order_by(CategoryRule.id.desc())).scalars().all()


@router.post("/category-rules", response_model=CategoryRuleApplied, status_code=201)
def create_category_rule(payload: CategoryRuleCreate, db: Session = Depends(get_tenant_db)):
    """'Always categorize this merchant as X': adds a manual rule and re-applies the rules."""
    try:
        rule, n = categorize.add_rule(db, **payload.model_dump(), source="manual")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    db.refresh(rule)
    return CategoryRuleApplied(rule=CategoryRuleResponse.model_validate(rule), recategorized=n)


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: str, db: Session = Depends(get_tenant_db)):
    """Get a single transaction by ID."""
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    db: Session = Depends(get_tenant_db),
):
    """Update a transaction's details."""
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    categorize.update_transaction(db, txn, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: str, db: Session = Depends(get_tenant_db)):
    """Delete a transaction."""
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
    return None
