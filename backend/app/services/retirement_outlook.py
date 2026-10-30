"""Planning v2: the household's starting point, a plan's inputs, and the outlook the Planning page draws.

Reads only, except the household birth date (set_birth_date). Plan and life-event writes live in
planning_service.py. Research behind the defaults: docs/requirements/planning-v2.md.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import retirement_sim as rs
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant, VestEvent
from app.models.planning import ContributionConfig, HouseholdProfile, PlanVersion
from app.models.property import Mortgage
from app.models.retirement import RetirementAccount
from app.models.transaction import Transaction
from app.services.compensation import comp_split, latest_w2
from app.services.plan_assumptions import ASSUMPTIONS, BY_KEY
from app.services.spending_rules import spending_filter

logger = logging.getLogger("tallied.planning")

N_PATHS = 1000          # headline Monte Carlo
N_PATHS_SCENARIO = 500  # each macro scenario
N_PATHS_SEEK = 400      # goal-seek, curves, sensitivity, event impacts
N_PATHS_SPRINT = 300    # the sprint grid (many bisections)


class BirthDateMissing(ValueError):
    """The household has no birth date yet; the page asks for it instead of assuming an age."""

    def __init__(self) -> None:
        super().__init__("Set the household's birth date first: the plan computes age from it.")


# ---------------------------------------------------------------------------
# Household
# ---------------------------------------------------------------------------
def household_profile(db: Session) -> HouseholdProfile | None:
    return db.execute(select(HouseholdProfile).order_by(HouseholdProfile.id).limit(1)).scalar_one_or_none()


def set_birth_date(db: Session, birth_date: date) -> HouseholdProfile:
    if birth_date > date.today() or birth_date.year < 1900:
        raise ValueError("Birth date must be in the past and after 1900")
    profile = household_profile(db)
    if profile is None:
        profile = HouseholdProfile(birth_date=birth_date)
        db.add(profile)
    else:
        profile.birth_date = birth_date
    db.commit()
    db.refresh(profile)
    return profile


def age_on(birth_date: date, today: date) -> int:
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def milestones(birth_date: date) -> list[dict]:
    """The ages at which money and cover become available, for the timeline."""
    fra = rs.full_retirement_age(birth_date.year)
    fra_label = f"{int(fra)}" + (f" and {round((fra % 1) * 12)} months" if fra % 1 else "")
    return [
        {"age": 55, "label": "55", "title": "Rule of 55",
         "detail": "Leave your employer in or after the year you turn 55 and that employer's 401(k) pays out without the 10% penalty."},
        {"age": 59.5, "label": "59½", "title": "Penalty-free 401(k) and IRA",
         "detail": "Withdrawals from any 401(k) or IRA avoid the 10% early-withdrawal penalty."},
        {"age": 62, "label": "62", "title": "Earliest Social Security",
         "detail": "Benefits can start, reduced about 30% from the full-age amount when full age is 67."},
        {"age": 65, "label": "65", "title": "Medicare",
         "detail": "Medicare replaces marketplace or COBRA cover."},
        {"age": fra, "label": f"{fra:g}" if fra % 1 == 0 else "FRA", "title": f"Full retirement age ({fra_label})",
         "detail": "Social Security pays the full benefit (born 1960 or later: 67)."},
        {"age": 70, "label": "70", "title": "Largest Social Security",
         "detail": "Delayed credits stop: 124% of the full-age benefit when full age is 67."},
    ]


# ---------------------------------------------------------------------------
# Starting point
# ---------------------------------------------------------------------------
def _latest_balances_by_group(db: Session) -> tuple[dict[str, float], date | None]:
    latest = (
        select(BalanceSnapshot.account_id, func.max(BalanceSnapshot.snapshot_date).label("d"))
        .group_by(BalanceSnapshot.account_id)
        .subquery()
    )
    rows = db.execute(
        select(Account.display_group, func.sum(BalanceSnapshot.balance), func.max(BalanceSnapshot.snapshot_date))
        .join(latest, Account.id == latest.c.account_id)
        .join(BalanceSnapshot, (BalanceSnapshot.account_id == Account.id) & (BalanceSnapshot.snapshot_date == latest.c.d))
        .where(Account.is_active.is_(True), Account.include_in_nw.is_(True))
        .group_by(Account.display_group)
    ).all()
    out: dict[str, float] = {}
    as_of: date | None = None
    for group, total, d in rows:
        key = (group or "other").lower().replace(" ", "_")
        out[key] = out.get(key, 0.0) + float(total or 0)
        if d and (as_of is None or d > as_of):
            as_of = d
    return out, as_of


def _company_price(db: Session, symbol: str) -> float | None:
    from app.services.stock_price import get_or_fetch_price
    try:
        return get_or_fetch_price(db, symbol)
    except Exception:  # a price outage must not take the page down; the starting point says so
        logger.warning("Planning: no price for %s; company stock and vests valued at 0", symbol, exc_info=True)
        return None


def starting_point(db: Session, birth_date: date, today: date | None = None) -> tuple[rs.Household, dict]:
    """The household as the database has it today, plus a description of where each figure came from."""
    today = today or date.today()
    groups, balances_as_of = _latest_balances_by_group(db)

    w2 = latest_w2(db)
    split = comp_split(db, w2)

    mortgage = db.execute(select(Mortgage).order_by(Mortgage.updated_at.desc()).limit(1)).scalar_one_or_none()
    mortgage_balance = float(mortgage.current_balance or 0) if mortgage else 0.0
    home_equity = groups.get("home_equity", 0.0)
    home_value = home_equity + mortgage_balance if (home_equity or mortgage_balance) else 0.0
    payment = float(mortgage.monthly_payment) if mortgage else 0.0
    escrow = min(float(mortgage.escrow or 0), payment) if mortgage else 0.0

    grants = db.execute(select(RSUGrant)).scalars().all()
    symbol = next((g.symbol for g in grants if g.symbol), None)
    price = _company_price(db, symbol) if symbol else None
    sellable = sum(g.sellable_shares or 0 for g in grants)
    company_from_balances = groups.get("company_stock", 0.0)
    company_stock = company_from_balances if company_from_balances else (sellable * price if price else 0.0)

    scheduled: dict[int, float] = {}
    vest_count = 0
    last_vest: date | None = None
    if price:
        for ve in db.execute(
            select(VestEvent).where(VestEvent.is_actual.is_(False), VestEvent.vest_date > today)
        ).scalars():
            period = int((ve.vest_date - today).days // 365.25)
            scheduled[period] = scheduled.get(period, 0.0) + float(ve.shares or 0) * price
            vest_count += 1
            last_vest = ve.vest_date if last_vest is None or ve.vest_date > last_vest else last_vest

    spent = db.execute(
        spending_filter(select(func.coalesce(func.sum(Transaction.amount), 0)))
        .where(Transaction.date > today - timedelta(days=365), Transaction.date <= today)
    ).scalar()
    spending_12m = abs(float(spent or 0))

    contrib = db.execute(
        select(ContributionConfig).order_by(ContributionConfig.effective_date.desc()).limit(1)
    ).scalar_one_or_none()
    irs_limit = float(contrib.annual_irs_limit) if contrib and contrib.annual_irs_limit else 23_500.0
    k401 = db.execute(
        select(RetirementAccount).order_by(RetirementAccount.statement_end.desc().nullslast()).limit(1)
    ).scalar_one_or_none()
    roth_basis = float(k401.roth_basis or 0) if k401 else 0.0

    household = rs.Household(
        start_year=today.year,
        current_age=age_on(birth_date, today),
        cash=groups.get("cash", 0.0) + groups.get("credit_cards", 0.0),
        taxable=groups.get("investments", 0.0),
        company_stock=company_stock,
        retirement=groups.get("retirement", 0.0),
        home_value=home_value,
        mortgage_balance=mortgage_balance,
        mortgage_rate=float(mortgage.rate) if mortgage else 0.0,
        mortgage_payment_monthly=payment,
        salary=split.salary,
        rsu_income=split.rsu_income,
        scheduled_vests=scheduled,
        spending_last_12m=spending_12m,
        irs_401k_limit=irs_limit,
        escrow_monthly=escrow,
        roth_basis=roth_basis,
        full_retirement_age=rs.full_retirement_age(birth_date.year),
    )
    described = {
        "balances_as_of": balances_as_of.isoformat() if balances_as_of else None,
        "cash": round(household.cash, 2),
        "taxable": round(household.taxable, 2),
        "company_stock": round(company_stock, 2),
        "company_stock_source": "balances" if company_from_balances else ("sellable_shares" if company_stock else "none"),
        "company_symbol": symbol,
        "company_price": price,
        "retirement": round(household.retirement, 2),
        "roth_basis": round(min(roth_basis, household.retirement), 2),
        "home_value": round(home_value, 2),
        "mortgage_balance": round(mortgage_balance, 2),
        "mortgage_payment_monthly": payment,
        "escrow_monthly": escrow,
        "mortgage_rate": household.mortgage_rate,
        "salary": round(split.salary, 2),
        "rsu_income": round(split.rsu_income, 2),
        "comp_source": split.source,
        "w2_year": w2.tax_year if w2 else None,
        "scheduled_vest_value": round(sum(scheduled.values()), 2),
        "scheduled_vest_count": vest_count,
        "last_scheduled_vest": last_vest.isoformat() if last_vest else None,
        "spending_last_12m": round(spending_12m, 2),
        "irs_401k_limit": irs_limit,
        "investable": round(household.cash + household.taxable + company_stock + household.retirement, 2),
        "full_retirement_age": household.full_retirement_age,
    }
    return household, described


# ---------------------------------------------------------------------------
# What will retirement cost? (derived from actual spending, with its uncertainty)
# ---------------------------------------------------------------------------
WORK_COST_CATEGORIES = ("gas", "fuel", "parking", "tolls", "transit", "public transportation", "commute", "commuting",
                        "rideshare", "auto & transport", "transportation")
UNCATEGORISED = ("", "uncategorized", "uncategorised", "other", "misc", "miscellaneous")
# Population references (labelled as such on the page).
BLS_CE = {"year": 2024, "all": 78_535, "age_65_plus": 61_432, "age_65_74": 65_354, "age_75_plus_2023": 53_031}


def spending_builder(db: Session, household: rs.Household, values: dict[str, float],
                     today: date | None = None) -> dict:
    """Retirement living spending built up from the last 12 months of actual spending.

    Living spending excludes the mortgage and escrow (the plan adds housing itself) and health cover
    (the plan adds marketplace premiums before 65 and Medicare costs after). Today's out-of-pocket
    medical bills stay in, because they are in the transactions.
    """
    today = today or date.today()
    since = today - timedelta(days=365)
    rows = db.execute(
        spending_filter(select(Transaction.date, Transaction.amount, Transaction.category, Transaction.merchant))
        .where(Transaction.date > since, Transaction.date <= today)
    ).all()
    total = sum(-float(a or 0) for _, a, _, _ in rows)
    by_month: dict[str, float] = {}
    for d, a, _, _ in rows:
        key = d.strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0.0) + -float(a or 0)
    months = [by_month[k] for k in sorted(by_month)]
    median_month = statistics.median(months) if months else 0.0
    uncategorised = sum(-float(a or 0) for _, a, c, _ in rows if (c or "").strip().lower() in UNCATEGORISED)
    work = sum(-float(a or 0) for _, a, c, _ in rows if (c or "").strip().lower() in WORK_COST_CATEGORIES)
    # One-off spikes: single purchases far above the usual (at least $2,500 and 10x the median purchase)
    # in a category that does not recur most months (rent-like bills are not one-offs).
    amounts = sorted(-float(a or 0) for _, a, _, _ in rows)
    median_txn = statistics.median(amounts) if amounts else 0.0
    threshold = max(2_500.0, 10 * median_txn)
    months_by_category: dict[str, set[str]] = {}
    for d, _, c, _ in rows:
        months_by_category.setdefault((c or "").strip().lower(), set()).add(d.strftime("%Y-%m"))
    recurring = {c for c, ms in months_by_category.items() if len(ms) >= 6 and c not in UNCATEGORISED}
    spikes = sorted(
        [{"date": d.isoformat(), "merchant": m or "", "category": c or "", "amount": round(-float(a or 0), 2)}
         for d, a, c, m in rows
         if -float(a or 0) >= threshold and (c or "").strip().lower() not in recurring],
        key=lambda r: -r["amount"],
    )
    spike_total = sum(s["amount"] for s in spikes)
    reduction = values.get("commute_reduction", 0.5)
    base = total - spike_total
    suggested = max(0.0, base - work * reduction)

    w2 = db.execute(select(W2Record).order_by(W2Record.tax_year.desc()).limit(1)).scalar_one_or_none()
    payroll_tax = float((w2.social_security or 0) + (w2.medicare or 0)) if w2 else 0.0
    saving_401k = float((w2.pretax_401k or 0) + (w2.roth_401k or 0)) if w2 else 0.0
    pay = household.salary + household.rsu_income

    people = int(values.get("health_people", 1))
    fpl = 15_650 + 5_500 * max(0, people - 1)
    benchmark = people * values.get("aca_benchmark", 0.0)
    return {
        "window": {"from": since.isoformat(), "to": today.isoformat(), "months": len(months)},
        "trailing_total": round(total, 0),
        "median_month": round(median_month, 0),
        "monthly": [{"month": k, "total": round(by_month[k], 0)} for k in sorted(by_month)],
        "uncategorised": round(uncategorised, 0),
        "spikes": spikes[:8],
        "spike_total": round(spike_total, 0),
        "work_costs": round(work, 0),
        "work_reduction": reduction,
        "suggested": round(suggested, -2),
        "range": {"low": round(max(0.0, suggested - uncategorised * 0.5), -2), "high": round(total, -2)},
        "excluded": {
            "mortgage_pi_monthly": round(household.mortgage_payment_monthly - household.escrow_monthly, 2),
            "escrow_monthly": round(household.escrow_monthly, 2),
            "payroll_tax": round(payroll_tax, 0),
            "saving_401k": round(saving_401k, 0),
        },
        "health": {
            "people": people,
            "pre65_full": round(benchmark, 0),
            "pre65_capped_at": round(values.get("aca_income_cap", 0.0), 4),
            "subsidy_cliff_magi": round(rs.ACA_SUBSIDY_CLIFF_FPL * fpl, 0),
            "pre65_at_cliff": round(min(benchmark, values.get("aca_income_cap", 0.0) * rs.ACA_SUBSIDY_CLIFF_FPL * fpl), 0),
            "post65": round(people * values.get("medicare_cost", 0.0), 0),
            "ltc_reference": {"assisted_living": 70_800, "nursing_home_private": 127_750, "year": 2024},
        },
        "references": {
            "replacement_low": round(pay * 0.70, -2),
            "replacement_high": round(pay * 0.80, -2),
            "pay": round(pay, 0),
            "bls": BLS_CE,
        },
    }


# ---------------------------------------------------------------------------
# Plan inputs
# ---------------------------------------------------------------------------
def plan_values(plan: PlanVersion, overrides: dict[str, float] | None = None) -> dict[str, float]:
    """Every vocabulary key: the plan's stored value, else the default; then any what-if override."""
    stored = {a.key: float(a.value) for a in plan.assumptions}
    values = {a["key"]: stored.get(a["key"], float(a["value"])) for a in ASSUMPTIONS}
    for k, v in (overrides or {}).items():
        spec = BY_KEY.get(k)
        if spec is None:
            raise ValueError(f"Unknown assumption '{k}'")
        values[k] = min(float(spec["max"]), max(float(spec["min"]), float(v)))
    return values


def events_for(plan: PlanVersion, enabled_overrides: dict[int, bool] | None = None) -> list[rs.LifeEvent]:
    out = []
    for e in plan.events:
        enabled = e.enabled if not enabled_overrides or e.id not in enabled_overrides else enabled_overrides[e.id]
        out.append(rs.LifeEvent(kind=e.kind, start_age=e.start_age, end_age=e.end_age, amount=float(e.amount or 0),
                                pct=float(e.pct or 0), label=e.label, enabled=bool(enabled), params=dict(e.params or {})))
    return out


def to_inputs(values: dict[str, float], spending_rule: str, events: list[rs.LifeEvent],
              spending_profile: str = "flat") -> rs.PlanInputs:
    if spending_rule not in rs.SPENDING_RULES:
        raise ValueError(f"Unknown spending rule '{spending_rule}'")
    if spending_profile not in rs.SPENDING_PROFILES:
        raise ValueError(f"Unknown spending profile '{spending_profile}'")
    return rs.PlanInputs(
        retirement_age=int(values["retirement_age"]),
        plan_to_age=int(values["plan_to_age"]),
        total_comp_growth=values["total_comp_growth"],
        inflation=values["inflation"],
        rsu_pct_of_comp=values["rsu_pct_of_comp"],
        rsu_pct_annual_increase=values["rsu_pct_annual_increase"],
        rsu_pct_cap=values["rsu_pct_cap"],
        rsu_tax_rate=values["rsu_tax_rate"],
        rsu_hold_fraction=values["rsu_hold_fraction"],
        income_tax_rate=values["income_tax_rate"],
        employee_401k_rate=values["employee_401k_rate"],
        employer_match_rate=values["employer_match_rate"],
        monthly_cash_savings=values["monthly_cash_savings"],
        investment_return=values["investment_return"],
        retirement_return=values["retirement_return"],
        stock_price_growth=values["stock_price_growth"],
        home_appreciation=values["home_appreciation"],
        stock_allocation_working=values["stock_allocation_working"],
        stock_allocation_retired=values["stock_allocation_retired"],
        retirement_spending=values["retirement_spending"],
        retirement_tax_rate=values["retirement_tax_rate"],
        spending_rule=spending_rule,
        spending_profile=spending_profile,
        spending_floor=values["spending_floor"],
        ss_monthly_at_fra=values["ss_monthly_at_fra"],
        ss_claim_age=int(values["ss_claim_age"]),
        ss_payable_share=values["ss_payable_share"],
        health_people=int(values["health_people"]),
        aca_benchmark=values["aca_benchmark"],
        aca_income_cap=values["aca_income_cap"],
        medicare_cost=values["medicare_cost"],
        health_excess_inflation=values["health_excess_inflation"],
        use_sepp=values["use_sepp"] >= 0.5,
        payoff_mortgage=values["payoff_mortgage"] >= 0.5,
        events=events,
    )


def _plan_horizon_ok(inputs: rs.PlanInputs, household: rs.Household) -> None:
    if inputs.plan_to_age <= household.current_age:
        raise ValueError("Plan-to age must be above the current age")


def household_and_inputs(db: Session, plan: PlanVersion, overrides: dict[str, float] | None = None,
                         spending_rule: str | None = None, spending_profile: str | None = None,
                         event_enabled: dict[int, bool] | None = None, today: date | None = None):
    profile = household_profile(db)
    if profile is None or profile.birth_date is None:
        raise BirthDateMissing()
    values = plan_values(plan, overrides)
    household, start = starting_point(db, profile.birth_date, today)
    rule = spending_rule or plan.spending_rule or "fixed"
    shape = spending_profile or plan.spending_profile or "flat"
    inputs = to_inputs(values, rule, events_for(plan, event_enabled), shape)
    _plan_horizon_ok(inputs, household)
    return profile, values, household, start, inputs


# ---------------------------------------------------------------------------
# Expected path (also stored as plan_projections)
# ---------------------------------------------------------------------------
def expected_rows(inputs: rs.PlanInputs, household: rs.Household) -> list[dict]:
    """Year-by-year figures for the path where every return sits at its median (nominal dollars)."""
    res = rs.run(inputs, household, rs.expected_market(inputs, household))
    d = res.detail
    rows = []
    r_age = _effective_retirement_age(inputs)
    for t, (age, year) in enumerate(zip(res.ages, res.years)):
        working = age < r_age
        liquid = float(d["cash"][t] + d["taxable"][t] + d["company_stock"][t] + d["retirement"][t])
        row = {"year": year, "age": age, "phase": "working" if working else "retired"}
        for key in ("salary", "rsu_income", "saved", "contrib_401k", "spending", "withdrawal", "social_security",
                    "other_income", "healthcare", "housing", "src_taxable", "src_roth_basis", "src_401k",
                    "src_401k_penalty", "equity_payout", "mortgage_payoff", "gap_costs", "extra_spend", "magi"):
            row[key] = round(float(d[key][t]), 2)
        row.update({
            "total_comp": round(float(d["salary"][t] + d["rsu_income"][t]), 2),
            "cash": round(float(d["cash"][t]), 2),
            "investments": round(float(d["taxable"][t]), 2),
            "company_stock": round(float(d["company_stock"][t]), 2),
            "retirement_bal": round(float(d["retirement"][t]), 2),
            "home_equity": round(float(d["home_equity"][t]), 2),
            "net_worth": round(liquid + float(d["home_equity"][t]), 2),
            "liquid_real": round(float(res.liquid_real[0, t]), 2),
            "net_worth_real": round(float(res.net_worth_real[0, t]), 2),
            "deflator": round(float(d["price_index"][t]) or 1.0, 6),
        })
        rows.append(row)
    return rows


def _effective_retirement_age(inputs: rs.PlanInputs) -> int:
    for e in inputs.events:
        if e.enabled and e.kind == "layoff" and rs.layoff_params(e)["never_reemployed"] and e.start_age < inputs.retirement_age:
            return e.start_age
    return inputs.retirement_age


# ---------------------------------------------------------------------------
# Outlook
# ---------------------------------------------------------------------------
SENSITIVITY_LEVERS: tuple[tuple[str, str, float], ...] = (
    # key, how to vary ("abs" adds +/-, "rel" multiplies), size
    ("retirement_age", "abs", 3),
    ("retirement_spending", "rel", 0.2),
    ("total_comp_growth", "abs", 0.01),
    ("investment_return", "abs", 0.01),
    ("retirement_return", "abs", 0.01),
    ("inflation", "abs", 0.01),
    ("monthly_cash_savings", "rel", 0.5),
    ("stock_price_growth", "abs", 0.05),
    ("stock_allocation_retired", "abs", 0.2),
    ("ss_claim_age", "abs", 3),
)


def _summary(res: rs.SimResult, inputs: rs.PlanInputs) -> dict:
    i = res.retirement_index
    end = res.liquid_real[:, -1]
    at_ret = res.liquid_real[:, i - 1] if i > 0 else res.liquid_real[:, 0]
    failed = ~res.success
    retired_cols = res.spending_real[:, i:] if i < res.spending_real.shape[1] else res.spending_real[:, :0]
    return {
        "success_rate": round(res.success_rate, 4),
        "paths": int(res.success.size),
        "median_at_retirement": round(float(np.median(at_ret)), 0),
        "p10_at_retirement": round(float(np.percentile(at_ret, 10)), 0),
        "median_at_end": round(float(np.median(end)), 0),
        "p10_at_end": round(float(np.percentile(end, 10)), 0),
        "p90_at_end": round(float(np.percentile(end, 90)), 0),
        "median_failure_age": float(np.nanmedian(res.depleted_age[failed])) if failed.any() else None,
        "earliest_failure_age": float(np.nanmin(res.depleted_age[failed])) if failed.any() else None,
        "spending_p10_lowest": round(float(np.percentile(retired_cols.min(axis=1), 10)), 0) if retired_cols.size else None,
        "spending_median": round(float(np.median(retired_cols)), 0) if retired_cols.size else None,
        "prob_spending_cut": round(float((res.cut_count > 0).mean()), 4),
        "prob_below_floor": round(float((res.min_spending_ratio < inputs.spending_floor).mean()), 4),
    }


def _warnings(values: dict[str, float], start: dict) -> list[dict]:
    warnings = []
    if values["ss_monthly_at_fra"] <= 0:
        warnings.append({"key": "social_security", "text": "Social Security is not counted. Enter the full-age monthly estimate from ssa.gov/myaccount."})
    if start["comp_source"] == "vests":
        warnings.append({"key": "comp", "text": f"The {start['w2_year']} W-2 has gross pay only; salary is gross minus that year's RSU vests."})
    if start["comp_source"] == "none":
        warnings.append({"key": "comp", "text": "No W-2 on file, so there is no salary in the plan. Add one in Settings, Income."})
    if start["company_symbol"] and not start["company_price"]:
        warnings.append({"key": "price", "text": f"No price for {start['company_symbol']} today; company stock and scheduled vests count as $0."})
    return warnings


def nest_egg(inputs: rs.PlanInputs, household: rs.Household) -> dict:
    """What nest egg the plan's first retired year needs, by withdrawal rule and horizon.

    The need is living spending plus health care and housing in the first retired year, less Social
    Security and other income then, grossed up for tax (today's dollars, plan line).
    """
    rows = expected_rows(inputs, household)
    r_age = _effective_retirement_age(inputs)
    first = next((r for r in rows if r["age"] == r_age), None)
    spending_gross = inputs.retirement_spending / (1 - inputs.retirement_tax_rate) if inputs.retirement_tax_rate < 1 else inputs.retirement_spending
    need = spending_gross
    if first:
        defl = first["deflator"] / (1 + inputs.inflation)  # start-of-period price index
        net = (first["spending"] + first["healthcare"] + first["housing"] + first["extra_spend"]
               - first["social_security"] - first["other_income"] * (1 - inputs.income_tax_rate)) / max(defl, 1e-9)
        need = max(0.0, net) / (1 - inputs.retirement_tax_rate) if inputs.retirement_tax_rate < 1 else max(0.0, net)
    horizon_plan = inputs.plan_to_age - r_age + 1
    real_ret = (1 + inputs.retirement_return) / (1 + inputs.inflation) - 1
    horizons = sorted({30, 40, 50, 60, horizon_plan})
    out = []
    for h in horizons:
        hist = rs.historical_withdrawal_rates(inputs.stock_allocation_retired, h)
        vpw = rs._vpw_rate(real_ret, h)
        out.append({
            "horizon": h, "is_plan": h == horizon_plan,
            "fixed_worst": hist["worst"] if hist else None,
            "fixed_worst_start": hist["worst_start"] if hist else None,
            "fixed_p10": hist["p10"] if hist else None,
            "cohorts": hist["cohorts"] if hist else 0,
            "vpw_first_year": round(vpw, 4),
            "nest_egg_fixed_worst": round(need / hist["worst"], -3) if hist else None,
            "nest_egg_fixed_p10": round(need / hist["p10"], -3) if hist else None,
            "nest_egg_vpw": round(need / vpw, -3) if vpw > 0 else None,
        })
    return {
        "need_first_year": round(need, -2),
        "spending_gross": round(spending_gross, -2),
        "stock_share": inputs.stock_allocation_retired,
        "rows": out,
        "references": [
            {"label": "Bengen (1994): fixed real, 30 years, every US period", "rate": 0.04},
            {"label": "Morningstar (Dec 2025): 30 years, 90% success, for 2026 retirees", "rate": 0.039},
            {"label": "Early Retirement Now fail-safe: 30 / 40 / 50 / 60 years", "rates": [0.0382, 0.0358, 0.0335, 0.0325]},
            {"label": "Guyton-Klinger (2006): guardrails starting rate, 99% confidence, 65%+ stocks", "rates": [0.052, 0.056]},
        ],
    }


def outlook(db: Session, plan: PlanVersion, overrides: dict[str, float] | None = None,
            spending_rule: str | None = None, regime_key: str = "base",
            event_enabled: dict[int, bool] | None = None, include_analysis: bool = True,
            spending_profile: str | None = None, today: date | None = None) -> dict:
    profile, values, household, start, inputs = household_and_inputs(
        db, plan, overrides, spending_rule, spending_profile, event_enabled, today)
    regime = rs.REGIME_BY_KEY.get(regime_key)
    if regime is None:
        raise ValueError(f"Unknown scenario '{regime_key}'")
    target = values["success_target"]

    market = rs.simulate_market(inputs, household, N_PATHS, rs.DEFAULT_SEED, regime)
    res = rs.run(inputs, household, market)
    rows = expected_rows(inputs, household)
    r_age = _effective_retirement_age(inputs)

    starts, hist_market = rs.historical_cohort_markets(replace(inputs, retirement_age=r_age), household)
    cohorts = []
    hist_rate = None
    if starts:
        hist = rs.run(inputs, household, hist_market)
        i = hist.retirement_index
        hist_rate = round(hist.success_rate, 4)
        for k, y in enumerate(starts):
            cohorts.append({
                "start_year": y,
                "success": bool(hist.success[k]),
                "end_real": round(float(hist.liquid_real[k, -1]), 0),
                "lowest_real": round(float(hist.liquid_real[k, i:].min()), 0),
                "failure_age": float(hist.depleted_age[k]) if not hist.success[k] else None,
            })

    out: dict = {
        "plan": {"id": plan.id, "name": plan.name, "spending_rule": inputs.spending_rule,
                 "spending_profile": inputs.spending_profile},
        "today": (today or date.today()).isoformat(),
        "birth_date": profile.birth_date.isoformat(),
        "current_age": household.current_age,
        "retirement_age": r_age,
        "planned_retirement_age": inputs.retirement_age,
        "plan_to_age": inputs.plan_to_age,
        "success_target": target,
        "regime": regime_key,
        "milestones": milestones(profile.birth_date),
        "starting_point": start,
        "warnings": _warnings(values, start),
        "values": values,
        "history_reference": {
            "working": rs.history_mix_stats(inputs.stock_allocation_working),
            "retired": rs.history_mix_stats(inputs.stock_allocation_retired),
        },
        "summary": {**_summary(res, inputs), "historical_success_rate": hist_rate,
                    "historical_cohorts": len(starts),
                    "plan_line_runs_out_at": rows_runout_age(rows, r_age)},
        "fan": {
            "ages": res.ages, "years": res.years,
            "liquid": rs.fan(res.liquid_real), "net_worth": rs.fan(res.net_worth_real),
            "plan_line": [r["liquid_real"] for r in rows],
            "spending": rs.fan(res.spending_real),
        },
        "rows": rows,
        "cohorts": cohorts,
        "events": [
            {"id": e.id, "kind": e.kind, "label": e.label, "start_age": e.start_age, "end_age": e.end_age,
             "amount": float(e.amount or 0), "pct": float(e.pct or 0), "params": dict(e.params or {}),
             "enabled": (event_enabled or {}).get(e.id, bool(e.enabled))}
            for e in plan.events
        ],
        "spending_builder": spending_builder(db, household, values, today),
        "nest_egg": nest_egg(inputs, household),
    }
    if include_analysis:
        out.update(analysis(inputs, household, target, plan, event_enabled, regime))
    return out


def rows_runout_age(rows: list[dict], r_age: int) -> int | None:
    """First retired age on the plan line where investable money is gone."""
    for r in rows:
        if r["age"] >= r_age and r["liquid_real"] <= 1.0:
            return r["age"]
    return None


def analysis(inputs: rs.PlanInputs, household: rs.Household, target: float, plan: PlanVersion,
             event_enabled: dict[int, bool] | None = None, regime: rs.Regime | None = None) -> dict:
    """Scenarios, goal-seek, sensitivity and per-event outcomes, under the selected macro scenario.
    Same seed everywhere, so differences come from the lever, not luck."""
    scenarios = []
    for reg in rs.REGIMES:
        r = rs.run(inputs, household, rs.simulate_market(inputs, household, N_PATHS_SCENARIO, rs.DEFAULT_SEED, reg))
        scenarios.append({
            "key": reg.key, "label": reg.label, "description": reg.description,
            "success_rate": round(r.success_rate, 4),
            "median_end": round(float(np.median(r.liquid_real[:, -1])), 0),
            "p10_end": round(float(np.percentile(r.liquid_real[:, -1], 10)), 0),
            "median_at_retirement": round(float(np.median(r.liquid_real[:, max(0, r.retirement_index - 1)])), 0),
        })

    g = rs.goal_seek(inputs, household, target, N_PATHS_SEEK, regime=regime)
    base_rate = rs.success_rate(inputs, household, N_PATHS_SEEK, regime=regime)

    sensitivity = []
    for key, how, size in SENSITIVITY_LEVERS:
        if key == "ss_claim_age" and inputs.ss_monthly_at_fra <= 0:
            continue
        spec = BY_KEY[key]
        base_v = float(getattr(inputs, key))
        lo_v = base_v - size if how == "abs" else base_v * (1 - size)
        hi_v = base_v + size if how == "abs" else base_v * (1 + size)
        lo_v = max(float(spec["min"]), lo_v)
        hi_v = min(float(spec["max"]), hi_v)
        if key in ("retirement_age", "ss_claim_age"):
            lo_v, hi_v = round(lo_v), round(hi_v)
            if key == "retirement_age":
                lo_v = max(lo_v, household.current_age + 1)
        lo_r = rs.success_rate(replace(inputs, **{key: lo_v}), household, N_PATHS_SEEK, regime=regime)
        hi_r = rs.success_rate(replace(inputs, **{key: hi_v}), household, N_PATHS_SEEK, regime=regime)
        sensitivity.append({
            "key": key, "label": spec["display_name"], "unit": spec["unit"], "base_value": base_v,
            "low_value": lo_v, "high_value": hi_v,
            "success_low": round(lo_r, 4), "success_high": round(hi_r, 4),
        })
    sensitivity.sort(key=lambda s: abs(s["success_high"] - s["success_low"]), reverse=True)

    impacts = []
    outcomes = []
    for e in plan.events:
        on = (event_enabled or {}).get(e.id, bool(e.enabled))
        if not on:
            continue
        others = events_for(plan, {**(event_enabled or {}), e.id: False})
        without_inputs = replace(inputs, events=others)
        without = rs.success_rate(without_inputs, household, N_PATHS_SEEK, regime=regime)
        impacts.append({"id": e.id, "success_without": round(without, 4), "success_with": round(base_rate, 4)})
        if e.kind in ("layoff", "job_loss", "acquisition"):
            outcomes.append(_event_outcome(e, inputs, household, target, base_rate, without, regime))

    return {
        "scenarios": scenarios,
        "goal_seek": {
            "target": g.target,
            "base_success": round(base_rate, 4),
            "max_spending": g.max_spending,
            "earliest_retirement_age": g.earliest_retirement_age,
            "extra_monthly_savings": g.extra_monthly_savings,
            "required_return_shift": g.required_return_shift,
            "required_investment_return": round(inputs.investment_return + g.required_return_shift, 4)
            if g.required_return_shift is not None else None,
            "required_retirement_return": round(inputs.retirement_return + g.required_return_shift, 4)
            if g.required_return_shift is not None else None,
            "by_age": g.by_age,
            "by_spending": g.by_spending,
        },
        "sensitivity": sensitivity,
        "event_impacts": impacts,
        "event_outcomes": outcomes,
    }


def _event_outcome(e, inputs: rs.PlanInputs, household: rs.Household, target: float, with_rate: float,
                   without_rate: float, regime: rs.Regime | None) -> dict:
    """For a career shock: does the money run out and when, and what part-time income would fix it."""
    line = rs.run(inputs, household, rs.expected_market(inputs, household))
    mc = rs.run(inputs, household, rs.simulate_market(inputs, household, N_PATHS_SEEK, rs.DEFAULT_SEED, regime))
    failed = ~mc.success
    start = e.start_age
    end = inputs.retirement_age - 1 if inputs.retirement_age > start else start
    end = max(end, start)
    return {
        "id": e.id, "label": e.label, "kind": e.kind,
        "success_with": round(with_rate, 4), "success_without": round(without_rate, 4),
        "plan_line_runs_out_at": float(line.depleted_age[0]) if not line.success[0] else None,
        "median_failure_age": float(np.nanmedian(mc.depleted_age[failed])) if failed.any() else None,
        "share_running_out": round(float(failed.mean()), 4),
        "income_window": [start, end],
        "income_for_plan_line": rs.min_income_plan_line_solvent(inputs, household, start, end),
        "income_to_restore": rs.min_bridge_income(inputs, household, start, end, without_rate, N_PATHS_SEEK,
                                                  regime=regime) if with_rate < without_rate else 0.0,
        "income_for_target": rs.min_bridge_income(inputs, household, start, end, target, N_PATHS_SEEK, regime=regime),
    }


# ---------------------------------------------------------------------------
# Sprint to retirement
# ---------------------------------------------------------------------------
SPRINT_SHIFTS = (-0.02, -0.01, 0.0, 0.01)


def sprint(db: Session, plan: PlanVersion, overrides: dict[str, float] | None = None, spending_rule: str | None = None,
           spending_profile: str | None = None, event_enabled: dict[int, bool] | None = None,
           regime_key: str = "base", today: date | None = None) -> dict:
    """Save as hard as possible now (401(k) at the IRS limit, every equity payout invested), then:
    for each retirement age and return assumption, the most living spending that reaches the target;
    for each spending level, the earliest age; and which levers move the answer most."""
    _, values, household, _, inputs = household_and_inputs(
        db, plan, overrides, spending_rule, spending_profile, event_enabled, today)
    regime = rs.REGIME_BY_KEY.get(regime_key)
    if regime is None:
        raise ValueError(f"Unknown scenario '{regime_key}'")
    target = values["success_target"]
    s_inputs = rs.sprint_inputs(inputs)
    lo = household.current_age + 1
    ages = sorted(set(range(max(lo, 40), min(inputs.plan_to_age - 10, 70) + 1, 2)) | {max(lo, inputs.retirement_age)})
    grid = rs.sprint_grid(s_inputs, household, target, ages, list(SPRINT_SHIFTS), N_PATHS_SPRINT, regime=regime)
    col = SPRINT_SHIFTS.index(0.0)
    spend0 = max(values["retirement_spending"], 1.0)
    levels = sorted({round(spend0 * m, -3) for m in (0.6, 0.7, 0.8, 0.9, 1.0, 1.2)})
    by_spending = [
        {"spending": lvl, "earliest_age": [rs.earliest_age_for(grid, c, lvl) for c in range(len(SPRINT_SHIFTS))]}
        for lvl in levels
    ]

    # Which levers matter most for the sprint, measured on chance of success at the plan's retirement age.
    base = rs.success_rate(s_inputs, household, N_PATHS_SEEK, regime=regime)
    layoff = next((e for e in s_inputs.events if e.enabled and e.kind == "layoff"), None)
    synthetic = layoff is None
    job_change = layoff or rs.LifeEvent("layoff", min(household.current_age + 2, max(household.current_age, s_inputs.retirement_age - 1)),
                                        label="job change", params={"gap_months": 6, "next_pay_pct": 1.0, "next_equity": 1})

    def with_job(**params) -> rs.PlanInputs:
        ev = rs.LifeEvent("layoff", job_change.start_age, label="job change",
                          params={**rs.layoff_params(job_change), **params})
        rest = [x for x in s_inputs.events if x is not layoff]
        return replace(s_inputs, events=[*rest, ev])

    jp = rs.layoff_params(job_change)
    job_base = with_job()
    job_base_rate = rs.success_rate(job_base, household, N_PATHS_SEEK, regime=regime)
    levers = []

    def add(label: str, lo_label: str, hi_label: str, lo_in: rs.PlanInputs, hi_in: rs.PlanInputs, base_rate: float):
        levers.append({
            "label": label, "low_label": lo_label, "high_label": hi_label, "base": round(base_rate, 4),
            "success_low": round(rs.success_rate(lo_in, household, N_PATHS_SEEK, regime=regime), 4),
            "success_high": round(rs.success_rate(hi_in, household, N_PATHS_SEEK, regime=regime), 4),
        })

    sp = s_inputs.retirement_spending
    add("Living spending", f"${sp * 0.8:,.0f}", f"${sp * 1.2:,.0f}",
        replace(s_inputs, retirement_spending=sp * 0.8), replace(s_inputs, retirement_spending=sp * 1.2), base)
    add("Returns", "1 point lower", "1 point higher",
        replace(s_inputs, investment_return=s_inputs.investment_return - 0.01, retirement_return=s_inputs.retirement_return - 0.01),
        replace(s_inputs, investment_return=s_inputs.investment_return + 0.01, retirement_return=s_inputs.retirement_return + 0.01), base)
    add("Pay after a job change", "70% of today's", "120% of today's",
        with_job(next_pay_pct=0.7), with_job(next_pay_pct=1.2), job_base_rate)
    add("New equity grants", "none", "at today's share", with_job(next_equity=0), with_job(next_equity=1), job_base_rate)
    add("Gap between jobs", f"{max(0, jp['gap_months'] - 6):g} months", f"{jp['gap_months'] + 6:g} months",
        with_job(gap_months=max(0, jp["gap_months"] - 6)), with_job(gap_months=jp["gap_months"] + 6), job_base_rate)
    levers.sort(key=lambda x: abs(x["success_high"] - x["success_low"]), reverse=True)

    return {
        "target": target,
        "settings": {"employee_401k": "IRS limit", "equity": "every payout sold and invested",
                     "irs_401k_limit": household.irs_401k_limit},
        "shifts": list(SPRINT_SHIFTS),
        "return_labels": [f"{(s_inputs.investment_return + s) * 100:.1f}% / {(s_inputs.retirement_return + s) * 100:.1f}%"
                          for s in SPRINT_SHIFTS],
        "grid": grid,
        "by_spending": by_spending,
        "plan_spending": spend0,
        "earliest_at_plan_spending": rs.earliest_age_for(grid, col, spend0),
        "base_success": round(base, 4),
        "levers": levers,
        "job_change": {"age": job_change.start_age, "synthetic": synthetic, "params": jp},
    }


def catalogue() -> dict:
    """Life-event templates, macro scenarios and the assumption vocabulary (one list, from the engine)."""
    return {
        "regimes": [{"key": r.key, "label": r.label, "description": r.description} for r in rs.REGIMES],
        "spending_rules": [
            {"key": "fixed", "label": "Fixed",
             "description": "Spend the target every year, raised with inflation, whatever markets do (the '4% rule' style)."},
            {"key": "guardrails", "label": "Guardrails",
             "description": "Guyton-Klinger: skip the inflation raise after a losing year; cut 10% when the withdrawal rate drifts 20% above where it started, raise 10% when 20% below."},
            {"key": "vpw", "label": "Variable (VPW)",
             "description": "Bogleheads variable percentage withdrawal: each year spend the payment that would empty the portfolio by the plan-to age at the expected real return."},
        ],
        "spending_profiles": [
            {"key": "flat", "label": "Flat", "description": "Real living spending stays level through retirement."},
            {"key": "smile", "label": "Smile",
             "description": "Blanchett's retirement spending smile: real living spending falls about 1% a year, about 2% in the mid-70s, then about 1% again; health care rises on its own."},
        ],
        "event_templates": EVENT_TEMPLATES,
        "layoff_defaults": rs.LAYOFF_DEFAULTS,
        "assumptions": ASSUMPTIONS,
    }


# Offsets are relative to the plan's retirement age (r) or current age (c); the page fills real ages.
EVENT_TEMPLATES: list[dict] = [
    {"kind": "acquisition", "label": "Employer acquired", "start": "c", "start_offset": 1, "amount": 0, "pct": 0.2,
     "amount_label": "New equity a year after close (today's $)", "pct_label": "Deal price vs today's",
     "help": "At close vested shares are bought for cash at the deal price; unvested grants turn into cash at the deal price and still pay on their vest dates. After close, equity is replaced by the amount you enter (0 for none)."},
    {"kind": "layoff", "label": "Layoff, back to work", "start": "c", "start_offset": 1, "amount": 0, "pct": 0,
     "params": {"severance_weeks": 8, "gap_months": 6, "next_pay_pct": 1.0, "next_equity": 1},
     "help": "Severance, unemployment benefit (up to 26 weeks), all unvested grants accelerate and pay now; no pay during the gap, COBRA or marketplace cover; then a new job at a share of today's pay."},
    {"kind": "layoff", "label": "Layoff, long gap and lower pay", "start": "c", "start_offset": 1, "amount": 0, "pct": 0,
     "params": {"severance_weeks": 8, "gap_months": 18, "next_pay_pct": 0.7, "next_equity": 0},
     "help": "The 'AI takes my job' middle case: a year and a half out of work, then 70% of today's pay with no equity."},
    {"kind": "layoff", "label": "Layoff, never re-employed", "start": "c", "start_offset": 1, "amount": 0, "pct": 0,
     "params": {"severance_weeks": 8, "never_reemployed": 1, "part_time_income": 0},
     "help": "No next job: the plan retires at the layoff. Add part-time income to see what keeps it solvent; the outcome shows the minimum."},
    {"kind": "part_time", "label": "Part-time bridge years", "start": "r", "start_offset": 0, "end": "r", "end_offset": 4,
     "amount": 40000, "pct": 0, "amount_label": "Income a year (today's $, before tax)",
     "help": "Consulting or part-time work after leaving the main job."},
    {"kind": "job_loss", "label": "Job loss (simple)", "start": "c", "start_offset": 5, "end": "c", "end_offset": 5,
     "amount": 0, "pct": 1.0, "pct_label": "Share of pay lost",
     "help": "No salary, RSUs or 401(k) for those years; living costs come out of savings. Use Layoff for severance, benefits and acceleration."},
    {"kind": "rsu_shock", "label": "Company stock crash", "start": "c", "start_offset": 1, "amount": 0, "pct": -0.5,
     "pct_label": "Price change", "help": "The share price falls (or rises) once: held shares and unvested grants move with it."},
    {"kind": "rsu_shock", "label": "Company stock boom", "start": "c", "start_offset": 1, "amount": 0, "pct": 1.0,
     "pct_label": "Price change", "help": "The share price doubles once."},
    {"kind": "one_off_expense", "label": "Big purchase", "start": "c", "start_offset": 3, "amount": 60000, "pct": 0,
     "amount_label": "Cost (today's $)", "help": "A car, a renovation, a wedding."},
    {"kind": "recurring_expense", "label": "Child costs", "start": "c", "start_offset": 2, "end": "c", "end_offset": 19,
     "amount": 18000, "pct": 0, "amount_label": "Cost a year", "help": "Childcare and everyday costs for one child."},
    {"kind": "recurring_expense", "label": "College", "start": "c", "start_offset": 20, "end": "c", "end_offset": 23,
     "amount": 35000, "pct": 0, "amount_label": "Cost a year", "help": "Four years of college for one child."},
    {"kind": "recurring_expense", "label": "Long-term care", "start": "fixed", "start_offset": 0, "start_value": 85, "end": "fixed", "end_value": 87,
     "amount": 70800, "pct": 0, "amount_label": "Cost a year (today's $)",
     "help": "Three years of assisted living from 85 (Genworth/CareScout 2024 national median $70,800 a year; a private nursing-home room was $127,750)."},
    {"kind": "spending_change", "label": "Relocate (lower cost of living)", "start": "r", "start_offset": 0,
     "amount": 25000, "pct": -0.15, "amount_label": "One-off moving cost", "pct_label": "Change in spending",
     "help": "Spending changes from that age on; the moving cost is paid once."},
    {"kind": "downsize", "label": "Downsize the house", "start": "r", "start_offset": 5, "amount": 350000, "pct": 0,
     "amount_label": "Price of the next home (today's $)",
     "help": "Sell (6% costs), pay off the mortgage, buy the next home for cash; the rest goes to savings. Property tax and insurance scale with the cheaper home."},
    {"kind": "windfall", "label": "Inheritance or windfall", "start": "c", "start_offset": 25, "amount": 100000, "pct": 0,
     "amount_label": "Amount (today's $)", "help": "A one-off amount added to savings."},
]
