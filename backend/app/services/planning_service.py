import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine.projection import ProjectionAssumptions, ProjectionInput
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.planning import (
    ContributionConfig,
    PlanAssumption,
    PlanEvent,
    PlanProjection,
    PlanVersion,
)
from app.models.property import Mortgage
from app.schemas.planning import AssumptionInput
from app.services.compensation import comp_split, latest_w2

logger = logging.getLogger("tallied.planning")


def build_projection_input(db: Session, assumptions: dict[str, float] | None = None) -> ProjectionInput:
    """Build ProjectionInput from current DB state (latest balances, W2, mortgage) plus the plan's own
    household assumptions (current_age, 401(k) rates)."""
    assumptions = assumptions or {}

    # --- Latest balances by display_group ---
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
            Account.display_group,
            Account.account_type,
            func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id)
            & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
        .where(Account.is_active.is_(True))
        .where(Account.include_in_nw.is_(True))
        .group_by(Account.display_group, Account.account_type)
    )

    rows = db.execute(stmt).all()

    balances: dict[str, float] = {}
    for display_group, _acct_type, total in rows:
        key = display_group.lower().replace(" ", "_")
        balances[key] = balances.get(key, 0.0) + (float(total) if total else 0.0)

    cash = balances.get("cash", 0.0)
    investments = balances.get("investments", 0.0)
    company_stock = balances.get("company_stock", 0.0)
    home_equity = balances.get("home_equity", 0.0)
    retirement_bal = balances.get("retirement", 0.0)

    # --- Latest W2 for income ---
    # Gross-only W-2s get their salary/RSU split from the year's vests (services/compensation.py).
    split = comp_split(db, latest_w2(db))
    salary = split.salary
    rsu_income = split.rsu_income

    # --- Mortgage ---
    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()

    mortgage_balance = float(mortgage.current_balance) if mortgage and mortgage.current_balance else 0.0
    mortgage_rate = float(mortgage.rate) if mortgage else 0.065
    mortgage_monthly = float(mortgage.monthly_payment) if mortgage else 0.0

    # --- 401k contribution config ---
    contrib = db.execute(
        select(ContributionConfig).order_by(ContributionConfig.effective_date.desc()).limit(1)
    ).scalar_one_or_none()

    employee_rate = float(assumptions.get("employee_401k_rate") or (contrib.employee_rate if contrib and contrib.employee_rate else 0.10))
    employer_match = float(assumptions.get("employer_match_rate") or (contrib.employer_match if contrib and contrib.employer_match else 0.06))
    irs_limit = float(contrib.annual_irs_limit) if contrib and contrib.annual_irs_limit else 23500.0

    current_year = date.today().year
    current_age = household_age(db)

    return ProjectionInput(
        current_age=current_age,
        current_year=current_year,
        cash=cash,
        investments=investments,
        company_stock=company_stock,
        home_equity=home_equity,
        retirement_bal=retirement_bal,
        salary=salary,
        rsu_income=rsu_income,
        mortgage_balance=mortgage_balance,
        mortgage_rate=mortgage_rate,
        mortgage_monthly_payment=mortgage_monthly,
        employee_401k_rate=employee_rate,
        employer_match_rate=employer_match,
        irs_401k_limit=irs_limit,
    )


def household_age(db: Session) -> int:
    """Age today from the household birth date; ValueError (a 422) when it is not set."""
    from app.services import retirement_outlook as ro

    profile = ro.household_profile(db)
    if profile is None or profile.birth_date is None:
        raise ro.BirthDateMissing()
    return ro.age_on(profile.birth_date, date.today())


def _assumptions_to_engine(assumptions: list[PlanAssumption]) -> ProjectionAssumptions:
    """Convert DB PlanAssumption rows to engine ProjectionAssumptions."""
    mapping = {a.key: float(a.value) for a in assumptions}
    return ProjectionAssumptions(
        retirement_age=int(mapping.get("retirement_age", 60)),
        total_comp_growth=mapping.get("total_comp_growth", 0.04),
        rsu_pct_of_comp=mapping.get("rsu_pct_of_comp", 0.37),
        rsu_pct_annual_increase=mapping.get("rsu_pct_annual_increase", 0.005),
        rsu_pct_cap=mapping.get("rsu_pct_cap", 0.50),
        rsu_tax_rate=mapping.get("rsu_tax_rate", 0.40),
        investment_return=mapping.get("investment_return", 0.07),
        retirement_return=mapping.get("retirement_return", 0.05),
        stock_price_growth=mapping.get("stock_price_growth", 0.07),
        inflation=mapping.get("inflation", 0.03),
        home_appreciation=mapping.get("home_appreciation", 0.03),
        monthly_cash_savings=mapping.get("monthly_cash_savings", 440.0),
        retirement_spending=mapping.get("retirement_spending", 100_000.0),
        retirement_tax_rate=mapping.get("retirement_tax_rate", 0.20),
    )


def _store_projection(db: Session, plan: PlanVersion) -> None:
    """Replace the plan's stored projection with the outlook engine's expected (median) path.

    plan_projections stays the queryable copy of the plan line the Planning page draws.
    """
    from app.services import retirement_outlook as ro

    for p in list(plan.projections):
        db.delete(p)
    db.flush()
    try:
        _, _, household, _, inputs = ro.household_and_inputs(db, plan)
    except ro.BirthDateMissing:
        # No birth date yet: there is no age to project from. The page asks for it; nothing is stored.
        logger.info("Plan %s: no household birth date, projection not stored", plan.id)
        return
    for row in ro.expected_rows(inputs, household):
        db.add(PlanProjection(
            plan_id=plan.id, year=row["year"], age=row["age"], phase=row["phase"],
            salary=Decimal(str(row["salary"])), rsu_income=Decimal(str(row["rsu_income"])),
            total_comp=Decimal(str(row["total_comp"])), cash=Decimal(str(row["cash"])),
            investments=Decimal(str(row["investments"])), company_stock=Decimal(str(row["company_stock"])),
            home_equity=Decimal(str(row["home_equity"])), retirement_bal=Decimal(str(row["retirement_bal"])),
            net_worth=Decimal(str(row["net_worth"])), withdrawal=Decimal(str(row["withdrawal"])),
        ))


def _recompute(db: Session, plan: PlanVersion) -> None:
    try:
        db.flush()
        db.refresh(plan)
        _store_projection(db, plan)
    except Exception as exc:
        db.rollback()
        logger.exception("Projection failed for plan %s", getattr(plan, "id", "(new)"))
        raise ValueError(f"Projection failed: {exc}") from exc


def _assumption_row(plan_id: int, a: AssumptionInput, old: PlanAssumption | None = None) -> PlanAssumption:
    from app.services.plan_assumptions import BY_KEY

    spec = BY_KEY.get(a.key, {})
    return PlanAssumption(
        plan_id=plan_id,
        key=a.key,
        display_name=a.display_name or (old.display_name if old else None) or spec.get("display_name") or a.key,
        category=a.category or (old.category if old else None) or spec.get("category") or "general",
        value=Decimal(str(a.value)),
        description=a.description or (old.description if old else None) or spec.get("description") or "",
        sensitivity=a.sensitivity or (old.sensitivity if old else None) or spec.get("sensitivity") or "medium",
    )


def create_plan(
    db: Session,
    name: str,
    description: str | None,
    scenario_type: str,
    assumptions_input: list[AssumptionInput],
    spending_rule: str = "fixed",
    copy_events_from: PlanVersion | None = None,
    spending_profile: str = "flat",
) -> PlanVersion:
    """Create plan with assumptions (and optionally another plan's life events), run projection, save."""
    _check_rule(spending_rule)
    _check_profile(spending_profile)
    plan = PlanVersion(name=name, description=description, scenario_type=scenario_type, spending_rule=spending_rule,
                       spending_profile=spending_profile)
    db.add(plan)
    db.flush()
    for a in assumptions_input:
        db.add(_assumption_row(plan.id, a))
    for e in (copy_events_from.events if copy_events_from else []):
        db.add(PlanEvent(plan_id=plan.id, kind=e.kind, label=e.label, start_age=e.start_age, end_age=e.end_age,
                         amount=e.amount, pct=e.pct, enabled=e.enabled, params=dict(e.params) if e.params else None))
    _recompute(db, plan)
    db.commit()
    return plan


def update_plan(
    db: Session,
    plan_id: int,
    assumptions_input: list[AssumptionInput] | None,
    spending_rule: str | None = None,
    name: str | None = None,
    description: str | None = None,
    spending_profile: str | None = None,
) -> PlanVersion:
    """Upsert the given assumptions (others keep their values), optionally rename or change the rule, rerun."""
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    if name is not None:
        plan.name = name
    if description is not None:
        plan.description = description
    if spending_rule is not None:
        _check_rule(spending_rule)
        plan.spending_rule = spending_rule
    if spending_profile is not None:
        _check_profile(spending_profile)
        plan.spending_profile = spending_profile
    if assumptions_input:
        existing = {a.key: a for a in plan.assumptions}
        for a in assumptions_input:
            old = existing.get(a.key)
            if old is not None:
                row = _assumption_row(plan.id, a, old)
                old.value, old.display_name, old.category = row.value, row.display_name, row.category
                old.description, old.sensitivity = row.description, row.sensitivity
            else:
                db.add(_assumption_row(plan.id, a))
    _recompute(db, plan)
    db.commit()
    return plan


def _check_profile(profile: str) -> None:
    from app.engine.retirement_sim import SPENDING_PROFILES

    if profile not in SPENDING_PROFILES:
        raise ValueError(f"Unknown spending profile '{profile}'")


def _check_rule(rule: str) -> None:
    from app.engine.retirement_sim import SPENDING_RULES

    if rule not in SPENDING_RULES:
        raise ValueError(f"Unknown spending rule '{rule}'")


def recompute_all(db: Session) -> None:
    """Re-store every plan's projection (after the household birth date changes)."""
    for plan in db.execute(select(PlanVersion)).scalars().all():
        _recompute(db, plan)
    db.commit()


def delete_plan(db: Session, plan_id: int) -> None:
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise LookupError(f"Plan {plan_id} not found")
    db.delete(plan)
    db.commit()


# ---------------------------------------------------------------------------
# Life events
# ---------------------------------------------------------------------------
def _check_event(kind: str, start_age: int, end_age: int | None) -> None:
    from app.engine.retirement_sim import EVENT_KINDS

    if kind not in EVENT_KINDS:
        raise ValueError(f"Unknown event kind '{kind}'")
    if end_age is not None and end_age < start_age:
        raise ValueError("End age is before start age")


def _clean_params(kind: str, params: dict | None) -> dict | None:
    """Only a layoff carries params today: whitelisted keys, numbers, sane ranges."""
    if not params:
        return None
    if kind != "layoff":
        raise ValueError(f"Event kind '{kind}' takes no parameters")
    from app.engine.retirement_sim import LAYOFF_DEFAULTS

    bounds = {"severance_weeks": (0, 104), "gap_months": (0, 120), "ui_weekly": (0, 5000),
              "gap_health_annual": (0, 100_000), "next_pay_pct": (0, 3), "next_equity": (0, 1),
              "never_reemployed": (0, 1), "part_time_income": (0, 1_000_000)}
    out = {}
    for k, v in params.items():
        if k not in LAYOFF_DEFAULTS:
            raise ValueError(f"Unknown layoff setting '{k}'")
        try:
            x = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Layoff setting '{k}' must be a number") from exc
        lo, hi = bounds[k]
        if not lo <= x <= hi:
            raise ValueError(f"Layoff setting '{k}' must be between {lo} and {hi}")
        out[k] = x
    return out


def add_event(db: Session, plan_id: int, data: dict) -> PlanEvent:
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise LookupError(f"Plan {plan_id} not found")
    _check_event(data["kind"], data["start_age"], data.get("end_age"))
    ev = PlanEvent(
        plan_id=plan_id, kind=data["kind"], label=data["label"], start_age=data["start_age"],
        end_age=data.get("end_age"), amount=Decimal(str(data.get("amount") or 0)),
        pct=Decimal(str(data.get("pct") or 0)), enabled=data.get("enabled", True),
        params=_clean_params(data["kind"], data.get("params")),
    )
    db.add(ev)
    _recompute(db, plan)
    db.commit()
    db.refresh(ev)
    return ev


def update_event(db: Session, event_id: int, data: dict) -> PlanEvent:
    ev = db.get(PlanEvent, event_id)
    if not ev:
        raise LookupError(f"Event {event_id} not found")
    for field in ("kind", "label", "start_age", "end_age", "enabled"):
        if field in data:
            setattr(ev, field, data[field])
    for field in ("amount", "pct"):
        if field in data and data[field] is not None:
            setattr(ev, field, Decimal(str(data[field])))
    if data.get("params") is not None:
        ev.params = _clean_params(ev.kind, {**(ev.params or {}), **data["params"]})
    _check_event(ev.kind, ev.start_age, ev.end_age)
    _recompute(db, ev.plan)
    db.commit()
    db.refresh(ev)
    return ev


def delete_event(db: Session, event_id: int) -> None:
    ev = db.get(PlanEvent, event_id)
    if not ev:
        raise LookupError(f"Event {event_id} not found")
    plan = ev.plan
    db.delete(ev)
    _recompute(db, plan)
    db.commit()
