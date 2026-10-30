from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db, require_permission
from app.engine.forecast import generate_forecast
from app.engine.projection import ProjectionAssumptions, run_projection
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant, VestEvent
from app.models.planning import (
    ActualSnapshot,
    Forecast,
    PlanAssumption,
    PlanVersion,
)
from app.models.property import Mortgage
from app.schemas.planning import (
    ActualSnapshotCreate,
    ActualSnapshotResponse,
    AssumptionInput,
    HouseholdResponse,
    HouseholdUpdate,
    PlanCompareResponse,
    PlanCreate,
    PlanEventInput,
    PlanEventResponse,
    PlanEventUpdate,
    PlanListItem,
    PlanResponse,
    PlanUpdate,
    SensitivityItem,
    SensitivityResponse,
    SsEarningsResponse,
    SsEarningsUpdate,
    VarianceMetric,
    VarianceResponse,
    WhatIfRequest,
)
from app.services import planning_service, retirement_outlook
from app.services.compensation import comp_split
from app.services.plan_assumptions import ASSUMPTIONS
from app.services.planning_service import (
    build_projection_input,
    create_plan,
    update_plan,
)

router = APIRouter(prefix="/plans", tags=["planning"])

# Default assumptions for new plans: the one vocabulary (services/plan_assumptions.py).
DEFAULT_ASSUMPTIONS: list[dict] = ASSUMPTIONS


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


@router.get("/", response_model=list[PlanListItem])
def list_plans(db: Session = Depends(get_tenant_db)):
    plans = db.execute(
        select(PlanVersion).order_by(PlanVersion.created_at.desc())
    ).scalars().all()
    return [
        PlanListItem(
            id=p.id,
            name=p.name,
            scenario_type=p.scenario_type,
            is_active=p.is_active,
            created_at=p.created_at,
        )
        for p in plans
    ]


@router.post("/", response_model=PlanResponse, status_code=201, dependencies=[Depends(require_permission("write"))])
def create_plan_endpoint(payload: PlanCreate, db: Session = Depends(get_tenant_db)):
    """New plan: every vocabulary key at its default, the source plan's values (copy_from), then the payload's."""
    source = None
    if payload.copy_from is not None:
        source = db.get(PlanVersion, payload.copy_from)
        if not source:
            raise HTTPException(status_code=404, detail="Plan to copy not found")
    base = {a.key: float(a.value) for a in source.assumptions} if source else {}
    user_keys = {a.key: a for a in payload.assumptions}

    assumptions_input = []
    for default in DEFAULT_ASSUMPTIONS:
        user = user_keys.get(default["key"])
        value = user.value if user else base.get(default["key"], default["value"])
        assumptions_input.append(AssumptionInput(
            key=default["key"],
            value=value,
            display_name=(user.display_name if user else None) or default["display_name"],
            category=(user.category if user else None) or default["category"],
            sensitivity=(user.sensitivity if user else None) or default["sensitivity"],
            description=default.get("description"),
        ))

    try:
        plan = create_plan(
            db,
            name=payload.name,
            description=payload.description,
            scenario_type=payload.scenario_type,
            assumptions_input=assumptions_input,
            spending_rule=source.spending_rule if source and payload.spending_rule == "fixed" else payload.spending_rule,
            copy_events_from=source,
            spending_profile=source.spending_profile if source and payload.spending_profile == "flat" else payload.spending_profile,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.refresh(plan)
    return plan


@router.get("/household", response_model=HouseholdResponse)
def get_household(db: Session = Depends(get_tenant_db)):
    """The household's birth date (age is computed from it every day). Null until set."""
    profile = retirement_outlook.household_profile(db)
    if profile is None or profile.birth_date is None:
        return HouseholdResponse()
    return HouseholdResponse(birth_date=profile.birth_date,
                             age=retirement_outlook.age_on(profile.birth_date, date.today()),
                             ss_earnings_years=len(profile.ss_earnings or {}))


@router.put("/household/ss-earnings", response_model=SsEarningsResponse, dependencies=[Depends(require_permission("write"))])
def put_ss_earnings(payload: SsEarningsUpdate, db: Session = Depends(get_tenant_db)):
    """Store the Social Security earnings record so retiring early reduces the statement's estimate."""
    try:
        profile = retirement_outlook.set_ss_earnings(db, payload.earnings)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return SsEarningsResponse(years=len(profile.ss_earnings or {}), factor_by_retirement_age=retirement_outlook.ss_factors(profile))


@router.put("/household", response_model=HouseholdResponse, dependencies=[Depends(require_permission("write"))])
def put_household(payload: HouseholdUpdate, db: Session = Depends(get_tenant_db)):
    try:
        profile = retirement_outlook.set_birth_date(db, payload.birth_date)
        planning_service.recompute_all(db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return HouseholdResponse(birth_date=profile.birth_date,
                             age=retirement_outlook.age_on(profile.birth_date, date.today()))


@router.get("/catalogue")
def plan_catalogue():
    """Spending rules, macro scenarios, life-event templates and the assumption vocabulary."""
    return retirement_outlook.catalogue()


@router.get("/compare", response_model=PlanCompareResponse)
def compare_plans(
    ids: str = Query(..., description="Comma-separated plan IDs"),
    db: Session = Depends(get_tenant_db),
):
    plan_ids = [int(x.strip()) for x in ids.split(",")]
    plans = db.execute(
        select(PlanVersion).where(PlanVersion.id.in_(plan_ids))
    ).scalars().all()

    if len(plans) != len(plan_ids):
        raise HTTPException(status_code=404, detail="One or more plans not found")

    return PlanCompareResponse(plans=plans)


@router.get("/forecasts/latest")
def latest_forecast(db: Session = Depends(get_tenant_db)):
    """Get the latest forecast rows."""
    latest_ts = db.execute(
        select(Forecast.generated_at).order_by(Forecast.generated_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not latest_ts:
        return {"forecasts": []}

    rows = db.execute(
        select(Forecast)
        .where(Forecast.generated_at == latest_ts)
        .order_by(Forecast.year)
    ).scalars().all()

    return {
        "generated_at": latest_ts.isoformat(),
        "forecasts": [
            {
                "year": f.year,
                "cash": float(f.cash) if f.cash else 0,
                "investments": float(f.investments) if f.investments else 0,
                "company_stock": float(f.company_stock) if f.company_stock else 0,
                "home_equity": float(f.home_equity) if f.home_equity else 0,
                "retirement_bal": float(f.retirement_bal) if f.retirement_bal else 0,
                "net_worth": float(f.net_worth) if f.net_worth else 0,
            }
            for f in rows
        ],
    }


@router.post("/forecasts/generate", status_code=201)
def generate_forecast_endpoint(
    years_forward: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_tenant_db),
):
    """Generate a new forecast from historical balance data."""
    # Query balance_snapshots grouped by month and display_group
    stmt = (
        select(
            BalanceSnapshot.snapshot_date,
            Account.display_group,
            sa_func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .where(Account.include_in_nw.is_(True))
        .group_by(BalanceSnapshot.snapshot_date, Account.display_group)
        .order_by(BalanceSnapshot.snapshot_date)
    )
    rows = db.execute(stmt).all()

    if not rows:
        raise HTTPException(status_code=422, detail="No balance history available for forecasting")

    balance_history = [
        {
            "date": row.snapshot_date.isoformat(),
            "display_group": row.display_group,
            "total": float(row.total) if row.total else 0,
        }
        for row in rows
    ]

    forecast_rows = generate_forecast(balance_history, years_forward=years_forward)

    if not forecast_rows:
        raise HTTPException(status_code=422, detail="Could not generate forecast from available data")

    # Save to forecasts table
    generated_at = datetime.utcnow()
    for fr in forecast_rows:
        f = Forecast(
            generated_at=generated_at,
            method="linear_trend",
            year=fr.year,
            cash=Decimal(str(fr.cash)),
            investments=Decimal(str(fr.investments)),
            company_stock=Decimal(str(fr.company_stock)),
            home_equity=Decimal(str(fr.home_equity)),
            retirement_bal=Decimal(str(fr.retirement_bal)),
            net_worth=Decimal(str(fr.net_worth)),
        )
        db.add(f)

    db.commit()

    return {
        "generated_at": generated_at.isoformat(),
        "years_forward": years_forward,
        "forecasts": [
            {
                "year": fr.year,
                "cash": fr.cash,
                "investments": fr.investments,
                "company_stock": fr.company_stock,
                "home_equity": fr.home_equity,
                "retirement_bal": fr.retirement_bal,
                "net_worth": fr.net_worth,
            }
            for fr in forecast_rows
        ],
    }


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, db: Session = Depends(get_tenant_db)):
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.put("/{plan_id}", response_model=PlanResponse, dependencies=[Depends(require_permission("write"))])
def update_plan_endpoint(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_tenant_db)):
    if not db.get(PlanVersion, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    try:
        plan = update_plan(db, plan_id, payload.assumptions, spending_rule=payload.spending_rule,
                           name=payload.name, description=payload.description,
                           spending_profile=payload.spending_profile)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=204, dependencies=[Depends(require_permission("write"))])
def delete_plan(plan_id: int, db: Session = Depends(get_tenant_db)):
    try:
        planning_service.delete_plan(db, plan_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Plan not found")
    return None


# ---------------------------------------------------------------------------
# Outlook (planning v2): Monte Carlo, history, scenarios, goal-seek
# ---------------------------------------------------------------------------
def _outlook_or_422(db: Session, plan_id: int, **kw) -> dict:
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    try:
        return retirement_outlook.outlook(db, plan, **kw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{plan_id}/outlook")
def plan_outlook(
    plan_id: int,
    regime: str = Query("base", description="Macro scenario key (see /plans/catalogue)"),
    analysis: bool = Query(True, description="Include scenarios, goal-seek, sensitivity and event impacts"),
    db: Session = Depends(get_tenant_db),
):
    """The saved plan's outlook: chance of success, wealth bands, historical cohorts and what would need to be true."""
    return _outlook_or_422(db, plan_id, regime_key=regime, include_analysis=analysis)


@router.post("/{plan_id}/what-if")
def plan_what_if(plan_id: int, payload: WhatIfRequest, db: Session = Depends(get_tenant_db)):
    """The outlook with levers changed. Writes nothing; save with PUT /plans/{id}."""
    return _outlook_or_422(
        db, plan_id, overrides=payload.overrides, spending_rule=payload.spending_rule,
        regime_key=payload.regime, event_enabled=payload.event_enabled, include_analysis=payload.analysis,
        spending_profile=payload.spending_profile,
    )


@router.post("/{plan_id}/sprint")
def plan_sprint(plan_id: int, payload: WhatIfRequest, db: Session = Depends(get_tenant_db)):
    """'Sprint to retirement' with the given levers: max 401(k), every equity payout invested; the most
    spending per retirement age and return, the earliest age per spending, and the levers that matter."""
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    try:
        return retirement_outlook.sprint(
            db, plan, payload.overrides, payload.spending_rule, payload.spending_profile, payload.event_enabled,
            payload.regime)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{plan_id}/events", response_model=PlanEventResponse, status_code=201,
             dependencies=[Depends(require_permission("write"))])
def add_plan_event(plan_id: int, payload: PlanEventInput, db: Session = Depends(get_tenant_db)):
    try:
        return planning_service.add_event(db, plan_id, payload.model_dump())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/events/{event_id}", response_model=PlanEventResponse, dependencies=[Depends(require_permission("write"))])
def update_plan_event(event_id: int, payload: PlanEventUpdate, db: Session = Depends(get_tenant_db)):
    try:
        return planning_service.update_event(db, event_id, payload.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/events/{event_id}", status_code=204, dependencies=[Depends(require_permission("write"))])
def delete_plan_event(event_id: int, db: Session = Depends(get_tenant_db)):
    try:
        planning_service.delete_event(db, event_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None


@router.get("/{plan_id}/sensitivity", response_model=SensitivityResponse)
def sensitivity_analysis(
    plan_id: int,
    target_year: int | None = Query(None),
    db: Session = Depends(get_tenant_db),
):
    """Run sensitivity analysis: vary each high/medium assumption +/- 20%."""
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        proj_input = build_projection_input(db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if target_year is None:
        target_year = proj_input.current_year + 20

    base_assumptions = _assumptions_to_engine(plan.assumptions)
    base_rows = run_projection(proj_input, base_assumptions)
    base_nw = _find_year_nw(base_rows, target_year)

    items = []
    for assumption in plan.assumptions:
        if assumption.sensitivity == "low":
            continue

        val = float(assumption.value)
        delta = abs(val) * 0.20 if val != 0 else 0.1

        # Low scenario
        low_val = val - delta
        low_assumptions = _assumptions_to_engine(plan.assumptions)
        setattr(low_assumptions, assumption.key, low_val if assumption.key != "retirement_age" else int(low_val))
        low_rows = run_projection(proj_input, low_assumptions)
        impact_low = _find_year_nw(low_rows, target_year) - base_nw

        # High scenario
        high_val = val + delta
        high_assumptions = _assumptions_to_engine(plan.assumptions)
        setattr(high_assumptions, assumption.key, high_val if assumption.key != "retirement_age" else int(high_val))
        high_rows = run_projection(proj_input, high_assumptions)
        impact_high = _find_year_nw(high_rows, target_year) - base_nw

        items.append(SensitivityItem(
            key=assumption.key,
            display_name=assumption.display_name,
            base_value=val,
            impact_low=round(impact_low, 2),
            impact_high=round(impact_high, 2),
        ))

    items.sort(key=lambda x: abs(x.impact_high - x.impact_low), reverse=True)

    return SensitivityResponse(
        items=items,
        target_metric="net_worth",
        target_year=target_year,
    )


@router.get("/{plan_id}/variance", response_model=list[VarianceResponse])
def plan_variance(plan_id: int, db: Session = Depends(get_tenant_db)):
    """Compare plan projections vs actual snapshots."""
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    actuals = db.execute(
        select(ActualSnapshot).order_by(ActualSnapshot.snapshot_date)
    ).scalars().all()

    if not actuals:
        return []

    # Index projections by year
    proj_by_year = {p.year: p for p in plan.projections}

    # Index forecasts by year (latest generation)
    latest_ts = db.execute(
        select(Forecast.generated_at).order_by(Forecast.generated_at.desc()).limit(1)
    ).scalar_one_or_none()
    forecast_by_year: dict = {}
    if latest_ts:
        forecasts = db.execute(
            select(Forecast).where(Forecast.generated_at == latest_ts)
        ).scalars().all()
        forecast_by_year = {f.year: f for f in forecasts}

    results = []
    for actual in actuals:
        year = actual.snapshot_date.year
        proj = proj_by_year.get(year)
        if not proj:
            continue

        forecast = forecast_by_year.get(year)

        metrics: dict[str, VarianceMetric] = {}
        for field in ["cash", "investments", "company_stock", "home_equity", "retirement_bal", "net_worth"]:
            plan_val = float(getattr(proj, field) or 0)
            actual_val = float(getattr(actual, field) or 0)
            plan_var = ((actual_val - plan_val) / plan_val * 100) if plan_val != 0 else 0.0

            forecast_val = None
            forecast_var = None
            if forecast:
                forecast_val = float(getattr(forecast, field) or 0)
                forecast_var = ((actual_val - forecast_val) / forecast_val * 100) if forecast_val != 0 else 0.0

            metrics[field] = VarianceMetric(
                plan=round(plan_val, 2),
                forecast=round(forecast_val, 2) if forecast_val is not None else None,
                actual=round(actual_val, 2),
                plan_var_pct=round(plan_var, 2),
                forecast_var_pct=round(forecast_var, 2) if forecast_var is not None else None,
            )

        results.append(VarianceResponse(year=year, metrics=metrics))

    return results


@router.post("/actuals", response_model=ActualSnapshotResponse, status_code=201)
def record_actual(payload: ActualSnapshotCreate, db: Session = Depends(get_tenant_db)):
    snapshot = ActualSnapshot(**payload.model_dump())
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Plan table endpoint — year × metric matrix
# ---------------------------------------------------------------------------


_PLAN_METRICS = [
    "gross_income", "base_salary", "rsu_income", "tax_paid", "take_home", "contributions_401k",
    "net_worth", "liquid_net_worth", "investment_balance",
    "retirement_balance", "home_equity", "mortgage_balance",
]



def _cell(value: float | None, status: str) -> dict:
    return {"value": round(value, 2) if value is not None else None, "status": status}


def _balances_for_year(db: Session, year: int) -> dict[str, float]:
    latest_sub = (
        select(
            BalanceSnapshot.account_id,
            sa_func.max(BalanceSnapshot.snapshot_date).label("max_date"),
        )
        .where(
            BalanceSnapshot.snapshot_date >= date(year, 1, 1),
            BalanceSnapshot.snapshot_date <= date(year, 12, 31),
        )
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )
    stmt = (
        select(
            Account.display_group,
            sa_func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id)
            & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
        .where(Account.include_in_nw.is_(True))
        .group_by(Account.display_group)
    )
    rows = db.execute(stmt).all()
    return {
        (dg or "unknown").lower().replace(" ", "_"): float(total) if total else 0.0
        for dg, total in rows
    }


def _latest_balances(db: Session) -> dict[str, float]:
    latest_sub = (
        select(
            BalanceSnapshot.account_id,
            sa_func.max(BalanceSnapshot.snapshot_date).label("max_date"),
        )
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )
    stmt = (
        select(
            Account.display_group,
            sa_func.sum(BalanceSnapshot.balance).label("total"),
        )
        .join(latest_sub, Account.id == latest_sub.c.account_id)
        .join(
            BalanceSnapshot,
            (BalanceSnapshot.account_id == Account.id)
            & (BalanceSnapshot.snapshot_date == latest_sub.c.max_date),
        )
        .where(Account.include_in_nw.is_(True))
        .group_by(Account.display_group)
    )
    rows = db.execute(stmt).all()
    return {
        (dg or "unknown").lower().replace(" ", "_"): float(total) if total else 0.0
        for dg, total in rows
    }


def _balance_metrics(balances: dict[str, float], mortgage_balance: float | None, status: str) -> dict:
    investment_balance = balances.get("investments", 0.0) + balances.get("company_stock", 0.0)
    retirement_balance = balances.get("retirement", 0.0)
    home_equity = balances.get("home_equity", 0.0)
    net_worth = sum(balances.values())
    liquid_net_worth = net_worth - home_equity - retirement_balance
    return {
        "net_worth": _cell(net_worth, status),
        "liquid_net_worth": _cell(liquid_net_worth, status),
        "investment_balance": _cell(investment_balance, status),
        "retirement_balance": _cell(retirement_balance, status),
        "home_equity": _cell(home_equity, status),
        "mortgage_balance": _cell(mortgage_balance, status),
    }


@router.get("/{plan_id}/table")
def plan_table(plan_id: int, db: Session = Depends(get_tenant_db)):
    """
    Return the full year×metric matrix for a plan.
    - Actuals: years before current year (from W2 records + balance snapshots)
    - Forecast: current year (YTD extrapolated)
    - Plan: future years (from PlanProjection rows)
    """
    plan = db.get(PlanVersion, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    assumption_ages = {a.key: float(a.value) for a in plan.assumptions}
    try:
        user_age: int = planning_service.household_age(db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    retirement_age: int = int(assumption_ages.get("retirement_age", 60))

    today = date.today()
    current_year = today.year
    current_month = today.month

    retirement_year = current_year + (retirement_age - user_age)

    w2_by_year: dict[int, Any] = {
        r.tax_year: r
        for r in db.execute(select(W2Record)).scalars().all()
    }
    first_year = min(w2_by_year.keys()) if w2_by_year else current_year
    years = list(range(first_year, retirement_year + 1))

    proj_by_year = {p.year: p for p in plan.projections}
    assumption_map = {a.key: float(a.value) for a in plan.assumptions}

    inflation = assumption_map.get("inflation", 0.03)
    employee_401k_rate = assumption_map.get("employee_401k_rate", 0.10)

    mortgage = db.execute(
        select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    current_mortgage_balance = float(mortgage.current_balance) if mortgage and mortgage.current_balance else None

    # Build RSU vest income by year from actual vest schedule
    # For future years with known vest events, use these instead of projection assumptions
    from app.services.stock_price import get_or_fetch_price
    vest_events = db.execute(select(VestEvent).order_by(VestEvent.vest_date)).scalars().all()
    rsu_vest_by_year: dict[int, float] = {}
    # Get stock price for RSU company — reads symbol from first grant
    first_grant = db.execute(select(RSUGrant).limit(1)).scalar_one_or_none()
    rsu_symbol = first_grant.symbol if first_grant and first_grant.symbol else "MSFT"
    current_price = get_or_fetch_price(db, rsu_symbol)
    for ve in vest_events:
        y = ve.vest_date.year
        if ve.is_actual and ve.fmv_at_vest:
            rsu_vest_by_year.setdefault(y, 0.0)
            rsu_vest_by_year[y] += float(ve.fmv_at_vest) * ve.shares
        elif not ve.is_actual and ve.shares and current_price:
            rsu_vest_by_year.setdefault(y, 0.0)
            rsu_vest_by_year[y] += current_price * ve.shares

    rows_out: dict[str, Any] = {}

    for year in years:
        if year < current_year:
            status = "actuals"
            w2 = w2_by_year.get(year)

            if w2:
                gross_income = float(w2.gross_pay or 0)
                split = comp_split(db, w2)
                base_salary, rsu_income = split.salary, split.rsu_income
                tax_paid = (float(w2.federal_tax or 0) + float(w2.state_tax or 0)
                            + float(w2.social_security or 0) + float(w2.medicare or 0))
                pretax_401k = float(w2.pretax_401k or 0)
                roth_401k = float(w2.roth_401k or 0)
                contributions_401k = pretax_401k + roth_401k
                take_home = (gross_income - tax_paid - pretax_401k - roth_401k
                             - float(w2.cafeteria_125 or 0) - float(w2.transit or 0))
            else:
                gross_income = base_salary = rsu_income = tax_paid = None
                contributions_401k = take_home = None

            balances = _balances_for_year(db, year)
            row: dict[str, Any] = {
                "status": status,
                "gross_income": _cell(gross_income, status),
                "base_salary": _cell(base_salary, status),
                "rsu_income": _cell(rsu_income, status),
                "tax_paid": _cell(tax_paid, status),
                "take_home": _cell(take_home, status),
                "contributions_401k": _cell(contributions_401k, status),
            }
            row.update(_balance_metrics(balances, current_mortgage_balance, status))

        elif year == current_year:
            status = "forecast"
            ratio = 12.0 / current_month if current_month > 0 else 1.0
            w2 = w2_by_year.get(year)

            if w2:
                gross_income = float(w2.gross_pay or 0) * ratio
                base_salary = float(w2.base_salary or 0) * ratio
                rsu_income = float(w2.rsu_income or 0) * ratio
                tax_paid = (float(w2.federal_tax or 0) + float(w2.state_tax or 0)
                            + float(w2.social_security or 0) + float(w2.medicare or 0)) * ratio
                pretax_401k = float(w2.pretax_401k or 0) * ratio
                roth_401k = float(w2.roth_401k or 0) * ratio
                contributions_401k = pretax_401k + roth_401k
                take_home = (gross_income - tax_paid - pretax_401k - roth_401k
                             - float(w2.cafeteria_125 or 0) * ratio
                             - float(w2.transit or 0) * ratio)
            else:
                # No W2 yet for current year — use vest schedule + last year's base salary as estimate
                rsu_income = rsu_vest_by_year.get(year)
                last_w2 = w2_by_year.get(year - 1)
                if last_w2 and rsu_income is not None:
                    base_salary = float(last_w2.base_salary or 0)
                    gross_income = base_salary + rsu_income
                    tax_paid = base_salary * 0.30 + rsu_income * 0.40  # rough estimate
                    contributions_401k = min(base_salary * employee_401k_rate, 23500.0)
                    take_home = gross_income - tax_paid - contributions_401k
                else:
                    gross_income = base_salary = rsu_income = tax_paid = None
                    contributions_401k = take_home = None

            balances = _latest_balances(db)
            row = {
                "status": status,
                "gross_income": _cell(gross_income, status),
                "base_salary": _cell(base_salary, status),
                "rsu_income": _cell(rsu_income, status),
                "tax_paid": _cell(tax_paid, status),
                "take_home": _cell(take_home, status),
                "contributions_401k": _cell(contributions_401k, status),
            }
            row.update(_balance_metrics(balances, current_mortgage_balance, status))

        else:
            status = "plan"
            proj = proj_by_year.get(year)

            if proj:
                gross_income = float(proj.total_comp or 0)
                base_salary = float(proj.salary or 0)
                rsu_income_val = float(proj.rsu_income or 0)

                # Override with actual vest schedule if we have data for this year
                if year in rsu_vest_by_year:
                    rsu_income_val = rsu_vest_by_year[year]
                    gross_income = base_salary + rsu_income_val

                rsu_tax_rate = assumption_map.get("rsu_tax_rate", 0.40)
                tax_paid = base_salary * 0.35 + rsu_income_val * rsu_tax_rate
                years_elapsed = year - current_year
                irs_limit = 23500.0 * (1 + inflation) ** years_elapsed
                contributions_401k = min(base_salary * employee_401k_rate, irs_limit)
                take_home = gross_income - tax_paid - contributions_401k

                inv_bal = float(proj.investments or 0) + float(proj.company_stock or 0)
                ret_bal = float(proj.retirement_bal or 0)
                home_eq = float(proj.home_equity or 0)
                net_worth_val = float(proj.net_worth or 0)
                liquid_nw = net_worth_val - home_eq - ret_bal

                # Count vest events for this year
                rsu_source = "vest_schedule" if year in rsu_vest_by_year else "projection"
                rsu_vest_count = sum(1 for ve in vest_events if ve.vest_date.year == year) if rsu_source == "vest_schedule" else 0

                row = {
                    "status": status,
                    "_meta": {
                        "rsu_source": rsu_source,
                        "rsu_vest_count": rsu_vest_count,
                    },
                    "gross_income": _cell(gross_income, status),
                    "base_salary": _cell(base_salary, status),
                    "rsu_income": _cell(rsu_income_val, status),
                    "tax_paid": _cell(tax_paid, status),
                    "take_home": _cell(take_home, status),
                    "contributions_401k": _cell(contributions_401k, status),
                    "net_worth": _cell(net_worth_val, status),
                    "liquid_net_worth": _cell(liquid_nw, status),
                    "investment_balance": _cell(inv_bal, status),
                    "retirement_balance": _cell(ret_bal, status),
                    "home_equity": _cell(home_eq, status),
                    "mortgage_balance": _cell(None, status),
                }
            else:
                row = {"status": status}
                for m in _PLAN_METRICS:
                    row[m] = _cell(None, status)

        rows_out[str(year)] = row

    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "years": years,
        "metrics": _PLAN_METRICS,
        "rows": rows_out,
        "current_age": user_age,
        "retirement_age": retirement_age,
        "retirement_year": retirement_year,
    }


def _find_year_nw(rows, target_year: int) -> float:
    """Find net_worth for a given year in projection rows."""
    for r in rows:
        if r.year == target_year:
            return r.net_worth
    # If target year beyond projection, return last year
    return rows[-1].net_worth if rows else 0.0
