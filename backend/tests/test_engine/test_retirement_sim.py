"""Planning v2 engine (app/engine/retirement_sim.py): the maths behind every Planning chart.

Households here are generic test shapes (Claudius-sized round numbers), never real figures.
"""
from dataclasses import replace

import numpy as np
import pytest

from app.engine import retirement_sim as rs


def _household(**kw) -> rs.Household:
    base = dict(start_year=2026, current_age=30, cash=40_000, taxable=45_000, company_stock=20_000,
                retirement=185_000, home_value=520_000, mortgage_balance=362_000, mortgage_rate=0.0425,
                mortgage_payment_monthly=1_870, salary=145_000, rsu_income=65_000,
                scheduled_vests={0: 40_000, 1: 30_000, 2: 10_000}, spending_last_12m=60_000)
    base.update(kw)
    return rs.Household(**base)


def _p(**kw) -> rs.PlanInputs:
    """Plan inputs with retirement health costs off, so cash-flow arithmetic stays checkable by hand."""
    return rs.PlanInputs(**{"medicare_cost": 0.0, "aca_benchmark": 0.0, **kw})


def _flat_market(T: int, n: int = 1, ret: float = 0.0, infl: float = 0.0) -> rs.Market:
    full = np.full((n, T), ret)
    return rs.Market(full.copy(), full.copy(), full.copy(), np.full((n, T), ret), np.full((n, T), infl))


def test_social_security_claim_age_factors():
    assert rs.ss_factor(67) == pytest.approx(1.0)
    assert rs.ss_factor(62) == pytest.approx(0.70)
    assert rs.ss_factor(64) == pytest.approx(0.80)
    assert rs.ss_factor(70) == pytest.approx(1.24)
    assert rs.ss_factor(75) == pytest.approx(1.24)  # no credit after 70


def test_retired_fixed_spending_draws_target_grossed_up_for_tax():
    hh = _household(current_age=65, cash=0, taxable=1_000_000, company_stock=0, retirement=0, home_value=0,
                    mortgage_balance=0, mortgage_payment_monthly=0, salary=0, rsu_income=0, scheduled_vests={})
    p = _p(retirement_age=65, plan_to_age=67, retirement_spending=40_000, retirement_tax_rate=0.20)
    res = rs.run(p, hh, _flat_market(3))
    # Zero returns and inflation: each year removes 40,000 / 0.8 = 50,000.
    assert res.liquid_real[0].tolist() == pytest.approx([950_000, 900_000, 850_000])
    assert res.success.all()


def test_running_out_is_a_failure_at_that_age():
    hh = _household(current_age=65, cash=0, taxable=120_000, company_stock=0, retirement=0, home_value=0,
                    mortgage_balance=0, mortgage_payment_monthly=0, salary=0, rsu_income=0, scheduled_vests={})
    p = _p(retirement_age=65, plan_to_age=70, retirement_spending=40_000, retirement_tax_rate=0.20)
    res = rs.run(p, hh, _flat_market(6))
    assert not res.success[0]
    assert res.depleted_age[0] == 67  # 120k covers 50k + 50k, the third year is short
    assert res.liquid_real[0, -1] == 0


def test_rsu_income_continues_after_the_last_scheduled_vest():
    """The October defect: plan rows fell to $0 RSU (and $0 income) after the last known vest."""
    hh = _household()
    p = _p(retirement_age=45, inflation=0.0, total_comp_growth=0.0, rsu_pct_annual_increase=0.0)
    res = rs.run(p, hh, _flat_market(p.plan_to_age - hh.current_age + 1))
    rsu = res.detail["rsu_income"]
    salary = res.detail["salary"]
    assert rsu[0] == pytest.approx(40_000)                      # only the scheduled vests this year
    for t in range(3, 15):                                       # schedule over, refresh grants fully in
        assert rsu[t] == pytest.approx(65_000)
        assert salary[t] == pytest.approx(145_000)
    assert rsu[15] == 0 and salary[15] == 0                      # retired at 45


def test_salary_only_household_has_no_invented_rsu():
    hh = _household(rsu_income=0, scheduled_vests={})
    p = _p(retirement_age=40, inflation=0.0, total_comp_growth=0.0)
    res = rs.run(p, hh, _flat_market(p.plan_to_age - hh.current_age + 1))
    assert res.detail["rsu_income"][:10].sum() == 0
    assert res.detail["salary"][5] == pytest.approx(145_000)


def test_monte_carlo_is_reproducible_and_moves_the_right_way():
    hh = _household()
    p = _p(retirement_age=55)
    a = rs.success_rate(p, hh, 300)
    assert a == rs.success_rate(p, hh, 300)  # same seed, same answer
    assert rs.success_rate(replace(p, retirement_spending=60_000), hh, 300) > a
    assert rs.success_rate(replace(p, retirement_spending=160_000), hh, 300) < a
    assert rs.success_rate(replace(p, retirement_age=62), hh, 300) > a
    assert rs.success_rate(replace(p, retirement_return=0.08), hh, 300) > a


def test_plan_line_sits_near_the_monte_carlo_median():
    hh = _household()
    p = _p(retirement_age=55)
    mc = rs.run(p, hh, rs.simulate_market(p, hh, 1000, rs.DEFAULT_SEED))
    line = rs.run(p, hh, rs.expected_market(p, hh))
    i = mc.retirement_index - 1
    median = float(np.median(mc.liquid_real[:, i]))
    assert line.liquid_real[0, i] == pytest.approx(median, rel=0.15)


def test_historical_cohorts_are_complete_sequences_and_1966_is_hard():
    hh = _household(current_age=65, salary=0, rsu_income=0, scheduled_vests={}, cash=0, company_stock=0,
                    taxable=500_000, retirement=500_000, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0)
    p = _p(retirement_age=65, plan_to_age=94, retirement_spending=48_000, retirement_tax_rate=0.0,
                      stock_allocation_retired=0.6)
    starts, market = rs.historical_cohort_markets(p, hh)
    assert starts[0] == 1928 and starts[-1] == rs.HISTORY_YEARS[-1] - 29  # 30-year retirements only
    res = rs.run(p, hh, market)
    by_year = dict(zip(starts, res.success))
    assert by_year[1982]           # a 4.8% start in 1982 survives
    assert not by_year[1966]       # ... and fails in 1966 (stagflation)
    # The replayed inflation is the CPI's: 1974 was 12.3%.
    assert market.inflation[starts.index(1966), 8] == pytest.approx(0.1234)


def test_stagflation_regime_replays_history_from_retirement():
    hh = _household()
    p = _p(retirement_age=55)
    m = rs.simulate_market(p, hh, 50, rs.DEFAULT_SEED, rs.REGIME_BY_KEY["stagflation"])
    t = 55 - 30
    assert np.allclose(m.inflation[:, t], rs.history_row(1966)[3])
    s, b, _, _ = rs.history_row(1974)
    assert np.allclose(m.portfolio_retired[:, t + 8], 0.6 * s + 0.4 * b)
    base = rs.success_rate(p, hh, 300)
    assert rs.success_rate(p, hh, 300, regime=rs.REGIME_BY_KEY["stagflation"]) < base
    assert rs.success_rate(p, hh, 300, regime=rs.REGIME_BY_KEY["strong_start"]) > base


def test_guardrails_cut_ten_percent_after_a_crash():
    hh = _household(current_age=60, salary=0, rsu_income=0, scheduled_vests={}, cash=0, company_stock=0,
                    taxable=1_000_000, retirement=0, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0)
    p = _p(retirement_age=60, plan_to_age=95, retirement_spending=50_000, retirement_tax_rate=0.0,
                      spending_rule="guardrails", spending_floor=0.0)
    m = _flat_market(36)
    m.portfolio_retired[0, 0] = -0.40  # crash in the first year
    res = rs.run(p, hh, m)
    # Year 0 spends 50k (5% of 1M). After the crash the portfolio is 570k: 50k is 8.8% > 6% -> cut to 45k.
    assert res.spending_real[0, 0] == pytest.approx(50_000)
    assert res.spending_real[0, 1] == pytest.approx(45_000)
    assert res.cut_count[0] >= 1


def test_guardrails_do_not_cut_a_withdrawal_rate_the_portfolio_can_sustain():
    """The sustainability gate: a 1% withdrawal rate is not cut after a 20% fall."""
    hh = _household(current_age=60, salary=0, rsu_income=0, scheduled_vests={}, cash=0, company_stock=0,
                    taxable=5_000_000, retirement=0, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0)
    p = _p(retirement_age=60, plan_to_age=95, retirement_spending=50_000, retirement_tax_rate=0.0,
                      spending_rule="guardrails", spending_floor=0.0)
    m = _flat_market(36)
    m.portfolio_retired[0, 0] = -0.40
    res = rs.run(p, hh, m)
    assert res.spending_real[0, 1] == pytest.approx(50_000)
    assert res.cut_count[0] == 0


def test_a_crash_in_the_first_retired_year_is_sequence_risk():
    hh = _household()
    p = _p(retirement_age=55)
    crash = rs.REGIME_BY_KEY["crash_at_retirement"]
    m = rs.simulate_market(p, hh, 50, rs.DEFAULT_SEED, crash)
    t = 55 - 30
    assert np.allclose(m.portfolio_retired[:, t], 0.6 * -0.35 + 0.4 * rs._BOND_MEAN)
    assert rs.success_rate(p, hh, 300, regime=crash) < rs.success_rate(p, hh, 300)


def test_vpw_spends_the_payment_that_empties_the_portfolio_at_the_end():
    hh = _household(current_age=90, salary=0, rsu_income=0, scheduled_vests={}, cash=0, company_stock=0,
                    taxable=100_000, retirement=0, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0)
    p = _p(retirement_age=90, plan_to_age=94, retirement_tax_rate=0.0, inflation=0.0, retirement_return=0.0,
                      spending_rule="vpw", spending_floor=0.0, retirement_spending=20_000)
    res = rs.run(p, hh, _flat_market(5))
    assert res.spending_real[0].tolist() == pytest.approx([20_000] * 5)  # 1/5, 1/4, ... of what is left
    assert res.liquid_real[0, -1] == pytest.approx(0, abs=1e-6)


def test_401k_before_60_only_after_taxable_and_with_penalty():
    hh = _household(current_age=50, salary=0, rsu_income=0, scheduled_vests={}, cash=0, company_stock=0,
                    taxable=10_000, retirement=500_000, home_value=0, mortgage_balance=0, mortgage_payment_monthly=0)
    p = _p(retirement_age=50, plan_to_age=51, retirement_spending=30_000, retirement_tax_rate=0.2)
    res = rs.run(p, hh, _flat_market(2))
    # 30k net = 37.5k gross; 10k from taxable at 20%, then (37.5k - 10k) * 0.8 = 22k net left -> 22k / 0.7 from 401(k).
    assert res.detail["retirement"][0] == pytest.approx(500_000 - 22_000 / 0.7)


def test_life_events_change_the_path_as_described():
    T = 66
    hh = _household(company_stock=100_000)
    p = _p(retirement_age=55, inflation=0.0, total_comp_growth=0.0)
    base = rs.run(p, hh, _flat_market(T))

    job_loss = rs.run(replace(p, events=[rs.LifeEvent("job_loss", 35, 35, pct=1.0)]), hh, _flat_market(T))
    assert job_loss.detail["salary"][5] == 0 and base.detail["salary"][5] > 0
    assert job_loss.liquid_real[0, 6] < base.liquid_real[0, 6]

    crash = rs.run(replace(p, events=[rs.LifeEvent("rsu_shock", 31, pct=-0.5)]), hh, _flat_market(T))
    assert crash.detail["company_stock"][1] < base.detail["company_stock"][1]

    health = rs.run(replace(p, events=[rs.LifeEvent("healthcare", 0, 64, amount=15_000)]), hh, _flat_market(T))
    w_base, w_h = base.detail["withdrawal"], health.detail["withdrawal"]
    assert w_h[25] - w_base[25] == pytest.approx(15_000)   # age 55
    assert w_h[35] == pytest.approx(w_base[35])            # age 65: Medicare

    down = rs.run(replace(p, events=[rs.LifeEvent("downsize", 60, amount=300_000)]), hh, _flat_market(T))
    assert down.detail["home_equity"][30] == pytest.approx(300_000 * 1.03)  # bought at the start of the year, mortgage gone


def test_goal_seek_answers_are_consistent_with_the_success_rate():
    hh = _household()
    p = _p(retirement_age=55)
    g = rs.goal_seek(p, hh, 0.85, n_paths=300)
    assert g.max_spending is not None
    assert rs.success_rate(replace(p, retirement_spending=g.max_spending), hh, 300) >= 0.84
    assert rs.success_rate(replace(p, retirement_spending=g.max_spending * 1.15), hh, 300) < 0.85
    if g.earliest_retirement_age is not None:
        assert rs.success_rate(replace(p, retirement_age=g.earliest_retirement_age), hh, 300) >= 0.85
    rates = [row["success"] for row in g.by_spending]
    assert rates == sorted(rates, reverse=True)
    if g.extra_monthly_savings:
        boosted = replace(p, monthly_cash_savings=p.monthly_cash_savings + g.extra_monthly_savings)
        assert rs.success_rate(boosted, hh, 300) >= 0.85
