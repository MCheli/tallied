from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.income import W2Record
from app.schemas.snapshot import LayerAccount, LiquidityLayer, SnapshotResponse
from app.services.balances import latest_balances, normalize_group

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

# Groups that count toward liquid_net_worth: money that can be spent within days.
LIQUID_GROUPS = {"cash", "investments", "company_stock"}


def build_current_snapshot(db: Session) -> SnapshotResponse:
    """
    Latest balance per active account, grouped by display_group into liquidity
    layers, with totals, the as-of date and the 12-month change.
    """
    rows = latest_balances(db)

    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(normalize_group(row.display_group), []).append(row)

    layers: list[LiquidityLayer] = []
    net_worth = 0.0
    liquid_net_worth = 0.0
    as_of: date | None = None

    for group_key in sorted(groups.keys(), key=lambda g: LAYER_ORDER.get(g, 99)):
        layer_accounts = []
        layer_total = 0.0
        layer_as_of: date | None = None
        for row in groups[group_key]:
            layer_accounts.append(LayerAccount(id=row.account_id, name=row.name, balance=row.balance,
                                               balance_date=row.as_of, include_in_nw=row.include_in_nw))
            if row.include_in_nw:
                layer_total += row.balance
                net_worth += row.balance
                if group_key in LIQUID_GROUPS:
                    liquid_net_worth += row.balance
            layer_as_of = row.as_of if layer_as_of is None else max(layer_as_of, row.as_of)
            as_of = row.as_of if as_of is None else max(as_of, row.as_of)

        layer_name = LAYER_NAMES.get(group_key, group_key.replace("_", " ").title())
        layers.append(LiquidityLayer(name=layer_name, total=round(layer_total, 2), accounts=layer_accounts,
                                     as_of=layer_as_of))

    # Total comp from latest W2
    w2 = db.execute(select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)).scalar_one_or_none()
    total_comp = None
    if w2:
        salary = float(w2.base_salary) if w2.base_salary else 0.0
        rsu = float(w2.rsu_income) if w2.rsu_income else 0.0
        total_comp = salary + rsu

    change = _compute_12mo_change(db, rows, date.today() - timedelta(days=365))

    return SnapshotResponse(
        layers=layers,
        net_worth=round(net_worth, 2),
        liquid_net_worth=round(liquid_net_worth, 2),
        total_comp_annual=round(total_comp, 2) if total_comp else None,
        net_worth_12mo_change=round(change, 2) if change is not None else None,
        as_of=as_of,
    )


def _compute_12mo_change(db: Session, current_rows, target_date: date) -> float | None:
    """Net worth now minus net worth as of `target_date`, over the same set of accounts.

    "As of" means each account's newest snapshot on or before that date, so the
    figure does not depend on a snapshot landing inside a narrow window.
    Accounts with no snapshot by then count as zero (they are new money).
    """
    past = {r.account_id: r.balance for r in latest_balances(db, on_or_before=target_date)}
    if not past:
        return None
    current = sum(r.balance for r in current_rows if r.include_in_nw)
    past_nw = sum(past.get(r.account_id, 0.0) for r in current_rows if r.include_in_nw)
    return current - past_nw
