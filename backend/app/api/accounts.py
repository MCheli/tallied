from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountWithBalance,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _latest_balance_subq():
    """Subquery returning the max snapshot_date per account_id."""
    return (
        select(
            BalanceSnapshot.account_id,
            func.max(BalanceSnapshot.snapshot_date).label("max_date"),
        )
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )


@router.get("/", response_model=list[AccountWithBalance])
def list_accounts(
    account_type: str | None = None,
    display_group: str | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
):
    latest_sub = _latest_balance_subq()

    stmt = (
        select(Account, BalanceSnapshot.balance, BalanceSnapshot.snapshot_date)
        .outerjoin(
            latest_sub,
            Account.id == latest_sub.c.account_id,
        )
        .outerjoin(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id)
            & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
    )

    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)
    if display_group is not None:
        stmt = stmt.where(Account.display_group == display_group)
    if is_active is not None:
        stmt = stmt.where(Account.is_active == is_active)

    rows = db.execute(stmt).all()

    results = []
    for acct, balance, snap_date in rows:
        data = AccountWithBalance.model_validate(acct)
        data.current_balance = float(balance) if balance is not None else None
        data.balance_date = snap_date
        results.append(data)
    return results


@router.get("/{account_id}", response_model=AccountWithBalance)
def get_account(account_id: str, db: Session = Depends(get_db)):
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    latest = db.execute(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account_id)
        .order_by(BalanceSnapshot.snapshot_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    result = AccountWithBalance.model_validate(acct)
    if latest:
        result.current_balance = float(latest.balance) if latest.balance is not None else None
        result.balance_date = latest.snapshot_date
    return result


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    import uuid

    acct = Account(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name,
        institution=payload.institution,
        account_type=payload.account_type,
        display_group=payload.display_group,
        include_in_nw=payload.include_in_nw,
        notes=payload.notes,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db)):
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(acct, key, value)

    db.commit()
    db.refresh(acct)
    return acct


@router.get("/{account_id}/balances")
def get_balance_history(
    account_id: str,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    stmt = (
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account_id)
        .order_by(BalanceSnapshot.snapshot_date)
    )
    if from_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date >= from_date)
    if to_date:
        stmt = stmt.where(BalanceSnapshot.snapshot_date <= to_date)

    snapshots = db.execute(stmt).scalars().all()
    return [
        {
            "date": s.snapshot_date.isoformat(),
            "balance": float(s.balance) if s.balance is not None else None,
            "source": s.source,
        }
        for s in snapshots
    ]
