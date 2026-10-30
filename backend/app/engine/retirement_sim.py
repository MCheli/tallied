"""
Retirement outlook engine: Monte Carlo, historical replay and goal-seek for one household.

Pure computation (numpy only). The service layer builds a ``Household`` from the database and a
``PlanInputs`` from the plan's assumptions; everything here is deterministic for a given seed, so
two runs that differ in one lever differ only because of that lever (common random numbers).

Time runs in 12-month periods starting today: period t covers [today + t years, today + t + 1 years),
the household is ``current_age + t`` during it and its label is ``start_year + t``. All money inside
the simulation is nominal; results are reported in today's dollars by dividing by each path's own
price index.

One period, working years (age < retirement_age):
  total comp     = (salary0 + rsu0) x price index x (1 + real raise)^t, real raise = comp growth - inflation
  RSU share      = starts at today's split, moves by rsu_pct_annual_increase, capped at rsu_pct_cap
  RSU income     = scheduled vests (at today's price x company price index) + refresh grants, which
                   ramp in over VEST_YEARS so income does not fall to zero after the last known vest
  401(k)         = min(salary x employee rate, IRS limit x price index) + salary x employer match
  saved          = monthly_cash_savings x 12, scaled with salary, plus after-tax RSU not held as stock
  balances grow at the period's return, then the period's contributions are added

One period, retired years:
  need           = living spending (spending rule) + events + mortgage payment while it lasts
                   - Social Security from the claim age - part-time income after tax
  withdrawals    = need grossed up by retirement_tax_rate, taken cash -> taxable -> company stock ->
                   401(k); the 401(k) is used before 60 only when the rest is gone, with a 10% penalty
  balances lose the withdrawal at the start of the period, then grow

A path fails in the first period it cannot fund its need (it "runs out"), or, under a variable
spending rule, in the first period real spending falls below spending_floor x the target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from app.engine.history_data import HISTORY

VEST_YEARS = 3                # refresh grants reach full value after this many years of vesting
COMPANY_STOCK_VOL = 0.30      # single-stock volatility (annual)
COMPANY_MARKET_CORR = 0.6     # correlation between the company stock and the market
INFLATION_PERSISTENCE = 0.6   # AR(1) coefficient of annual inflation
INFLATION_SHOCK_VOL = 0.015   # sd of the annual inflation shock
EARLY_WITHDRAWAL_PENALTY = 0.10
PENALTY_FREE_AGE = 60         # 59 1/2, rounded to the period the household turns 60
RULE_OF_55_AGE = 55           # leave the employer in/after the year you turn 55: that 401(k) is penalty-free
MEDICARE_AGE = 65
HOME_SELLING_COST = 0.06
DEFAULT_SEED = 20261029
SS_SHORTFALL_YEAR = 2034      # 2025 Trustees Report: combined OASDI reserves depleted in 2034, ~81% payable after
SEPP_RATE = 0.05              # IRS Notice 2022-6: up to the greater of 5% or 120% of the federal mid-term rate
ACA_SUBSIDY_CLIFF_FPL = 4.0   # premium tax credit ends above 400% of the poverty line (enhanced credits expired 2025)
TAXABLE_GAIN_SHARE = 0.5      # share of a taxable-account withdrawal that is realised gain (counts towards MAGI)
CAPITAL_GAINS_RATE = 0.15     # long-term gains: federal 15% bracket (Massachusetts adds 5%; 0% federal at low income)
TAXABLE_WITHDRAWAL_TAX = TAXABLE_GAIN_SHARE * CAPITAL_GAINS_RATE   # only the gain is taxed, not the cost basis

SPENDING_RULES = ("fixed", "guardrails", "vpw")
SPENDING_PROFILES = ("flat", "smile")

# ---------------------------------------------------------------------------
# Historical statistics (used for volatility and the historical backtest)
# ---------------------------------------------------------------------------
_H = np.array([r[1:] for r in HISTORY], dtype=float)  # stocks, bonds, bills, inflation
HISTORY_YEARS: list[int] = [r[0] for r in HISTORY]
_STOCK_SD = float(np.std(_H[:, 0], ddof=1))
_BOND_SD = float(np.std(_H[:, 1], ddof=1))
_BOND_MEAN = float(np.mean(_H[:, 1]))
_STOCK_BOND_CORR = float(np.corrcoef(_H[:, 0], _H[:, 1])[0, 1])


def portfolio_volatility(stock_share: float) -> float:
    """Annual volatility of a stock/bond mix from the 1928-onward record."""
    w = min(1.0, max(0.0, stock_share))
    var = (w * _STOCK_SD) ** 2 + ((1 - w) * _BOND_SD) ** 2 + 2 * w * (1 - w) * _STOCK_BOND_CORR * _STOCK_SD * _BOND_SD
    return math.sqrt(max(var, 0.0))


def history_row(year: int) -> tuple[float, float, float, float]:
    i = HISTORY_YEARS.index(year)
    s, b, bill, inf = _H[i]
    return float(s), float(b), float(bill), float(inf)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass
class Household:
    """Where the household stands today. Built from the database by the planning service."""
    start_year: int
    current_age: int
    cash: float = 0.0
    taxable: float = 0.0
    company_stock: float = 0.0
    retirement: float = 0.0
    home_value: float = 0.0
    mortgage_balance: float = 0.0
    mortgage_rate: float = 0.0
    mortgage_payment_monthly: float = 0.0
    salary: float = 0.0
    rsu_income: float = 0.0
    scheduled_vests: dict[int, float] = field(default_factory=dict)  # period -> value at today's price
    spending_last_12m: float = 0.0
    # Cash flow while working (today's $ a year). When living_spending is set, savings from pay are
    # take-home salary minus living spending, housing and other debt payments (it can be negative:
    # equity then pays for part of life); monthly_cash_savings is extra saved on top by spending less.
    living_spending: float = 0.0       # excludes housing, health cover paid from pay, and debt payments
    other_debt_payments: float = 0.0   # loans other than the mortgage (student loan, HEAT loan, ...)
    # Covered earnings by year from the Social Security statement: the benefit is reduced for the years
    # not worked when retiring before the claim age (the statement assumes work until claiming).
    ss_earnings: dict[int, float] = field(default_factory=dict)
    irs_401k_limit: float = 23_500.0
    escrow_monthly: float = 0.0       # part of the mortgage payment that is tax and insurance (continues after payoff)
    roth_basis: float = 0.0           # Roth contributions inside the 401(k): withdrawable tax- and penalty-free
    roth_balance: float = 0.0         # Roth part of `retirement` (contributions + earnings): tax-free after 59 1/2
    roth_contribution_share: float = 0.0  # share of employee 401(k) deferrals that go to Roth (the match is pre-tax)
    full_retirement_age: float = 67.0  # Social Security FRA from the birth year


def full_retirement_age(birth_year: int) -> float:
    """Social Security full retirement age by birth year (SSA): 65 to 1937, rising 2 months a year to 66
    for 1943-54, rising again 2 months a year to 67 for 1960 and later."""
    if birth_year <= 1937:
        return 65.0
    if birth_year <= 1942:
        return 65 + (birth_year - 1937) * 2 / 12
    if birth_year <= 1954:
        return 66.0
    if birth_year <= 1959:
        return 66 + (birth_year - 1954) * 2 / 12
    return 67.0


def smile_change(age: int) -> float:
    """Yearly real change in living spending under the 'smile' profile.

    Approximates Blanchett (2014), "Exploring the Retirement Consumption Puzzle", as summarised by
    Kitces: about -1% a year early in retirement, deepening to about -2% in the mid-70s ("slow-go"),
    easing back to about -1% late. Health care is modelled separately and rises on its own, which is
    what turns the curve up at the end.
    """
    if age < 65:
        return -0.01
    if age < 75:
        return -0.01 - 0.01 * (age - 65) / 10
    if age < 90:
        return -0.02 + 0.01 * (age - 75) / 15
    return -0.01


@dataclass
class LifeEvent:
    kind: str
    start_age: int
    end_age: int | None = None
    amount: float = 0.0       # today's dollars (annual for recurring kinds)
    pct: float = 0.0          # fraction (job loss share, price shock, spending change)
    label: str = ""
    enabled: bool = True
    params: dict = field(default_factory=dict)  # kind-specific settings (layoff, acquisition)


LAYOFF_DEFAULTS = {
    "severance_weeks": 8,        # weeks of salary paid at the layoff
    "gap_months": 6,             # months without pay before the next job
    "ui_weekly": 1105,           # state unemployment benefit a week (MA maximum from Oct 2025), up to 26 weeks
    "gap_health_annual": 9500,   # COBRA (up to 102% of the KFF 2025 single premium, $9,325) or marketplace, a year
    "next_pay_pct": 1.0,         # next job's total pay as a share of today's path
    "next_equity": 1,            # 1: the next job grants equity at today's RSU share; 0: salary only
    "never_reemployed": 0,       # 1: no next job; retire at the layoff (with part-time income below)
    "part_time_income": 0,       # yearly income (today's $) from the layoff to the planned retirement age
}


def layoff_params(e: LifeEvent) -> dict:
    return {**LAYOFF_DEFAULTS, **{k: v for k, v in (e.params or {}).items() if k in LAYOFF_DEFAULTS}}


EVENT_KINDS = (
    "part_time", "job_loss", "layoff", "rsu_shock", "one_off_expense", "recurring_expense",
    "spending_change", "downsize", "healthcare", "windfall", "acquisition",
)


@dataclass
class PlanInputs:
    retirement_age: int = 60
    plan_to_age: int = 95
    total_comp_growth: float = 0.04
    inflation: float = 0.03
    rsu_pct_of_comp: float = 0.37
    rsu_pct_annual_increase: float = 0.005
    rsu_pct_cap: float = 0.50
    rsu_tax_rate: float = 0.40
    rsu_hold_fraction: float = 0.5
    income_tax_rate: float = 0.30
    employee_401k_rate: float = 0.10
    employer_match_rate: float = 0.06
    monthly_cash_savings: float = 440.0
    investment_return: float = 0.07
    retirement_return: float = 0.05
    stock_price_growth: float = 0.07
    home_appreciation: float = 0.03
    stock_allocation_working: float = 0.90
    stock_allocation_retired: float = 0.60
    retirement_spending: float = 100_000.0
    retirement_tax_rate: float = 0.20
    spending_rule: str = "fixed"
    spending_profile: str = "flat"
    spending_floor: float = 0.75
    ss_monthly_at_fra: float = 0.0
    ss_claim_age: int = 67
    ss_payable_share: float = 1.0      # share of scheduled benefits paid from SS_SHORTFALL_YEAR on
    health_people: int = 1             # people the household insures in retirement
    aca_benchmark: float = 15_000.0    # unsubsidised benchmark silver premium per person, today's $
    aca_income_cap: float = 0.0996     # premium capped at this share of MAGI below the subsidy cliff
    medicare_cost: float = 8_500.0     # Medicare B/D, Medigap and out-of-pocket per person per year
    health_excess_inflation: float = 0.02
    projects_allowance: float = 0.0    # yearly irregular projects/hobby budget while working (today's $)
    use_sepp: bool = False             # 72(t) payments from the 401(k) before 59 1/2
    payoff_mortgage: bool = False      # pay the mortgage off from savings in the first retired year
    events: list[LifeEvent] = field(default_factory=list)


@dataclass
class Regime:
    """A macro scenario layered on the Monte Carlo paths.

    replay_from: replay this historical stretch (stocks/bonds by allocation, bills, CPI) ...
    anchor:      ... starting "now" or at "retirement".
    shift_*:     add to expected returns / inflation for ``shift_years`` periods from the anchor.
    """
    key: str
    label: str
    description: str
    anchor: str = "now"
    replay_from: int | None = None
    replay_to: int | None = None
    shift_return: float = 0.0
    shift_inflation: float = 0.0
    shift_years: int = 0
    stock_shock: float | None = None  # one period at the anchor: stocks return this, bonds their average


REGIMES: tuple[Regime, ...] = (
    Regime("base", "Your assumptions", "Returns and inflation drawn around the plan's own assumptions."),
    Regime("strong_start", "Strong market now (1982-1999)",
           "Replays the 1982-1999 bull market from today, then your assumptions.",
           anchor="now", replay_from=1982, replay_to=1999),
    Regime("crash_at_retirement", "Crash in your first year retired",
           "Stocks fall 35% in the year you retire (bonds earn their average), then your assumptions: "
           "sequence-of-returns risk on its own.",
           anchor="retirement", stock_shock=-0.35),
    Regime("lost_decade", "Lost decade at retirement (2000-2009)",
           "Replays 2000-2009 from the year you retire: two crashes and flat stocks for ten years.",
           anchor="retirement", replay_from=2000, replay_to=2009),
    Regime("stagflation", "Stagflation at retirement (1966-1981)",
           "Replays 1966-1981 from the year you retire: high inflation and negative real stock returns, "
           "the worst start date in the US record.",
           anchor="retirement", replay_from=1966, replay_to=1981),
    Regime("depression", "Depression at retirement (1929-1941)",
           "Replays 1929-1941 from the year you retire: stocks fall by more than 80% with deflation.",
           anchor="retirement", replay_from=1929, replay_to=1941),
    Regime("high_inflation", "High inflation for 10 years",
           "Inflation 3 points above your assumption for ten years from today; returns only 1 point higher.",
           anchor="now", shift_inflation=0.03, shift_return=0.01, shift_years=10),
    Regime("low_returns", "Low returns for good",
           "Every expected return (portfolio and company stock) 2 points below your assumptions, forever.",
           anchor="now", shift_return=-0.02, shift_years=200),
)
REGIME_BY_KEY = {r.key: r for r in REGIMES}


# ---------------------------------------------------------------------------
# Market paths
# ---------------------------------------------------------------------------
@dataclass
class Market:
    portfolio_working: np.ndarray   # (n, T) nominal return of the working-years mix
    portfolio_retired: np.ndarray   # (n, T) nominal return of the retired-years mix
    company: np.ndarray             # (n, T) company stock nominal return
    bills: np.ndarray               # (n, T) cash return
    inflation: np.ndarray           # (n, T)


def _lognormal(mean: float, sd: float, z: np.ndarray) -> np.ndarray:
    """Returns with arithmetic mean ``mean`` and sd about ``sd`` from standard normals z."""
    sd = max(sd, 1e-9)
    s2 = math.log(1 + (sd / (1 + mean)) ** 2) if mean > -1 else sd ** 2
    mu = math.log(1 + mean) - s2 / 2
    return np.exp(mu + math.sqrt(s2) * z) - 1


def simulate_market(inputs: PlanInputs, household: Household, n_paths: int, seed: int,
                    regime: Regime | None = None, return_shift: float = 0.0) -> Market:
    T = inputs.plan_to_age - household.current_age + 1
    rng = np.random.default_rng(seed)
    z_market = rng.standard_normal((n_paths, T))
    z_company = rng.standard_normal((n_paths, T))
    z_infl = rng.standard_normal((n_paths, T))

    anchor = 0
    if regime is not None and regime.anchor == "retirement":
        anchor = max(0, inputs.retirement_age - household.current_age)
    shift_ret = np.zeros(T)
    shift_inf = np.zeros(T)
    if regime is not None and regime.shift_years:
        end = min(T, anchor + regime.shift_years)
        shift_ret[anchor:end] = regime.shift_return
        shift_inf[anchor:end] = regime.shift_inflation

    # Inflation: AR(1) around the assumption (plus any regime shift).
    infl = np.empty((n_paths, T))
    prev = np.full(n_paths, inputs.inflation)
    for t in range(T):
        mean_t = inputs.inflation + shift_inf[t]
        prev = mean_t + INFLATION_PERSISTENCE * (prev - mean_t) + INFLATION_SHOCK_VOL * z_infl[:, t]
        infl[:, t] = prev

    sd_w = portfolio_volatility(inputs.stock_allocation_working)
    sd_r = portfolio_volatility(inputs.stock_allocation_retired)
    pw = np.empty((n_paths, T))
    pr = np.empty((n_paths, T))
    co = np.empty((n_paths, T))
    zc = COMPANY_MARKET_CORR * z_market + math.sqrt(1 - COMPANY_MARKET_CORR ** 2) * z_company
    for t in range(T):
        # Returns move with inflation surprises only through the regime shift (documented simplification).
        extra = shift_ret[t] + return_shift
        pw[:, t] = _lognormal(inputs.investment_return + extra, sd_w, z_market[:, t])
        pr[:, t] = _lognormal(inputs.retirement_return + extra, sd_r, z_market[:, t])
        co[:, t] = _lognormal(inputs.stock_price_growth + extra, COMPANY_STOCK_VOL, zc[:, t])
    bills = infl + 0.005

    if regime is not None and regime.replay_from is not None:
        years = list(range(regime.replay_from, (regime.replay_to or regime.replay_from) + 1))
        for k, y in enumerate(years):
            t = anchor + k
            if t >= T or y not in HISTORY_YEARS:
                break
            s, b, bill, inf = history_row(y)
            pw[:, t] = inputs.stock_allocation_working * s + (1 - inputs.stock_allocation_working) * b + return_shift
            pr[:, t] = inputs.stock_allocation_retired * s + (1 - inputs.stock_allocation_retired) * b + return_shift
            # The company stock keeps its own risk on top of the market's historical year.
            co[:, t] = s + COMPANY_STOCK_VOL * math.sqrt(1 - COMPANY_MARKET_CORR ** 2) * z_company[:, t] + return_shift
            bills[:, t] = bill
            infl[:, t] = inf
    if regime is not None and regime.stock_shock is not None and anchor < T:
        s, b = regime.stock_shock, _BOND_MEAN
        pw[:, anchor] = inputs.stock_allocation_working * s + (1 - inputs.stock_allocation_working) * b + return_shift
        pr[:, anchor] = inputs.stock_allocation_retired * s + (1 - inputs.stock_allocation_retired) * b + return_shift
        co[:, anchor] = s + COMPANY_STOCK_VOL * math.sqrt(1 - COMPANY_MARKET_CORR ** 2) * z_company[:, anchor] + return_shift
    return Market(pw, pr, np.maximum(co, -0.95), bills, infl)


def _median_return(mean: float, sd: float) -> float:
    return float(_lognormal(mean, sd, np.zeros(1))[0])


def expected_market(inputs: PlanInputs, household: Household, return_shift: float = 0.0) -> Market:
    """One path at the median of every return distribution: the 'plan line' and the year table.

    Median, not mean: compounding the arithmetic mean overstates the typical outcome (volatility
    drag), so this line sits on the Monte Carlo median instead of above it.
    """
    T = inputs.plan_to_age - household.current_age + 1
    full = lambda v: np.full((1, T), v)  # noqa: E731
    sd_w = portfolio_volatility(inputs.stock_allocation_working)
    sd_r = portfolio_volatility(inputs.stock_allocation_retired)
    return Market(
        full(_median_return(inputs.investment_return + return_shift, sd_w)),
        full(_median_return(inputs.retirement_return + return_shift, sd_r)),
        full(_median_return(inputs.stock_price_growth + return_shift, COMPANY_STOCK_VOL)),
        full(inputs.inflation + 0.005), full(inputs.inflation),
    )


def historical_cohort_markets(inputs: PlanInputs, household: Household) -> tuple[list[int], Market]:
    """Expected returns until retirement, then each complete historical sequence from retirement on.

    One path per historical start year whose sequence covers the whole retirement (FIRECalc-style
    complete cohorts, no wrap-around). Empty when the record is shorter than the retirement.
    """
    T = inputs.plan_to_age - household.current_age + 1
    r0 = max(0, inputs.retirement_age - household.current_age)
    horizon = T - r0
    starts = [y for y in HISTORY_YEARS if y + horizon - 1 <= HISTORY_YEARS[-1]]
    n = len(starts)
    base = expected_market(inputs, household)
    pw = np.repeat(base.portfolio_working, max(n, 1), axis=0)
    pr = np.repeat(base.portfolio_retired, max(n, 1), axis=0)
    co = np.repeat(base.company, max(n, 1), axis=0)
    bills = np.repeat(base.bills, max(n, 1), axis=0)
    infl = np.repeat(base.inflation, max(n, 1), axis=0)
    for i, y0 in enumerate(starts):
        for k in range(horizon):
            s, b, bill, inf = history_row(y0 + k)
            t = r0 + k
            pr[i, t] = inputs.stock_allocation_retired * s + (1 - inputs.stock_allocation_retired) * b
            pw[i, t] = inputs.stock_allocation_working * s + (1 - inputs.stock_allocation_working) * b
            co[i, t] = s
            bills[i, t] = bill
            infl[i, t] = inf
    if n == 0:
        return [], Market(pw[:0], pr[:0], co[:0], bills[:0], infl[:0])
    return starts, Market(pw, pr, co, bills, infl)


# ---------------------------------------------------------------------------
# The year loop
# ---------------------------------------------------------------------------
@dataclass
class SimResult:
    ages: list[int]
    years: list[int]
    retirement_index: int
    success: np.ndarray            # (n,) bool
    depleted_age: np.ndarray       # (n,) float, nan when never
    liquid_real: np.ndarray        # (n, T) end-of-period investable assets, today's $
    net_worth_real: np.ndarray     # (n, T) liquid + home equity, today's $
    spending_real: np.ndarray      # (n, T) living spending in retirement, today's $ (0 while working)
    min_spending_ratio: np.ndarray  # (n,) lowest real spending / target over retirement
    cut_count: np.ndarray          # (n,) number of periods where real spending fell more than 5%
    detail: dict[str, np.ndarray] = field(default_factory=dict)  # per-bucket, path 0, nominal

    @property
    def success_rate(self) -> float:
        return float(self.success.mean()) if self.success.size else 0.0


# Social Security contribution and benefit base (taxable maximum) by year (SSA). It moves with the national
# average wage index, so it serves to index past earnings to today's wage level.
TAXABLE_MAX = {
    1995: 61_200, 1996: 62_700, 1997: 65_400, 1998: 68_400, 1999: 72_600, 2000: 76_200, 2001: 80_400,
    2002: 84_900, 2003: 87_000, 2004: 87_900, 2005: 90_000, 2006: 94_200, 2007: 97_500, 2008: 102_000,
    2009: 106_800, 2010: 106_800, 2011: 106_800, 2012: 110_100, 2013: 113_700, 2014: 117_000, 2015: 118_500,
    2016: 118_500, 2017: 127_200, 2018: 128_400, 2019: 132_900, 2020: 137_700, 2021: 142_800, 2022: 147_000,
    2023: 160_200, 2024: 168_600, 2025: 176_100,
}
PIA_BEND_POINTS_2025 = (1_226, 7_391)   # 90% / 32% / 15% formula, 2025 eligibility year


def _pia(aime: float) -> float:
    b1, b2 = PIA_BEND_POINTS_2025
    return 0.9 * min(aime, b1) + 0.32 * max(0.0, min(aime, b2) - b1) + 0.15 * max(0.0, aime - b2)


def ss_stop_factor(earnings: dict[int, float], stop_year: int, claim_year: int) -> float:
    """Benefit if covered earnings stop before ``stop_year``, relative to the statement's estimate, which
    assumes earnings at the taxable maximum until ``claim_year``.

    Past earnings are capped at that year's maximum and indexed to today's wage level by the ratio of
    taxable maximums; future years at the maximum count as today's maximum. Highest 35 years / 420 months
    give the AIME; the 90/32/15 formula gives the PIA. Returns at most 1.
    """
    if not earnings:
        return 1.0
    latest = max(TAXABLE_MAX)
    top = TAXABLE_MAX[latest]
    last_year = max(earnings)

    def indexed(through: int) -> list[float]:
        vals = []
        for y, e in earnings.items():
            cap = TAXABLE_MAX.get(y)
            if cap is None or y >= through:
                continue
            vals.append(min(float(e), cap) * top / cap)
        vals += [float(top)] * max(0, through - (last_year + 1))
        return sorted(vals, reverse=True)[:35]

    full = _pia(sum(indexed(claim_year)) / 420)
    stop = _pia(sum(indexed(stop_year)) / 420)
    return min(1.0, stop / full) if full > 0 else 1.0


def ss_factor(claim_age: float, fra: float = 67.0) -> float:
    """Social Security benefit at claim_age as a share of the full-retirement-age benefit.

    5/9 % per month for the first 36 months early, 5/12 % per month beyond that; 8% a year of
    delayed credits up to 70 (ssa.gov, "Early or late retirement"). With FRA 67: 70% at 62, 124% at 70.
    """
    claim_age = max(62.0, min(70.0, float(claim_age)))
    if claim_age >= fra:
        return 1 + 0.08 * (claim_age - fra)
    months = round((fra - claim_age) * 12)
    first = min(36, months)
    rest = max(0, months - 36)
    return 1 - first * (5 / 9) / 100 - rest * (5 / 12) / 100


def _vpw_rate(real_return: float, periods_left: int) -> float:
    if periods_left <= 1:
        return 1.0
    if abs(real_return) < 1e-9:
        return 1.0 / periods_left
    return real_return / (1 - (1 + real_return) ** (-periods_left))


def sepp_life_expectancy(age: int) -> float:
    """IRS Single Life Table (2022) at ages 40-59, approximated as 86.2 - age (45: 41.0, 50: 36.2, 55: 31.6)."""
    return max(1.0, 86.2 - age)


def _take(need_after_tax: np.ndarray, bucket: np.ndarray, tax: float, cap_gross: np.ndarray | None = None) -> np.ndarray:
    """Withdraw from one bucket to deliver up to ``need_after_tax``; mutates the bucket.

    Returns the after-tax amount delivered. ``cap_gross`` limits the gross amount taken (SEPP, Roth basis).
    """
    keep = 1 - tax if tax < 1 else 1.0
    gross_wanted = need_after_tax / keep
    available = np.maximum(bucket, 0.0)
    if cap_gross is not None:
        available = np.minimum(available, np.maximum(cap_gross, 0.0))
    gross = np.minimum(gross_wanted, available)
    bucket -= gross
    return gross * keep


def _withdraw(need: np.ndarray, buckets: list[np.ndarray], tax: float) -> np.ndarray:
    """Take ``need`` (after tax) from buckets in order; mutates them; returns the unmet need (after tax)."""
    remaining = need.copy()
    for b in buckets:
        remaining = remaining - _take(remaining, b, tax)
    return remaining


def run(inputs: PlanInputs, household: Household, market: Market) -> SimResult:
    n, T = market.inflation.shape
    ages = [household.current_age + t for t in range(T)]
    years = [household.start_year + t for t in range(T)]
    events = [e for e in inputs.events if e.enabled]
    planned_retirement = inputs.retirement_age

    # A layoff: severance, unemployment benefit and accelerated vesting at the layoff; a gap without
    # pay (spending and health cover from savings); then the next job at a share of today's pay, or
    # no next job at all, which retires the household at the layoff with any part-time income.
    layoff = next((e for e in events if e.kind == "layoff" and e.start_age < inputs.retirement_age), None)
    lp = layoff_params(layoff) if layoff else None
    t_layoff = (layoff.start_age - household.current_age) if layoff else None
    if layoff and lp["never_reemployed"]:
        inputs = replace(inputs, retirement_age=max(household.current_age, layoff.start_age))
        if lp["part_time_income"] > 0:
            events = [*events, LifeEvent("part_time", layoff.start_age, planned_retirement - 1, lp["part_time_income"])]
    r_idx = max(0, inputs.retirement_age - household.current_age)
    tax_r = inputs.retirement_tax_rate

    cash = np.full(n, float(household.cash))
    taxable = np.full(n, float(household.taxable))
    company = np.full(n, float(household.company_stock))
    # The 401(k) is two pools taxed differently: pre-tax money is ordinary income when withdrawn
    # (retirement_tax_rate); Roth money is tax-free once qualified, and its contributions (roth_basis)
    # can come out tax- and penalty-free at any age.
    # Roth contributions on record imply at least that much Roth money.
    roth_start = float(min(max(household.roth_balance, household.roth_basis, 0.0), household.retirement))
    roth = np.full(n, roth_start)
    pre = np.full(n, float(household.retirement) - roth_start)
    roth_basis = np.full(n, float(min(household.roth_basis, roth_start)))
    roth_share = float(min(max(household.roth_contribution_share, 0.0), 1.0))
    cg_tax = TAXABLE_WITHDRAWAL_TAX
    home = np.full(n, float(household.home_value))
    mortgage = np.full(n, float(household.mortgage_balance))
    escrow_month = float(min(household.escrow_monthly, household.mortgage_payment_monthly))
    pi_payment = np.full(n, float(household.mortgage_payment_monthly) - escrow_month)
    escrow_month_v = np.full(n, escrow_month)
    price_index = np.ones(n)
    company_index = np.ones(n)
    alive = np.ones(n, dtype=bool)
    depleted_age = np.full(n, np.nan)
    scheduled = dict(household.scheduled_vests)

    comp0 = household.salary + household.rsu_income
    if comp0 > 0 and household.rsu_income > 0:
        share0 = household.rsu_income / comp0
    elif scheduled:
        share0 = inputs.rsu_pct_of_comp
    else:
        share0 = 0.0
    real_raise = inputs.total_comp_growth - inputs.inflation
    salary0 = comp0 * (1 - share0)  # year-0 salary under the split the loop uses
    acquired_replacement: float | None = None  # after an acquisition: yearly equity/bonus, today's $
    deal_index: np.ndarray | None = None        # after an acquisition: unvested grants convert at the deal price

    liquid_real = np.zeros((n, T))
    nw_real = np.zeros((n, T))
    spending_real = np.zeros((n, T))
    target_real = inputs.retirement_spending
    min_ratio = np.full(n, np.inf)
    cuts = np.zeros(n, dtype=int)

    spend_nominal = np.zeros(n)
    initial_wr = np.zeros(n)
    prev_return = np.zeros(n)
    magi_prev = np.zeros(n)
    sepp_annual = np.zeros(n)
    profile_mult = 1.0
    detail_keys = ("cash", "taxable", "company_stock", "retirement", "home_equity", "salary", "rsu_income",
                   "saved", "contrib_401k", "spending", "withdrawal", "social_security", "other_income",
                   "healthcare", "housing", "src_taxable", "src_roth_basis", "src_401k", "src_401k_penalty",
                   "magi", "equity_payout", "mortgage_payoff", "gap_costs", "extra_spend")
    detail = {k: np.zeros(T) for k in detail_keys}
    fra = household.full_retirement_age
    ss_annual = inputs.ss_monthly_at_fra * 12 * ss_factor(inputs.ss_claim_age, fra)
    if household.ss_earnings:
        birth_year = household.start_year - household.current_age
        stop_year = household.start_year + (inputs.retirement_age - household.current_age)
        ss_annual *= ss_stop_factor(household.ss_earnings, stop_year, birth_year + round(fra))
    real_ret_retired = (1 + inputs.retirement_return) / (1 + inputs.inflation) - 1
    rule_of_55 = inputs.retirement_age >= RULE_OF_55_AGE
    # 2025 HHS poverty guideline (48 states): $15,650 for one person, +$5,500 for each extra person.
    fpl = 15_650 + 5_500 * max(0, inputs.health_people - 1)

    for t in range(T):
        age = ages[t]
        infl = market.inflation[:, t]
        # Price index applies during the period (amounts in today's $ are inflated to this period).
        if t > 0:
            price_index = price_index * (1 + market.inflation[:, t - 1])
        working = age < inputs.retirement_age
        ret_p = market.portfolio_working[:, t] if working else market.portfolio_retired[:, t]
        health_index = price_index * (1 + inputs.health_excess_inflation) ** t

        # --- events active this period ---
        job_loss = 0.0
        extra_spend = np.zeros(n)        # today's $, before inflation
        other_income_today = 0.0         # today's $, before tax
        windfall_today = 0.0
        spending_mult = 1.0
        payout = np.zeros(n)
        for e in events:
            end = e.end_age if e.end_age is not None else e.start_age
            if e.kind == "job_loss" and e.start_age <= age <= end and working:
                job_loss = max(job_loss, min(1.0, e.pct or 1.0))
            elif e.kind == "part_time" and e.start_age <= age <= end:
                other_income_today += e.amount
            elif e.kind == "rsu_shock" and age == e.start_age:
                company_index = company_index * (1 + e.pct)
                company *= 1 + e.pct
            elif e.kind in ("one_off_expense", "recurring_expense") and e.start_age <= age <= end:
                extra_spend += e.amount  # a one-off has no end age, so end == start
            elif e.kind == "windfall" and age == e.start_age:
                windfall_today += e.amount
            elif e.kind == "spending_change" and age >= e.start_age:
                spending_mult *= 1 + e.pct
                if age == e.start_age:
                    extra_spend += e.amount
            elif e.kind == "healthcare":
                start = e.start_age if e.start_age else inputs.retirement_age
                stop = e.end_age if e.end_age is not None else MEDICARE_AGE - 1
                if not working and max(start, inputs.retirement_age) <= age <= stop:
                    extra_spend += e.amount
            elif e.kind == "acquisition" and age == e.start_age and acquired_replacement is None:
                # Close: vested shares are bought for cash at the deal price (already taxed at vest; the gain
                # since vest is not taxed here). Unvested grants convert to cash at the deal price and still pay
                # on their original vest dates (taxed as pay). New equity after close: a fixed yearly amount.
                deal = 1 + e.pct
                deal_index = company_index * deal
                payout = company * deal
                taxable += payout
                company = np.zeros(n)
                acquired_replacement = e.amount
            elif e.kind == "downsize" and age == e.start_age:
                proceeds = home * (1 - HOME_SELLING_COST) - mortgage
                new_home = e.amount * price_index
                taxable += proceeds - new_home
                # Property tax and insurance scale with the home's value.
                escrow_month_v = escrow_month_v * np.where(home > 0, new_home / np.maximum(home, 1.0), 0.0)
                home = np.array(new_home, dtype=float)
                mortgage = np.zeros(n)
                pi_payment = np.zeros(n)

        # --- layoff schedule for this period ---
        laid_off = layoff is not None and t >= t_layoff
        if laid_off and t == t_layoff:
            # Severance on today's pay path, unemployment benefit (taxable), and every unvested grant
            # accelerating and paying now (at the deal price when acquired).
            growth0 = (1 + real_raise) ** t
            sev = comp0 * growth0 * price_index * lp["severance_weeks"] / 52
            gap_weeks = min(26.0, lp["gap_months"] * 52 / 12) if not lp["never_reemployed"] else 26.0
            ui = lp["ui_weekly"] * gap_weeks * price_index
            unvested = sum(v for p, v in scheduled.items() if p >= t)
            idx = deal_index if deal_index is not None else company_index
            accel = unvested * idx * (1 - inputs.rsu_tax_rate)
            scheduled = {p: v for p, v in scheduled.items() if p < t}
            payout = payout + accel
            taxable += (sev + ui) * (1 - inputs.income_tax_rate) + accel

        employed = 1.0 - job_loss
        pay_mult, equity_on, ramp_from = 1.0, True, 0
        gap_health = np.zeros(n)
        if laid_off and working:
            k = t - t_layoff
            worked = min(1.0, max(0.0, (12 * (k + 1) - lp["gap_months"]) / 12))
            gap_share = 1.0 - worked if k * 12 < lp["gap_months"] else 0.0
            employed = employed * worked
            job_loss = max(job_loss, gap_share)
            pay_mult, equity_on, ramp_from = lp["next_pay_pct"], bool(lp["next_equity"]), t_layoff
            gap_health = lp["gap_health_annual"] * gap_share * health_index
        salary = rsu = contrib = saved = 0.0
        withdrawal = np.zeros(n)
        ss = 0.0
        health_v = np.zeros(n)
        housing_v = np.zeros(n)
        src = {k: np.zeros(n) for k in ("taxable", "taxable_gross", "roth", "roth_q", "k401", "k401_pen")}
        if working:
            growth = (1 + real_raise) ** t
            share = min(inputs.rsu_pct_cap, max(0.0, share0 + inputs.rsu_pct_annual_increase * t)) if share0 > 0 else 0.0
            total_comp = comp0 * growth * pay_mult
            salary_v = total_comp * (1 - share) * price_index * employed
            if not equity_on:
                refresh = 0.0
            elif acquired_replacement is not None and not laid_off:
                refresh = acquired_replacement * growth * price_index
            else:
                refresh = total_comp * share * min(1.0, (t - ramp_from) / VEST_YEARS) * price_index
            vesting = scheduled.get(t, 0.0) * (deal_index if deal_index is not None else company_index)
            rsu_v = (refresh + vesting) * employed
            irs_limit = household.irs_401k_limit * price_index
            employee = np.minimum(salary_v * inputs.employee_401k_rate, irs_limit)
            contrib_v = employee + salary_v * inputs.employer_match_rate
            salary_scale = (salary_v / (salary0 * price_index)) if salary0 > 0 else employed
            if household.living_spending > 0:
                # Cash flow: take-home salary less living costs, the mortgage and other debts.
                housing_work = (np.where(mortgage > 0, pi_payment * 12, 0.0) + escrow_month_v * 12) * price_index
                take_home = salary_v * (1 - inputs.income_tax_rate) - employee
                living_now = (household.living_spending + household.other_debt_payments
                              + inputs.projects_allowance) * price_index
                saved_v = (take_home - living_now - housing_work
                           + inputs.monthly_cash_savings * 12 * price_index)
            else:
                saved_v = inputs.monthly_cash_savings * 12 * price_index * salary_scale
            rsu_net = rsu_v * (1 - inputs.rsu_tax_rate)
            other_net = other_income_today * price_index * (1 - inputs.income_tax_rate)
            windfall_v = windfall_today * price_index
            hold = inputs.rsu_hold_fraction if acquired_replacement is None else 0.0

            # Grow, then add the period's money.
            cash = cash * (1 + market.bills[:, t])
            taxable = taxable * (1 + ret_p)
            company = company * (1 + market.company[:, t])
            company_index = company_index * (1 + market.company[:, t])
            pre = pre * (1 + ret_p)
            roth = roth * (1 + ret_p)
            roth += employee * roth_share
            roth_basis = roth_basis + employee * roth_share
            pre += contrib_v - employee * roth_share
            company += rsu_net * hold
            shortfall = np.maximum(-np.asarray(saved_v, dtype=float), 0.0)
            taxable += np.maximum(saved_v, 0.0) + rsu_net * (1 - hold) + other_net + windfall_v
            # A pay shortfall, out-of-work spending, gap health cover and one-off costs come out of savings.
            jobless_spend = 0.0 if household.living_spending > 0 else household.spending_last_12m * job_loss
            out = shortfall + (jobless_spend + extra_spend) * price_index + gap_health
            unmet = _withdraw(out, [cash, taxable, company], 0.0)
            before = roth.copy()
            unmet = unmet - _take(unmet, roth, 0.0, cap_gross=roth_basis)
            roth_basis = roth_basis - (before - roth)
            unmet = _withdraw(unmet, [pre, roth], tax_r + EARLY_WITHDRAWAL_PENALTY)
            newly = alive & (unmet > 1.0)
            depleted_age[newly] = age
            alive &= ~newly
            salary, rsu, contrib, saved = salary_v, rsu_v, contrib_v, saved_v
            withdrawal = out
            if np.any(mortgage > 0):
                mortgage, _ = _vec_amortize(mortgage, household.mortgage_rate, pi_payment)
        else:
            # --- living spending under the rule and profile ---
            liquid_start = cash + taxable + company + pre + roth
            if t > r_idx and inputs.spending_profile == "smile":
                profile_mult *= 1 + smile_change(age - 1)
            target_nominal = target_real * spending_mult * profile_mult * price_index
            if t == r_idx:
                spend_nominal = target_nominal.copy()
                initial_wr = np.where(liquid_start > 0, spend_nominal / np.maximum(liquid_start, 1.0), 0.0)
                if inputs.use_sepp and age < PENALTY_FREE_AGE and not rule_of_55:
                    le = sepp_life_expectancy(age)
                    sepp_annual = pre * SEPP_RATE / (1 - (1 + SEPP_RATE) ** (-le))
            elif inputs.spending_rule == "fixed":
                spend_nominal = target_nominal.copy()
            elif inputs.spending_rule == "guardrails":
                # Guyton-Klinger, with one gate: no cut and no skipped raise while the withdrawal rate is
                # still below what the portfolio could pay to the plan-to age at the expected real return
                # (the VPW rate). Without it a 1% withdrawal rate gets cut like a 6% one.
                sustainable = _vpw_rate(real_ret_retired, inputs.plan_to_age - age + 1)
                step = 1 + (smile_change(age - 1) if inputs.spending_profile == "smile" else 0.0)
                raised = spend_nominal * (1 + market.inflation[:, t - 1]) * step
                wr_now = np.where(liquid_start > 0, raised / np.maximum(liquid_start, 1.0), np.inf)
                # Withdrawal rule: no inflation raise after a losing year when the rate is above its start.
                skip = (prev_return < 0) & (wr_now > initial_wr) & (wr_now > sustainable)
                spend_nominal = np.where(skip, spend_nominal * step, raised)
                wr_now = np.where(liquid_start > 0, spend_nominal / np.maximum(liquid_start, 1.0), np.inf)
                years_left = inputs.plan_to_age - age
                cut = (wr_now > initial_wr * 1.2) & (wr_now > sustainable) & (years_left > 15)
                rise = wr_now < initial_wr * 0.8
                spend_nominal = np.where(cut, spend_nominal * 0.9, np.where(rise, spend_nominal * 1.1, spend_nominal))
            elif inputs.spending_rule == "vpw":
                rate = _vpw_rate(real_ret_retired, inputs.plan_to_age - age + 1)
                spend_nominal = np.maximum(liquid_start, 0.0) * rate

            # --- what else retirement costs ---
            if age < MEDICARE_AGE:
                # ACA marketplace: premium capped at a share of last year's MAGI below 400% of the poverty
                # line; above it the full benchmark (the subsidy cliff after the enhanced credits expired).
                full = inputs.health_people * inputs.aca_benchmark * health_index
                # The first retired year has no retired-year income yet: full benchmark (conservative; it
                # usually includes part of a salary). Later years use last year's MAGI.
                below_cliff = (magi_prev <= ACA_SUBSIDY_CLIFF_FPL * fpl * price_index) & (t > r_idx)
                # Income below 138% of the poverty line would mean Medicaid; the plan does not count on it and
                # charges the capped premium at 138% instead.
                magi_eff = np.maximum(magi_prev, 1.38 * fpl * price_index)
                health_v = np.where(below_cliff, np.minimum(full, inputs.aca_income_cap * magi_eff), full)
            else:
                health_v = inputs.health_people * inputs.medicare_cost * health_index
            mortgage_paid = np.zeros(n)
            if t == r_idx and inputs.payoff_mortgage and np.any(mortgage > 0):
                # Pay the mortgage off from savings (taxable first, then the 401(k) at the retirement rate).
                gross_401k = (1 - tax_r) if tax_r < 1 else 1.0
                left = mortgage.copy()
                for b in (cash, taxable, company):
                    take = np.minimum(left, np.maximum(b, 0.0))
                    b -= take
                    left = left - take
                take = np.minimum(left / gross_401k, np.maximum(pre, 0.0))
                pre -= take
                left = left - take * gross_401k
                take = np.minimum(left, np.maximum(roth, 0.0))
                roth -= take
                left = left - take
                mortgage_paid += mortgage - left
                mortgage = left
                pi_payment = np.where(mortgage > 0, pi_payment, 0.0)
            if np.any(mortgage > 0):
                mortgage, paid = _vec_amortize(mortgage, household.mortgage_rate, pi_payment)
                housing_v = paid + escrow_month_v * 12 * price_index
            else:
                housing_v = escrow_month_v * 12 * price_index
            payoff_lump = mortgage_paid

            payable = inputs.ss_payable_share if years[t] >= SS_SHORTFALL_YEAR else 1.0
            ss = ss_annual * payable if age >= inputs.ss_claim_age else 0.0
            ss_v = ss * price_index
            other_gross = other_income_today * price_index
            other_net = other_gross * (1 - inputs.income_tax_rate)
            windfall_v = windfall_today * price_index
            need = spend_nominal + extra_spend * price_index + health_v + housing_v - ss_v - other_net - windfall_v
            surplus = np.maximum(-need, 0.0)
            need = np.maximum(need, 0.0)
            taxable += surplus

            # --- withdrawals, and the early-access bridge ---
            remaining = need.copy()
            # Cash is principal (no tax); taxable accounts and company stock pay tax on the gain only.
            got = _take(remaining, cash, 0.0)
            src["taxable"] += got
            remaining = remaining - got
            for b in (taxable, company):
                got = _take(remaining, b, cg_tax)
                src["taxable"] += got
                src["taxable_gross"] += got / (1 - cg_tax)
                remaining = remaining - got
            if age >= PENALTY_FREE_AGE or rule_of_55:
                # Pre-tax first (taxed as income), Roth last (tax-free, and it keeps growing tax-free).
                got = _take(remaining, pre, tax_r)
                src["k401"] += got
                remaining = remaining - got
                got = _take(remaining, roth, 0.0)
                src["roth_q"] += got
                remaining = remaining - got
            else:
                # Roth contributions come out first, tax- and penalty-free (once rolled to a Roth IRA).
                before = roth.copy()
                got = _take(remaining, roth, 0.0, cap_gross=roth_basis)
                roth_basis -= before - roth
                src["roth"] += got
                remaining = remaining - got
                if inputs.use_sepp:
                    got = _take(remaining, pre, tax_r, cap_gross=sepp_annual)
                    src["k401"] += got
                    remaining = remaining - got
                for b in (pre, roth):   # Roth earnings before 59 1/2 are taxed and penalised too
                    got = _take(remaining, b, tax_r + EARLY_WITHDRAWAL_PENALTY)
                    src["k401_pen"] += got
                    remaining = remaining - got
            unmet = remaining
            withdrawal = need - unmet
            pretax_gross = (src["k401"] / (1 - tax_r) if tax_r < 1 else src["k401"]) \
                + (src["k401_pen"] / (1 - tax_r - EARLY_WITHDRAWAL_PENALTY) if tax_r + EARLY_WITHDRAWAL_PENALTY < 1 else 0)
            # MAGI: pre-tax 401(k) withdrawals, part-time pay, 85% of Social Security, and the gains share of
            # taxable withdrawals (the rest is cost basis). Roth basis is not income.
            magi_prev = pretax_gross + other_gross + 0.85 * ss_v + TAXABLE_GAIN_SHARE * src["taxable_gross"]

            target_now = target_real * spending_mult * profile_mult
            ratio = (spend_nominal / price_index) / target_now if target_now > 0 else np.ones(n)
            if inputs.spending_rule != "fixed":
                floor_fail = ratio < inputs.spending_floor
            else:
                floor_fail = np.zeros(n, dtype=bool)
            newly = alive & ((unmet > 1.0) | floor_fail)
            depleted_age[newly] = age
            alive &= ~newly
            min_ratio = np.minimum(min_ratio, np.where(unmet > 1.0, 0.0, ratio))
            if t > r_idx:
                prev_real = spending_real[:, t - 1]
                cuts += (spend_nominal / price_index < prev_real * 0.95).astype(int)
            spending_real[:, t] = np.where(unmet > 1.0, np.maximum(spend_nominal - unmet, 0.0) / price_index,
                                           spend_nominal / price_index)

            cash = cash * (1 + market.bills[:, t])
            taxable = taxable * (1 + ret_p)
            company = company * (1 + market.company[:, t])
            company_index = company_index * (1 + market.company[:, t])
            pre = pre * (1 + ret_p)
            roth = roth * (1 + ret_p)
            roth_basis = np.minimum(roth_basis, roth)
            prev_return = ret_p
            salary = 0.0
            rsu = 0.0

        home = home * (1 + inputs.home_appreciation + (infl - inputs.inflation))

        for b in (cash, taxable, company, pre, roth):
            np.maximum(b, 0.0, out=b)
        deflate = price_index * (1 + infl)  # end-of-period dollars back to today's
        liquid = cash + taxable + company + pre + roth
        liquid_real[:, t] = np.where(alive, liquid, 0.0) / deflate
        nw_real[:, t] = (np.where(alive, liquid, 0.0) + home - mortgage) / deflate

        first = lambda v: float(np.atleast_1d(v)[0])  # noqa: E731
        detail["cash"][t] = cash[0]
        detail["taxable"][t] = taxable[0]
        detail["company_stock"][t] = company[0]
        detail["retirement"][t] = pre[0] + roth[0]
        detail["home_equity"][t] = home[0] - mortgage[0]
        detail["salary"][t] = first(salary)
        detail["rsu_income"][t] = first(rsu)
        detail["saved"][t] = first(saved)
        detail["contrib_401k"][t] = first(contrib)
        detail["spending"][t] = float(spend_nominal[0]) if not working else 0.0
        detail["withdrawal"][t] = first(withdrawal)
        detail["social_security"][t] = first(ss * price_index) if not working else 0.0
        detail["other_income"][t] = first(other_income_today * price_index)
        detail["healthcare"][t] = first(health_v)
        detail["housing"][t] = first(housing_v)
        detail["mortgage_payoff"][t] = first(payoff_lump) if not working else 0.0
        detail["gap_costs"][t] = first(gap_health) if working else 0.0
        detail["extra_spend"][t] = first(extra_spend * price_index)
        detail["src_taxable"][t] = first(src["taxable"])
        detail["src_roth_basis"][t] = first(src["roth"])
        detail["src_401k"][t] = first(src["k401"] + src["roth_q"])   # pre-tax and qualified Roth
        detail["src_401k_penalty"][t] = first(src["k401_pen"])
        detail["magi"][t] = first(magi_prev) if not working else 0.0
        detail["equity_payout"][t] = first(payout)
        detail.setdefault("price_index", np.zeros(T))[t] = float(deflate[0])

    if not np.isfinite(min_ratio).any():
        min_ratio = np.ones(n)
    min_ratio = np.where(np.isfinite(min_ratio), min_ratio, 1.0)
    return SimResult(
        ages=ages, years=years, retirement_index=min(r_idx, T - 1), success=alive.copy(),
        depleted_age=depleted_age, liquid_real=liquid_real, net_worth_real=nw_real,
        spending_real=spending_real, min_spending_ratio=min_ratio, cut_count=cuts, detail=detail,
    )


def _vec_amortize(balance: np.ndarray, rate: float, monthly_payment: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """12 months of amortization for every path (balances may differ after a downsize)."""
    bal = balance.copy()
    paid = np.zeros_like(bal)
    for _ in range(12):
        interest = bal * rate / 12
        pay = np.minimum(monthly_payment, bal + interest)
        pay = np.where(bal > 0, pay, 0.0)
        bal = np.maximum(0.0, bal + interest - pay)
        paid += pay
    return bal, paid


# ---------------------------------------------------------------------------
# Summaries used by the API
# ---------------------------------------------------------------------------
PERCENTILES = (10, 25, 50, 75, 90)


def fan(values: np.ndarray) -> dict[str, list[float]]:
    """Percentile bands per period of an (n, T) array."""
    if values.shape[0] == 0:
        return {f"p{p}": [] for p in PERCENTILES}
    q = np.percentile(values, PERCENTILES, axis=0)
    return {f"p{p}": [round(float(v), 0) for v in q[i]] for i, p in enumerate(PERCENTILES)}


def success_rate(inputs: PlanInputs, household: Household, n_paths: int = 500, seed: int = DEFAULT_SEED,
                 regime: Regime | None = None, return_shift: float = 0.0) -> float:
    return run(inputs, household, simulate_market(inputs, household, n_paths, seed, regime, return_shift)).success_rate


def _bisect(f, lo: float, hi: float, target: float, increasing: bool, iters: int = 14) -> float | None:
    """Smallest (increasing) or largest (decreasing) x in [lo, hi] with f(x) >= target, or None."""
    f_lo, f_hi = f(lo), f(hi)
    if increasing:
        if f_hi < target:
            return None
        if f_lo >= target:
            return lo
    else:
        if f_lo < target:
            return None
        if f_hi >= target:
            return hi
    for _ in range(iters):
        mid = (lo + hi) / 2
        ok = f(mid) >= target
        if increasing:
            hi, lo = (mid, lo) if ok else (hi, mid)
        else:
            lo, hi = (mid, hi) if ok else (lo, mid)
    return hi if increasing else lo


@dataclass
class GoalSeek:
    target: float
    max_spending: float | None          # today's $ a year
    earliest_retirement_age: int | None
    extra_monthly_savings: float | None  # today's $ a month on top of the plan's
    required_return_shift: float | None  # added to both expected portfolio returns
    by_age: list[dict]
    by_spending: list[dict]


def goal_seek(inputs: PlanInputs, household: Household, target: float, n_paths: int = 400,
              seed: int = DEFAULT_SEED, regime: Regime | None = None) -> GoalSeek:
    """Each lever on its own, everything else fixed, same simulated markets (under ``regime``)."""
    def sr(**kw) -> float:
        return success_rate(replace(inputs, **kw), household, n_paths, seed, regime)

    def sr_shift(shift: float) -> float:
        return success_rate(inputs, household, n_paths, seed, regime, return_shift=shift)

    spend0 = max(inputs.retirement_spending, 1.0)
    max_spend = _bisect(lambda s: sr(retirement_spending=s), 0.0, spend0 * 4, target, increasing=False)

    lo_age = household.current_age + 1
    hi_age = max(lo_age, min(inputs.plan_to_age - 5, 80))
    ages = list(range(max(lo_age, inputs.retirement_age - 12), min(hi_age, inputs.retirement_age + 12) + 1))
    by_age = []
    for a in ages:
        p = replace(inputs, retirement_age=a)
        res = run(p, household, simulate_market(p, household, n_paths, seed, regime))
        i = max(0, res.retirement_index - 1)
        by_age.append({
            "age": a, "success": round(res.success_rate, 4),
            "median_at_retirement": round(float(np.median(res.liquid_real[:, i])), 0),
            "median_at_end": round(float(np.median(res.liquid_real[:, -1])), 0),
        })
    earliest = next((row["age"] for row in by_age if row["success"] >= target), None)
    if earliest is None and ages and ages[-1] < hi_age:
        for a in range(ages[-1] + 1, hi_age + 1):
            if sr(retirement_age=a) >= target:
                earliest = a
                break
    mults = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0]
    by_spending = [
        {"spending": round(spend0 * m, 0), "success": round(sr(retirement_spending=spend0 * m), 4)} for m in mults
    ]

    base = sr()
    extra = 0.0 if base >= target else _bisect(
        lambda x: sr(monthly_cash_savings=inputs.monthly_cash_savings + x), 0.0, 25_000.0, target, increasing=True)
    req = 0.0 if base >= target else _bisect(sr_shift, -0.06, 0.10, target, increasing=True)
    if base >= target:
        # Already there: report how far returns could fall before missing the target.
        req = _bisect(sr_shift, -0.08, 0.0, target, increasing=True)
    return GoalSeek(
        target=target,
        max_spending=math.floor(max_spend / 100) * 100.0 if max_spend is not None else None,  # round towards safe
        earliest_retirement_age=earliest,
        extra_monthly_savings=math.ceil(extra / 10) * 10.0 if extra is not None else None,
        required_return_shift=round(req, 4) if req is not None else None,
        by_age=by_age, by_spending=by_spending,
    )


def _with_income(inputs: PlanInputs, start_age: int, end_age: int, z: float) -> PlanInputs:
    return replace(inputs, events=[*inputs.events, LifeEvent("part_time", start_age, end_age, z, label="bridge income")])


def min_bridge_income(inputs: PlanInputs, household: Household, start_age: int, end_age: int, target: float,
                      n_paths: int = 400, seed: int = DEFAULT_SEED, regime: Regime | None = None) -> float | None:
    """Smallest extra yearly income (today's $, before tax) from ``start_age`` to ``end_age`` that brings
    the chance of success to ``target``: 0 when already there, None when even $300,000 a year is not enough."""
    if end_age < start_age:
        return None

    def sr(z: float) -> float:
        return success_rate(_with_income(inputs, start_age, end_age, z), household, n_paths, seed, regime)

    z = _bisect(sr, 0.0, 300_000.0, target, increasing=True, iters=12)
    return None if z is None else math.ceil(z / 500) * 500.0


def min_income_plan_line_solvent(inputs: PlanInputs, household: Household, start_age: int, end_age: int) -> float | None:
    """Smallest extra yearly income from ``start_age`` to ``end_age`` with which the plan line (every return
    at its median) never runs out: 0 when it already lasts, None when $300,000 a year is not enough."""
    if end_age < start_age:
        return None

    def lasts(z: float) -> float:
        p = _with_income(inputs, start_age, end_age, z)
        return 1.0 if run(p, household, expected_market(p, household)).success[0] else 0.0

    z = _bisect(lasts, 0.0, 300_000.0, 1.0, increasing=True, iters=14)
    return None if z is None else math.ceil(z / 500) * 500.0


def sprint_inputs(inputs: PlanInputs) -> PlanInputs:
    """'Sprint to retirement': the 401(k) at the IRS limit and every equity payout sold and invested."""
    return replace(inputs, employee_401k_rate=1.0, rsu_hold_fraction=0.0)


def sprint_grid(inputs: PlanInputs, household: Household, target: float, ages: list[int], shifts: list[float],
                n_paths: int = 300, seed: int = DEFAULT_SEED, regime: Regime | None = None) -> list[dict]:
    """Most living spending (today's $) that reaches ``target`` for each retirement age and return shift."""
    rows = []
    for a in ages:
        p = replace(inputs, retirement_age=a)
        cells = []
        for s in shifts:
            def sr(spend: float, p=p, s=s) -> float:
                return success_rate(replace(p, retirement_spending=spend), household, n_paths, seed, regime, return_shift=s)
            m = _bisect(sr, 0.0, max(inputs.retirement_spending, 50_000.0) * 4, target, increasing=False, iters=10)
            cells.append(None if m is None else math.floor(m / 500) * 500.0)
        rows.append({"age": a, "max_spending": cells})
    return rows


def earliest_age_for(grid: list[dict], column: int, spending: float) -> int | None:
    """From a sprint grid: the first retirement age whose maximum spending covers ``spending``."""
    for row in grid:
        m = row["max_spending"][column]
        if m is not None and m >= spending:
            return row["age"]
    return None


def historical_withdrawal_rates(stock_share: float, horizon: int) -> dict | None:
    """Highest constant real withdrawal rate each complete historical retirement of ``horizon`` years
    could sustain (withdrawals at the start of each year, rebalanced mix, CPI-adjusted).

    For returns g_k the money lasts exactly when W x sum_k prod_{j<k} 1/(1+g_j) <= 1, so the maximum
    rate is 1 / that sum. Returns the worst (Bengen's SAFEMAX), 10th percentile and median across
    start years, or None when the record is shorter than the horizon.
    """
    w = min(1.0, max(0.0, stock_share))
    real = (1 + w * _H[:, 0] + (1 - w) * _H[:, 1]) / (1 + _H[:, 3]) - 1
    starts = len(real) - horizon + 1
    if starts <= 0 or horizon <= 0:
        return None
    rates = []
    for s in range(starts):
        disc, total = 1.0, 0.0
        for k in range(horizon):
            total += disc
            disc /= 1 + real[s + k]
        rates.append(1 / total)
    arr = np.array(rates)
    worst = int(np.argmin(arr))
    return {
        "horizon": horizon, "cohorts": starts,
        "worst": round(float(arr.min()), 4), "worst_start": HISTORY_YEARS[worst],
        "p10": round(float(np.percentile(arr, 10)), 4), "median": round(float(np.median(arr)), 4),
    }


def history_mix_stats(stock_share: float) -> dict:
    """What a stock/bond mix returned over the whole record: the yardstick for the return assumptions."""
    w = min(1.0, max(0.0, stock_share))
    nominal = w * _H[:, 0] + (1 - w) * _H[:, 1]
    real = (1 + nominal) / (1 + _H[:, 3]) - 1
    years = len(nominal)
    return {
        "stock_share": w,
        "from_year": HISTORY_YEARS[0], "to_year": HISTORY_YEARS[-1],
        "nominal_mean": round(float(nominal.mean()), 4),
        "real_mean": round(float(real.mean()), 4),
        "nominal_cagr": round(float(np.prod(1 + nominal) ** (1 / years) - 1), 4),
        "real_cagr": round(float(np.prod(1 + real) ** (1 / years) - 1), 4),
        "volatility": round(portfolio_volatility(w), 4),
        "inflation_mean": round(float(_H[:, 3].mean()), 4),
    }
