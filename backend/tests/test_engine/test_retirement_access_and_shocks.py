"""Planning v2 engine: account access (rule of 55, 59½, Roth basis, 72(t)), health cover, housing,
Social Security timing and shortfall, spending smile, acquisition, layoff, sprint and safe withdrawal rates.

Households are generic round-number test shapes, never real figures.
"""
from dataclasses import replace

import numpy as np
import pytest

from app.engine import retirement_sim as rs


def _retiree(age: int, **kw) -> rs.Household:
    base = dict(start_year=2026, current_age=age, cash=0, taxable=0, company_stock=0, retirement=0,
                home_value=0, mortgage_balance=0, mortgage_payment_monthly=0, salary=0, rsu_income=0,
                scheduled_vests={})
    base.update(kw)
    return rs.Household(**base)


def _worker(**kw) -> rs.Household:
    base = dict(start_year=2026, current_age=30, cash=40_000, taxable=45_000, company_stock=20_000,
                retirement=185_000, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0,
                salary=145_000, rsu_income=65_000, scheduled_vests={0: 40_000, 1: 30_000, 2: 10_000},
                spending_last_12m=60_000)
    base.update(kw)
    return rs.Household(**base)


def _p(**kw) -> rs.PlanInputs:
    return rs.PlanInputs(**{"medicare_cost": 0.0, "aca_benchmark": 0.0, "inflation": 0.0, "health_excess_inflation": 0.0,
                            "total_comp_growth": 0.0, "rsu_pct_annual_increase": 0.0, **kw})


def _flat(T: int, n: int = 1) -> rs.Market:
    z = np.zeros((n, T))
    return rs.Market(z.copy(), z.copy(), z.copy(), z.copy(), z.copy())


def _run(p: rs.PlanInputs, hh: rs.Household) -> rs.SimResult:
    return rs.run(p, hh, _flat(p.plan_to_age - hh.current_age + 1))


# --- access to money --------------------------------------------------------------------------

def test_full_retirement_age_and_claiming_factors():
    assert rs.full_retirement_age(1950) == 66
    assert rs.full_retirement_age(1959) == pytest.approx(66 + 10 / 12)
    assert rs.full_retirement_age(1996) == 67
    assert rs.ss_factor(62, 67) == pytest.approx(0.70)
    assert rs.ss_factor(70, 67) == pytest.approx(1.24)
    assert rs.ss_factor(62, 66) == pytest.approx(0.75)


def test_rule_of_55_opens_the_401k_without_penalty():
    hh = _retiree(55, retirement=500_000)
    res = _run(_p(retirement_age=55, plan_to_age=58, retirement_spending=40_000, retirement_tax_rate=0.2), hh)
    assert res.detail["src_401k_penalty"].sum() == 0
    assert res.detail["src_401k"][0] == pytest.approx(40_000)
    assert res.detail["retirement"][0] == pytest.approx(500_000 - 50_000)


def test_before_55_the_bridge_is_taxable_then_roth_basis_then_penalty():
    hh = _retiree(50, taxable=10_000, retirement=500_000, roth_basis=20_000)
    res = _run(_p(retirement_age=50, plan_to_age=52, retirement_spending=40_000, retirement_tax_rate=0.2), hh)
    d = res.detail
    taxable_net = 10_000 * (1 - rs.TAXABLE_WITHDRAWAL_TAX)      # only the gain share is taxed
    assert d["src_taxable"][0] == pytest.approx(taxable_net)
    assert d["src_roth_basis"][0] == pytest.approx(20_000)     # tax- and penalty-free
    rest = 40_000 - taxable_net - 20_000
    assert d["src_401k_penalty"][0] == pytest.approx(rest)     # the rest, at 20% + 10%
    assert d["retirement"][0] == pytest.approx(500_000 - 20_000 - rest / 0.7)


def test_72t_payments_avoid_the_penalty_up_to_the_sepp_amount():
    hh = _retiree(50, retirement=500_000)
    p = _p(retirement_age=50, plan_to_age=52, retirement_spending=40_000, retirement_tax_rate=0.2, use_sepp=True)
    res = _run(p, hh)
    le = rs.sepp_life_expectancy(50)
    sepp = 500_000 * 0.05 / (1 - 1.05 ** (-le))
    assert res.detail["src_401k"][0] == pytest.approx(sepp * 0.8)
    assert res.detail["src_401k_penalty"][0] == pytest.approx(40_000 - sepp * 0.8)


# --- health cover -------------------------------------------------------------------------------

def test_marketplace_premium_is_capped_by_income_below_the_cliff_and_medicare_from_65():
    hh = _retiree(62, retirement=3_000_000)
    p = rs.PlanInputs(retirement_age=62, plan_to_age=66, retirement_spending=30_000, retirement_tax_rate=0.0,
                      inflation=0.0, health_excess_inflation=0.0, aca_benchmark=15_000, aca_income_cap=0.0996,
                      medicare_cost=8_500)
    res = _run(p, hh)
    h = res.detail["healthcare"]
    assert h[0] == pytest.approx(15_000)                        # first retired year: full benchmark
    magi = res.detail["magi"][0]                                # all from the pre-tax 401(k)
    assert magi == pytest.approx(30_000 + 15_000)
    assert h[1] == pytest.approx(0.0996 * magi)                 # below 400% FPL: capped
    assert h[3] == pytest.approx(8_500) and h[4] == pytest.approx(8_500)   # 65, 66: Medicare

    rich = _run(replace(p, retirement_spending=200_000), _retiree(62, retirement=9_000_000))
    assert rich.detail["healthcare"][1] == pytest.approx(15_000)          # above the cliff: no subsidy


# --- housing ------------------------------------------------------------------------------------

def test_escrow_continues_after_payoff_and_payoff_at_retirement_is_a_lump():
    hh = _retiree(60, taxable=1_000_000, mortgage_balance=20_000, mortgage_rate=0.04,
                  mortgage_payment_monthly=1_500, escrow_monthly=500, home_value=400_000)
    p = _p(retirement_age=60, plan_to_age=65, retirement_spending=0, retirement_tax_rate=0.0)
    res = _run(p, hh)
    assert res.detail["housing"][0] > 6_000                     # P&I plus escrow
    assert res.detail["housing"][4] == pytest.approx(6_000)     # paid off: escrow only
    lump = _run(replace(p, payoff_mortgage=True), hh)
    assert lump.detail["mortgage_payoff"][0] == pytest.approx(20_000)
    assert lump.detail["housing"][0] == pytest.approx(6_000)


# --- Social Security ----------------------------------------------------------------------------

def test_social_security_from_claim_age_and_trust_fund_shortfall_from_2034():
    hh = _retiree(66, retirement=2_000_000)
    p = _p(retirement_age=66, plan_to_age=75, retirement_spending=50_000, ss_monthly_at_fra=2_000, ss_claim_age=67,
           ss_payable_share=0.81)
    res = _run(p, hh)
    ss = res.detail["social_security"]
    years = res.years
    assert ss[0] == 0                                             # 66: not yet claimed
    assert ss[1] == pytest.approx(24_000)                         # 2027 at 67: full benefit
    assert ss[years.index(2034)] == pytest.approx(24_000 * 0.81)  # trust fund shortfall


# --- spending shape -----------------------------------------------------------------------------

def test_spending_smile_falls_in_real_terms_and_flat_does_not():
    hh = _retiree(65, retirement=5_000_000)
    smile = _run(_p(retirement_age=65, plan_to_age=85, retirement_spending=100_000, spending_profile="smile"), hh)
    flat = _run(_p(retirement_age=65, plan_to_age=85, retirement_spending=100_000), hh)
    assert flat.spending_real[0, 10] == pytest.approx(100_000)
    assert smile.spending_real[0, 0] == pytest.approx(100_000)
    assert smile.spending_real[0, 1] == pytest.approx(100_000 * (1 + rs.smile_change(65)))
    assert 80_000 < smile.spending_real[0, 10] < 90_000           # about -1.5% a year through 65-75
    assert smile.success[0]


# --- career shocks ------------------------------------------------------------------------------

def test_acquisition_cashes_out_vested_shares_and_pays_unvested_at_the_deal_price_on_schedule():
    hh = _worker()
    p = _p(retirement_age=45, events=[rs.LifeEvent("acquisition", 31, pct=0.25, amount=10_000)])
    res = _run(p, hh)
    base = _run(_p(retirement_age=45), hh)
    assert res.detail["equity_payout"][1] == pytest.approx(base.detail["company_stock"][0] * 1.25)
    assert res.detail["company_stock"][1] == pytest.approx(0)
    assert res.detail["rsu_income"][2] == pytest.approx(10_000 + 10_000 * 1.25)  # replacement + converted vest
    assert res.detail["rsu_income"][5] == pytest.approx(10_000)                  # only the replacement equity


def test_layoff_pays_severance_and_benefit_accelerates_vesting_then_a_gap_and_lower_pay():
    hh = _worker()
    params = {"severance_weeks": 26, "gap_months": 6, "ui_weekly": 1_000, "gap_health_annual": 10_000,
              "next_pay_pct": 0.5, "next_equity": 0}
    p = _p(retirement_age=45, income_tax_rate=0.0, rsu_tax_rate=0.0, events=[rs.LifeEvent("layoff", 31, params=params)])
    res = _run(p, hh)
    d = res.detail
    assert d["equity_payout"][1] == pytest.approx(30_000 + 10_000)   # every unvested grant pays at the layoff
    assert d["salary"][1] == pytest.approx(145_000 * 0.5 * 0.5)      # half a year worked, at half the pay
    assert d["rsu_income"][1] == 0 and d["rsu_income"][5] == 0       # the next job grants no equity
    assert d["salary"][3] == pytest.approx(145_000 * 0.5)
    assert d["gap_costs"][1] == pytest.approx(10_000 * 0.5)          # six months of COBRA/marketplace


def test_layoff_with_no_next_job_retires_at_the_layoff_and_income_keeps_it_solvent():
    hh = _worker()
    never = rs.LifeEvent("layoff", 40, params={"never_reemployed": 1})
    p = rs.PlanInputs(retirement_age=55, retirement_spending=60_000, events=[never])
    line = rs.run(p, hh, rs.expected_market(p, hh))
    assert line.detail["salary"][10] == 0 and line.detail["spending"][10] > 0   # retired at 40
    z = rs.min_income_plan_line_solvent(p, hh, 40, 54)
    if not line.success[0]:
        assert z and z > 0
        fixed = rs._with_income(p, 40, 54, z)
        assert rs.run(fixed, hh, rs.expected_market(fixed, hh)).success[0]
        short = rs._with_income(p, 40, 54, max(0.0, z - 2_000))
        assert not rs.run(short, hh, rs.expected_market(short, hh)).success[0]


# --- sprint and safe withdrawal rates -----------------------------------------------------------

def test_sprint_grid_spending_rises_with_retirement_age_and_returns():
    hh = _worker()
    p = rs.sprint_inputs(rs.PlanInputs(retirement_age=55, retirement_spending=60_000))
    assert p.employee_401k_rate == 1.0 and p.rsu_hold_fraction == 0.0
    grid = rs.sprint_grid(p, hh, 0.85, [45, 50, 55], [-0.01, 0.0, 0.01], n_paths=200)
    for row in grid:
        vals = [v or 0 for v in row["max_spending"]]
        assert vals == sorted(vals)
    assert [(r["max_spending"][1] or 0) for r in grid] == sorted((r["max_spending"][1] or 0) for r in grid)
    first = grid[-1]["max_spending"][1] or 0
    assert rs.earliest_age_for(grid, 1, first) <= 55
    assert rs.earliest_age_for(grid, 1, 10_000_000) is None


def test_historical_safe_withdrawal_rates_match_the_published_record():
    # Early Retirement Now's fail-safe rates for a 75/25 portfolio: 3.82 / 3.58 / 3.35 / 3.25% (30-60 years).
    published = {30: 0.0382, 40: 0.0358, 50: 0.0335, 60: 0.0325}
    for horizon, rate in published.items():
        ours = rs.historical_withdrawal_rates(0.75, horizon)
        assert ours["worst"] == pytest.approx(rate, abs=0.0015), horizon
    assert rs.historical_withdrawal_rates(0.6, 30)["worst_start"] == 1966
    assert rs.historical_withdrawal_rates(0.6, 200) is None



# --- taxes by account type -----------------------------------------------------------------------

def test_roth_money_comes_out_tax_free_and_pretax_money_is_taxed():
    p = _p(retirement_age=62, plan_to_age=64, retirement_spending=40_000, retirement_tax_rate=0.2)
    pretax = _run(p, _retiree(62, retirement=1_000_000)).detail["retirement"][0]
    roth = _run(p, _retiree(62, retirement=1_000_000, roth_balance=1_000_000)).detail["retirement"][0]
    assert 1_000_000 - pretax == pytest.approx(40_000 / 0.8, rel=0.05)   # grossed up for income tax
    assert 1_000_000 - roth == pytest.approx(40_000, rel=0.05)           # no tax on qualified Roth


def test_new_deferrals_split_between_roth_and_pretax():
    hh = rs.Household(start_year=2026, current_age=40, salary=100_000, roth_contribution_share=0.25)
    p = _p(retirement_age=45, plan_to_age=46, employee_401k_rate=0.10, employer_match_rate=0.0,
           investment_return=0.0, inflation=0.0, total_comp_growth=0.0)
    d = _run(p, hh).detail
    assert d["retirement"][0] == pytest.approx(10_000, rel=0.02)
