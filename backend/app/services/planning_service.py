from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.engine.projection import ProjectionInput, ProjectionAssumptions, run_projection
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant
from app.models.planning import (
    PlanVersion,
    PlanAssumption,
    PlanProjection,
    ContributionConfig,
)
from app.models.property import Mortgage
from app.schemas.planning import AssumptionInput


def build_projection_input(db: Session) -> ProjectionInput:
    """Build ProjectionInput from current DB state (latest account balances, W2, mortgage, etc.)."""

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
    for display_group, acct_type, total in rows:
        key = display_group.lower().replace(" ", "_")
        balances[key] = balances.get(key, 0.0) + (float(total) if total else 0.0)

    cash = balances.get("cash", 0.0)
    investments = balances.get("investments", 0.0)
    company_stock = balances.get("company_stock", 0.0)
    home_equity = balances.get("home_equity", 0.0)
    retirement_bal = balances.get("retirement", 0.0)

    # --- Latest W2 for income ---
    w2 = db.execute(
        select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)
    ).scalar_one_or_none()

    salary = float(w2.base_salary) if w2 and w2.base_salary else 0.0
    rsu_income = float(w2.rsu_income) if w2 and w2.rsu_income else 0.0

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

    employee_rate = float(contrib.employee_rate) if contrib and contrib.employee_rate else 0.10
    employer_match = float(contrib.employer_match) if contrib and contrib.employer_match else 0.06
    irs_limit = float(contrib.annual_irs_limit) if contrib and contrib.annual_irs_limit else 23500.0

    current_year = date.today().year
    # Approximate current age from W2 tax_year or default to 33
    current_age = 33  # default

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


def create_plan(
    db: Session,
    name: str,
    description: str | None,
    scenario_type: str,
    assumptions_input: list[AssumptionInput],
) -> PlanVersion:
    """Create plan with assumptions, run projection, save results."""
    plan = PlanVersion(
        name=name,
        description=description,
        scenario_type=scenario_type,
    )
    db.add(plan)
    db.flush()  # get plan.id

    # Save assumptions
    db_assumptions = []
    for a in assumptions_input:
        assumption = PlanAssumption(
            plan_id=plan.id,
            key=a.key,
            display_name=a.display_name or a.key,
            category=a.category or "general",
            value=Decimal(str(a.value)),
            description=a.description or "",
            sensitivity=a.sensitivity or "medium",
        )
        db.add(assumption)
        db_assumptions.append(assumption)

    db.flush()

    # Build projection input and run
    try:
        proj_input = build_projection_input(db)
        engine_assumptions = _assumptions_to_engine(db_assumptions)
        rows = run_projection(proj_input, engine_assumptions)

        for row in rows:
            proj = PlanProjection(
                plan_id=plan.id,
                year=row.year,
                age=row.age,
                phase=row.phase,
                salary=Decimal(str(row.salary)),
                rsu_income=Decimal(str(row.rsu_income)),
                total_comp=Decimal(str(row.total_comp)),
                cash=Decimal(str(row.cash)),
                investments=Decimal(str(row.investments)),
                company_stock=Decimal(str(row.company_stock)),
                home_equity=Decimal(str(row.home_equity)),
                retirement_bal=Decimal(str(row.retirement_bal)),
                net_worth=Decimal(str(row.net_worth)),
                withdrawal=Decimal(str(row.withdrawal)),
            )
            db.add(proj)
    except Exception:
        # If projection fails (e.g., no data yet), still save the plan with assumptions
        pass

    db.commit()
    return plan


def update_plan(
    db: Session,
    plan_id: int,
    assumptions_input: list[AssumptionInput],
) -> PlanVersion:
    """Update assumptions, rerun projection, replace old projections."""
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    # Delete existing assumptions and projections
    for a in list(plan.assumptions):
        db.delete(a)
    for p in list(plan.projections):
        db.delete(p)
    db.flush()

    # Save new assumptions
    db_assumptions = []
    for a in assumptions_input:
        assumption = PlanAssumption(
            plan_id=plan.id,
            key=a.key,
            display_name=a.display_name or a.key,
            category=a.category or "general",
            value=Decimal(str(a.value)),
            description=a.description or "",
            sensitivity=a.sensitivity or "medium",
        )
        db.add(assumption)
        db_assumptions.append(assumption)

    db.flush()

    # Rerun projection
    try:
        proj_input = build_projection_input(db)
        engine_assumptions = _assumptions_to_engine(db_assumptions)
        rows = run_projection(proj_input, engine_assumptions)

        for row in rows:
            proj = PlanProjection(
                plan_id=plan.id,
                year=row.year,
                age=row.age,
                phase=row.phase,
                salary=Decimal(str(row.salary)),
                rsu_income=Decimal(str(row.rsu_income)),
                total_comp=Decimal(str(row.total_comp)),
                cash=Decimal(str(row.cash)),
                investments=Decimal(str(row.investments)),
                company_stock=Decimal(str(row.company_stock)),
                home_equity=Decimal(str(row.home_equity)),
                retirement_bal=Decimal(str(row.retirement_bal)),
                net_worth=Decimal(str(row.net_worth)),
                withdrawal=Decimal(str(row.withdrawal)),
            )
            db.add(proj)
    except Exception:
        pass

    db.commit()
    return plan
