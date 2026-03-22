from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.schemas.snapshot import SnapshotResponse, LiquidityLayer, LayerAccount


# Map display_group -> liquidity layer ordering
LAYER_ORDER = {
    "cash": 0,
    "investments": 1,
    "company_stock": 1,  # grouped with investments for liquid NW
    "home_equity": 2,
    "retirement": 3,
    "other": 4,
}

# Display names for layers
LAYER_NAMES = {
    "cash": "Cash",
    "investments": "Investments",
    "home_equity": "Home Equity",
    "retirement": "Retirement",
    "other": "Other",
}

# Groups that count toward liquid_net_worth
LIQUID_GROUPS = {"cash", "investments", "company_stock"}


def build_current_snapshot(db: Session) -> SnapshotResponse:
    """
    Query latest balance for each active account.
    Group by display_group into liquidity layers.
    Calculate totals and metadata.
    """
    # Subquery: latest snapshot_date per account
    latest_sub = (
        select(
            BalanceSnapshot.account_id,
            func.max(BalanceSnapshot.snapshot_date).label("max_date"),
        )
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )

    stmt = (
        select(
            Account.id,
            Account.name,
            Account.display_group,
            Account.account_type,
            Account.include_in_nw,
            BalanceSnapshot.balance,
            BalanceSnapshot.snapshot_date,
        )
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id)
            & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
        .where(Account.is_active.is_(True))
    )

    rows = db.execute(stmt).all()

    # Group accounts by display_group
    groups: dict[str, list[tuple]] = {}
    for acct_id, name, display_group, acct_type, include_nw, balance, snap_date in rows:
        key = display_group.lower().replace(" ", "_")
        if key not in groups:
            groups[key] = []
        groups[key].append((acct_id, name, balance, include_nw))

    # Build layers
    layers: list[LiquidityLayer] = []
    net_worth = 0.0
    liquid_net_worth = 0.0

    # Sort groups by layer order
    sorted_groups = sorted(groups.keys(), key=lambda g: LAYER_ORDER.get(g, 99))

    for group_key in sorted_groups:
        accounts_in_group = groups[group_key]
        layer_accounts = []
        layer_total = 0.0

        for acct_id, name, balance, include_nw in accounts_in_group:
            bal = float(balance) if balance is not None else 0.0
            layer_accounts.append(LayerAccount(id=acct_id, name=name, balance=bal))
            layer_total += bal
            if include_nw:
                net_worth += bal
            if group_key in LIQUID_GROUPS and include_nw:
                liquid_net_worth += bal

        layer_name = LAYER_NAMES.get(group_key, group_key.replace("_", " ").title())
        layers.append(LiquidityLayer(
            name=layer_name,
            total=round(layer_total, 2),
            accounts=layer_accounts,
        ))

    # Total comp from latest W2
    w2 = db.execute(
        select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)
    ).scalar_one_or_none()

    total_comp = None
    if w2:
        salary = float(w2.base_salary) if w2.base_salary else 0.0
        rsu = float(w2.rsu_income) if w2.rsu_income else 0.0
        total_comp = salary + rsu

    # 12-month change: compare current total to 12 months ago
    twelve_months_ago = date.today() - timedelta(days=365)
    net_worth_12mo_change = _compute_12mo_change(db, net_worth, twelve_months_ago)

    return SnapshotResponse(
        layers=layers,
        net_worth=round(net_worth, 2),
        liquid_net_worth=round(liquid_net_worth, 2),
        total_comp_annual=round(total_comp, 2) if total_comp else None,
        net_worth_12mo_change=round(net_worth_12mo_change, 2) if net_worth_12mo_change is not None else None,
    )


def _compute_12mo_change(db: Session, current_nw: float, target_date: date) -> float | None:
    """
    Compute net worth as of ~12 months ago by finding the closest
    snapshots to the target date for each account.
    """
    # Find snapshots closest to target_date (within a 14-day window)
    window_start = target_date - timedelta(days=7)
    window_end = target_date + timedelta(days=7)

    # Get the latest snapshot per account within the window
    sub = (
        select(
            BalanceSnapshot.account_id,
            func.max(BalanceSnapshot.snapshot_date).label("max_date"),
        )
        .where(BalanceSnapshot.snapshot_date.between(window_start, window_end))
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )

    stmt = (
        select(
            Account.include_in_nw,
            BalanceSnapshot.balance,
        )
        .join(sub, BalanceSnapshot.account_id == sub.c.account_id)
        .join(Account, Account.id == BalanceSnapshot.account_id)
        .where(BalanceSnapshot.snapshot_date == sub.c.max_date)
        .where(Account.is_active.is_(True))
    )

    rows = db.execute(stmt).all()
    if not rows:
        return None

    past_nw = sum(
        float(balance) if balance is not None else 0.0
        for include_nw, balance in rows
        if include_nw
    )

    return current_nw - past_nw
