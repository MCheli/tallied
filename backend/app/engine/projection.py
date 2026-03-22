"""
Retirement / Long-Range Projection engine.

Pure computation — no framework dependencies.
Takes current financial state + assumptions, returns year-by-year projections to age 90.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectionInput:
    current_age: int  # e.g. 33
    current_year: int  # e.g. 2026

    # Current balances (five liquidity buckets)
    cash: float
    investments: float  # non-retirement investments (stock/brokerage)
    company_stock: float  # current value of unvested + sellable RSUs
    home_equity: float  # home value minus mortgage balance
    retirement_bal: float  # 401k / IRA

    # Current income
    salary: float
    rsu_income: float  # annual RSU vest income

    # Mortgage details
    mortgage_balance: float
    mortgage_rate: float  # annual rate, e.g. 0.065
    mortgage_monthly_payment: float

    # 401k
    employee_401k_rate: float  # fraction of salary, e.g. 0.10
    employer_match_rate: float  # fraction of salary, e.g. 0.06
    irs_401k_limit: float  # e.g. 23500


@dataclass
class ProjectionAssumptions:
    retirement_age: int = 60
    total_comp_growth: float = 0.04
    rsu_pct_of_comp: float = 0.37
    rsu_pct_annual_increase: float = 0.005  # 0.5 pp per year
    rsu_pct_cap: float = 0.50
    rsu_tax_rate: float = 0.40
    investment_return: float = 0.07
    retirement_return: float = 0.05
    stock_price_growth: float = 0.07
    inflation: float = 0.03
    home_appreciation: float = 0.03
    monthly_cash_savings: float = 440.0
    retirement_spending: float = 100_000.0  # today's dollars
    retirement_tax_rate: float = 0.20


@dataclass
class ProjectionRow:
    year: int
    age: int
    phase: str  # "working" or "retired"
    salary: float
    rsu_income: float
    total_comp: float
    cash: float
    investments: float
    company_stock: float
    home_equity: float
    retirement_bal: float
    net_worth: float
    withdrawal: float = 0.0


def _amortize_year(balance: float, annual_rate: float, monthly_payment: float) -> float:
    """Run 12 months of mortgage amortization, return new balance."""
    bal = balance
    for _ in range(12):
        if bal <= 0:
            break
        interest = bal * annual_rate / 12
        principal = monthly_payment - interest
        if principal <= 0:
            # Payment doesn't cover interest — balance isn't shrinking.
            break
        bal = max(0.0, bal - principal)
    return bal


def run_projection(
    inputs: ProjectionInput,
    assumptions: ProjectionAssumptions,
) -> list[ProjectionRow]:
    """
    Produce year-by-year projections from *current_age* to age 90.

    WORKING PHASE (current_age .. retirement_age - 1):
      - total_comp grows by total_comp_growth each year (after year 0)
      - rsu_pct ramps by rsu_pct_annual_increase, capped at rsu_pct_cap
      - salary  = total_comp * (1 - rsu_pct)
      - rsu_income = total_comp * rsu_pct
      - 401k: employee contributes min(salary * rate, IRS limit inflated);
              employer contributes salary * match rate
      - RSU after-tax proceeds split 50/50 between company_stock and investments
      - cash grows by monthly_cash_savings * 12
      - home appreciates, mortgage amortises

    RETIRED PHASE (retirement_age .. 90):
      - No income
      - Spending = retirement_spending inflated from current_year
      - Gross withdrawal = spending / (1 - retirement_tax_rate)
      - Draw order: cash -> investments -> company_stock -> retirement
      - Remaining balances grow at retirement_return (cash at 1 %)
      - Home continues appreciating / mortgage continues
    """
    rows: list[ProjectionRow] = []

    # ---- mutable state ----
    cash = inputs.cash
    investments = inputs.investments
    company_stock = inputs.company_stock
    retirement_bal = inputs.retirement_bal

    mortgage_bal = inputs.mortgage_balance
    home_value = inputs.home_equity + mortgage_bal  # derive initial home value

    total_comp = inputs.salary + inputs.rsu_income

    # Starting RSU % — derive from actuals when RSU income is known.
    if total_comp > 0 and inputs.rsu_income > 0:
        rsu_pct = inputs.rsu_income / total_comp
    else:
        rsu_pct = assumptions.rsu_pct_of_comp

    end_age = 90

    for age in range(inputs.current_age, end_age + 1):
        year = inputs.current_year + (age - inputs.current_age)

        if age < assumptions.retirement_age:
            phase = "working"

            # --- grow comp (skip first year — we already have actuals) ---
            if age > inputs.current_age:
                total_comp *= 1 + assumptions.total_comp_growth
                rsu_pct = min(rsu_pct + assumptions.rsu_pct_annual_increase,
                              assumptions.rsu_pct_cap)

            salary = total_comp * (1 - rsu_pct)
            rsu_income = total_comp * rsu_pct

            # --- 401k contributions ---
            years_elapsed = age - inputs.current_age
            irs_limit = inputs.irs_401k_limit * (1 + assumptions.inflation) ** years_elapsed
            employee_contrib = min(salary * inputs.employee_401k_rate, irs_limit)
            employer_contrib = salary * inputs.employer_match_rate

            retirement_bal = (retirement_bal * (1 + assumptions.investment_return)
                              + employee_contrib + employer_contrib)

            # --- RSU after-tax split ---
            rsu_after_tax = rsu_income * (1 - assumptions.rsu_tax_rate)
            keep_half = rsu_after_tax * 0.5
            sell_half = rsu_after_tax * 0.5

            company_stock = company_stock * (1 + assumptions.stock_price_growth) + keep_half
            investments = investments * (1 + assumptions.investment_return) + sell_half

            # --- cash ---
            cash += assumptions.monthly_cash_savings * 12

            # --- home ---
            home_value *= 1 + assumptions.home_appreciation
            mortgage_bal = _amortize_year(mortgage_bal, inputs.mortgage_rate,
                                          inputs.mortgage_monthly_payment)
            home_equity = home_value - mortgage_bal

            withdrawal = 0.0

        else:
            phase = "retired"
            salary = 0.0
            rsu_income = 0.0
            total_comp = 0.0

            # --- inflation-adjusted spending ---
            years_from_start = year - inputs.current_year
            real_spending = assumptions.retirement_spending * (1 + assumptions.inflation) ** years_from_start
            gross_withdrawal = real_spending / (1 - assumptions.retirement_tax_rate)

            withdrawal = gross_withdrawal
            remaining = gross_withdrawal

            # Draw in liquidity order
            draw = min(remaining, max(0.0, cash))
            cash -= draw
            remaining -= draw

            draw = min(remaining, max(0.0, investments))
            investments -= draw
            remaining -= draw

            draw = min(remaining, max(0.0, company_stock))
            company_stock -= draw
            remaining -= draw

            draw = min(remaining, max(0.0, retirement_bal))
            retirement_bal -= draw
            remaining -= draw

            # Grow remaining balances
            if cash > 0:
                cash *= 1.01  # minimal cash return
            investments = max(0.0, investments) * (1 + assumptions.retirement_return)
            company_stock = max(0.0, company_stock) * (1 + assumptions.retirement_return)
            retirement_bal = max(0.0, retirement_bal) * (1 + assumptions.retirement_return)

            # Home
            home_value *= 1 + assumptions.home_appreciation
            mortgage_bal = _amortize_year(mortgage_bal, inputs.mortgage_rate,
                                          inputs.mortgage_monthly_payment)
            home_equity = home_value - mortgage_bal

        net_worth = cash + investments + company_stock + home_equity + retirement_bal

        rows.append(ProjectionRow(
            year=year,
            age=age,
            phase=phase,
            salary=round(salary, 2) if phase == "working" else 0.0,
            rsu_income=round(rsu_income, 2) if phase == "working" else 0.0,
            total_comp=round(total_comp, 2) if phase == "working" else 0.0,
            cash=round(cash, 2),
            investments=round(investments, 2),
            company_stock=round(company_stock, 2),
            home_equity=round(home_equity, 2),
            retirement_bal=round(retirement_bal, 2),
            net_worth=round(net_worth, 2),
            withdrawal=round(withdrawal, 2) if phase == "retired" else 0.0,
        ))

    return rows
