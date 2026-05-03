from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.transaction import Transaction
from app.models.property import Mortgage, PropertyValuation
from app.models.property_value_history import PropertyValueHistory
from app.models.monarch_link import MonarchAccountConfig
from app.models.simplefin_link import SimpleFinAccountConfig
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountWithBalance,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _account_source(account_id: str) -> str:
    """Derive the data-source label from the synthetic id prefix.

    Sync providers create accounts with a known prefix (monarch-*, simplefin-*,
    plaid-*); manually created accounts use whatever id the user/system chose.
    Surface this so the Settings page can show where each row's data came from.
    """
    if account_id.startswith("monarch-"):
        return "monarch"
    if account_id.startswith("simplefin-"):
        return "simplefin"
    if account_id.startswith("plaid-"):
        return "plaid"
    return "manual"


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
    db: Session = Depends(get_tenant_db),
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
        data.source = _account_source(acct.id)
        data.current_balance = float(balance) if balance is not None else None
        data.balance_date = snap_date
        results.append(data)
    return results


@router.get("/{account_id}", response_model=AccountWithBalance)
def get_account(account_id: str, db: Session = Depends(get_tenant_db)):
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
    result.source = _account_source(acct.id)
    if latest:
        result.current_balance = float(latest.balance) if latest.balance is not None else None
        result.balance_date = latest.snapshot_date
    return result


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_tenant_db)):
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
def update_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_tenant_db)):
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(acct, key, value)

    db.commit()
    db.refresh(acct)
    return acct


def _related_counts(db: Session, account_id: str) -> dict[str, int]:
    """Count records that reference this account, grouped by table."""
    return {
        "balance_snapshots": db.execute(
            select(func.count()).select_from(BalanceSnapshot).where(BalanceSnapshot.account_id == account_id)
        ).scalar_one(),
        "transactions": db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.account_id == account_id)
        ).scalar_one(),
        "mortgages": db.execute(
            select(func.count()).select_from(Mortgage).where(Mortgage.account_id == account_id)
        ).scalar_one(),
        "property_valuations": db.execute(
            select(func.count()).select_from(PropertyValuation).where(PropertyValuation.account_id == account_id)
        ).scalar_one(),
        "property_value_history": db.execute(
            select(func.count()).select_from(PropertyValueHistory).where(PropertyValueHistory.account_id == account_id)
        ).scalar_one(),
    }


@router.get("/{account_id}/related-counts")
def get_related_counts(account_id: str, db: Session = Depends(get_tenant_db)):
    """Return counts of records that would be affected by deleting this account.

    Powers the Settings → Accounts delete confirmation so the UI can show the
    user exactly what will be removed before they tick the cascade box.
    """
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return _related_counts(db, account_id)


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: str,
    cascade: bool = Query(False, description="If true, also delete all records referencing this account."),
    db: Session = Depends(get_tenant_db),
):
    """Delete an account.

    Default (cascade=false) refuses if any related records exist and returns
    409 with counts so the UI can prompt. With cascade=true, deletes related
    transactions, balance snapshots, mortgages, and property history first.

    Sync-provider per-account configs (Monarch/SimpleFIN) are not deleted;
    their `local_account_id` is cleared so they no longer reference the
    removed row but the user's sync mapping survives.
    """
    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    counts = _related_counts(db, account_id)
    has_related = any(v > 0 for v in counts.values())

    if has_related and not cascade:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Account has related records. Re-send with ?cascade=true to delete them.",
                "related_counts": counts,
            },
        )

    if cascade and has_related:
        db.execute(BalanceSnapshot.__table__.delete().where(BalanceSnapshot.account_id == account_id))
        db.execute(Transaction.__table__.delete().where(Transaction.account_id == account_id))
        db.execute(Mortgage.__table__.delete().where(Mortgage.account_id == account_id))
        db.execute(PropertyValuation.__table__.delete().where(PropertyValuation.account_id == account_id))
        db.execute(PropertyValueHistory.__table__.delete().where(PropertyValueHistory.account_id == account_id))

    db.execute(
        update(MonarchAccountConfig)
        .where(MonarchAccountConfig.local_account_id == account_id)
        .values(local_account_id=None)
    )
    db.execute(
        update(SimpleFinAccountConfig)
        .where(SimpleFinAccountConfig.local_account_id == account_id)
        .values(local_account_id=None)
    )

    db.delete(acct)
    db.commit()
    return None


class BalanceSnapshotCreate(BaseModel):
    snapshot_date: date
    balance: float
    source: str = "manual"


@router.post("/{account_id}/balances", status_code=201)
def create_balance_snapshot(
    account_id: str,
    payload: BalanceSnapshotCreate,
    db: Session = Depends(get_tenant_db),
):
    """Add a manual balance snapshot for an account."""
    from decimal import Decimal

    acct = db.get(Account, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    snap = BalanceSnapshot(
        account_id=account_id,
        snapshot_date=payload.snapshot_date,
        balance=Decimal(str(payload.balance)),
        source=payload.source,
    )
    db.add(snap)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Balance snapshot already exists for {account_id} on {payload.snapshot_date}")
    db.refresh(snap)
    return {
        "id": snap.id,
        "account_id": snap.account_id,
        "date": snap.snapshot_date.isoformat(),
        "balance": float(snap.balance) if snap.balance is not None else None,
        "source": snap.source,
    }


@router.get("/{account_id}/balances")
def get_balance_history(
    account_id: str,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_tenant_db),
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
