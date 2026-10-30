"""The one assumption vocabulary for plans: key, label, category, default, unit, range, meaning.

The API's defaults for new plans, the seed, the Alembic backfill (0006planv2) and the Planning page's
levers all read this list, so a key means the same thing everywhere. Age is not an assumption: it
comes from the household's birth date (household_profile). The research behind each default is in
docs/requirements/planning-v2.md ("Defaults and where they come from").

Units: pct (a fraction shown as a percent), usd (today's dollars a year), usd_month, age, count, flag (0/1).
"""
from __future__ import annotations

ASSUMPTIONS: list[dict] = [
    # career / income
    {"key": "retirement_age", "display_name": "Retirement Age", "category": "career", "value": 60, "unit": "age",
     "sensitivity": "high", "min": 35, "max": 80,
     "description": "First year with no salary or RSU income. Unvested RSUs after this age are forfeited. Leaving at 55 or later opens that employer's 401(k) without penalty (rule of 55)."},
    {"key": "total_comp_growth", "display_name": "Total Comp Growth", "category": "career", "value": 0.04, "unit": "pct",
     "sensitivity": "high", "min": -0.05, "max": 0.15,
     "description": "Yearly growth of salary plus RSU, in nominal terms. The real raise is this minus inflation; in a high-inflation scenario pay keeps up with inflation plus that raise."},
    {"key": "rsu_pct_of_comp", "display_name": "RSU % of Total Comp", "category": "career", "value": 0.37, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.9,
     "description": "Used only when the latest W-2 has no RSU income but vests are scheduled; otherwise the RSU share comes from the W-2 split."},
    {"key": "rsu_pct_annual_increase", "display_name": "RSU % Annual Increase", "category": "career", "value": 0.005, "unit": "pct",
     "sensitivity": "low", "min": -0.05, "max": 0.05,
     "description": "How much the RSU share of comp moves each year (percentage points)."},
    {"key": "rsu_pct_cap", "display_name": "RSU % Cap", "category": "career", "value": 0.50, "unit": "pct",
     "sensitivity": "low", "min": 0, "max": 0.9, "description": "Ceiling on the RSU share of comp."},
    {"key": "rsu_hold_fraction", "display_name": "RSU Kept as Company Stock", "category": "career", "value": 0.5, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 1,
     "description": "Share of after-tax vested RSUs kept as company stock; the rest is sold into the taxable portfolio."},
    {"key": "employee_401k_rate", "display_name": "401(k) Employee Contribution", "category": "career", "value": 0.10, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.5,
     "description": "Share of salary contributed, capped at the IRS limit (which rises with inflation)."},
    {"key": "employer_match_rate", "display_name": "401(k) Employer Match", "category": "career", "value": 0.06, "unit": "pct",
     "sensitivity": "low", "min": 0, "max": 0.2, "description": "Employer contribution as a share of salary."},
    # spending and savings
    {"key": "monthly_cash_savings", "display_name": "Monthly Savings from Pay", "category": "spending", "value": 440, "unit": "usd_month",
     "sensitivity": "medium", "min": 0, "max": 50000,
     "description": "What you save from salary each month after living costs, in today's dollars; it grows in step with salary. After-tax RSU proceeds are saved on top."},
    {"key": "retirement_spending", "display_name": "Retirement Living Spending", "category": "spending", "value": 100000, "unit": "usd",
     "sensitivity": "high", "min": 0, "max": 1000000,
     "description": "Yearly living spending in retirement in today's dollars, before tax. Excludes the mortgage, property tax/insurance and health care, which the plan adds itself. 'What will retirement cost?' derives a figure from your actual spending."},
    {"key": "spending_floor", "display_name": "Spending Floor", "category": "spending", "value": 0.75, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 1,
     "description": "Guardrails and VPW only: a path counts as a failure when real spending falls below this share of the target."},
    {"key": "commute_reduction", "display_name": "Work Costs That Stop", "category": "spending", "value": 0.5, "unit": "pct",
     "sensitivity": "low", "min": 0, "max": 1,
     "description": "Share of commuting and transport spending (fuel, parking, tolls, transit) that stops at retirement, used by 'What will retirement cost?'."},
    {"key": "payoff_mortgage", "display_name": "Pay Off the Mortgage at Retirement", "category": "spending", "value": 0, "unit": "flag",
     "sensitivity": "low", "min": 0, "max": 1,
     "description": "Pay the remaining mortgage from savings in the first retired year (taxable first, then the 401(k) at the retirement tax rate). Property tax and insurance continue either way."},
    # retirement income and access
    {"key": "plan_to_age", "display_name": "Plan to Age", "category": "retirement", "value": 95, "unit": "age",
     "sensitivity": "medium", "min": 70, "max": 110, "description": "The money has to last to this age."},
    {"key": "ss_monthly_at_fra", "display_name": "Social Security at Full Age", "category": "retirement", "value": 0, "unit": "usd_month",
     "sensitivity": "medium", "min": 0, "max": 10000,
     "description": "Monthly benefit at full retirement age in today's dollars, from your statement at ssa.gov/myaccount. 0 means not counted."},
    {"key": "ss_claim_age", "display_name": "Social Security Claim Age", "category": "retirement", "value": 67, "unit": "age",
     "sensitivity": "medium", "min": 62, "max": 70,
     "description": "With a full retirement age of 67, claiming at 62 pays 70% of the benefit; each year of delay to 70 adds 8% (124% at 70)."},
    {"key": "ss_payable_share", "display_name": "Social Security Paid After 2034", "category": "retirement", "value": 1.0, "unit": "pct",
     "sensitivity": "medium", "min": 0.5, "max": 1,
     "description": "Share of scheduled benefits paid from 2034. The 2025 Trustees Report projects 81% payable once the combined trust funds run out in 2034 unless Congress acts."},
    {"key": "use_sepp", "display_name": "Use 72(t) Payments Before 59½", "category": "retirement", "value": 0, "unit": "flag",
     "sensitivity": "low", "min": 0, "max": 1,
     "description": "Retiring before 55: take substantially equal periodic payments from the 401(k) (amortization at 5%, IRS Notice 2022-6) without the 10% penalty. Once started they must continue for 5 years or to 59½."},
    {"key": "success_target", "display_name": "Target Chance of Success", "category": "retirement", "value": 0.85, "unit": "pct",
     "sensitivity": "low", "min": 0.5, "max": 0.99,
     "description": "The bar 'what would need to be true' aims for."},
    # health care in retirement
    {"key": "health_people", "display_name": "People Insured", "category": "health", "value": 1, "unit": "count",
     "sensitivity": "medium", "min": 1, "max": 6,
     "description": "People the household buys health cover for in retirement (premiums and Medicare are per person)."},
    {"key": "aca_benchmark", "display_name": "Pre-65 Premium per Person", "category": "health", "value": 15000, "unit": "usd",
     "sensitivity": "medium", "min": 0, "max": 50000,
     "description": "Unsubsidised benchmark (second-lowest silver) marketplace premium per person, today's dollars. KFF: about $14,900 for a 60-year-old in 2026. The plan caps it at a share of income below 400% of the poverty line."},
    {"key": "aca_income_cap", "display_name": "Premium Cap (Share of Income)", "category": "health", "value": 0.0996, "unit": "pct",
     "sensitivity": "low", "min": 0, "max": 0.2,
     "description": "Below 400% of the poverty line the benchmark premium is capped at this share of MAGI (9.96% at the top of the scale in 2026, after the enhanced credits expired). Above it there is no subsidy."},
    {"key": "medicare_cost", "display_name": "Medicare-Age Health Cost per Person", "category": "health", "value": 8500, "unit": "usd",
     "sensitivity": "medium", "min": 0, "max": 40000,
     "description": "Part B and D premiums, Medigap and out-of-pocket costs per person per year from 65. Fidelity's 2026 estimate is $185,500 over retirement for a 65-year-old (about $8,500 a year); Part B alone is $202.90 a month in 2026."},
    {"key": "health_excess_inflation", "display_name": "Health Cost Inflation Above CPI", "category": "health", "value": 0.02, "unit": "pct",
     "sensitivity": "low", "min": 0, "max": 0.06,
     "description": "Health costs grow at inflation plus this much a year."},
    # markets
    {"key": "investment_return", "display_name": "Pre-Retirement Return", "category": "markets", "value": 0.07, "unit": "pct",
     "sensitivity": "high", "min": -0.02, "max": 0.15,
     "description": "Expected (average) nominal yearly return of the portfolio while working."},
    {"key": "retirement_return", "display_name": "Post-Retirement Return", "category": "markets", "value": 0.05, "unit": "pct",
     "sensitivity": "high", "min": -0.02, "max": 0.15,
     "description": "Expected (average) nominal yearly return of the portfolio in retirement."},
    {"key": "stock_allocation_working", "display_name": "Stocks While Working", "category": "markets", "value": 0.90, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 1,
     "description": "Stock share of the portfolio while working. Sets the volatility of Monte Carlo returns and the stock/bond mix in historical replays."},
    {"key": "stock_allocation_retired", "display_name": "Stocks in Retirement", "category": "markets", "value": 0.60, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 1,
     "description": "Stock share of the portfolio in retirement (volatility and historical mix)."},
    {"key": "stock_price_growth", "display_name": "Company Stock Growth", "category": "markets", "value": 0.07, "unit": "pct",
     "sensitivity": "medium", "min": -0.1, "max": 0.3,
     "description": "Expected yearly change of the company share price; Monte Carlo adds single-stock volatility (30% a year)."},
    {"key": "inflation", "display_name": "Inflation Rate", "category": "markets", "value": 0.03, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.12, "description": "Long-run average inflation; Monte Carlo varies it year to year."},
    {"key": "home_appreciation", "display_name": "Home Appreciation", "category": "markets", "value": 0.03, "unit": "pct",
     "sensitivity": "low", "min": -0.05, "max": 0.1, "description": "Nominal yearly change of the home's value."},
    # tax
    {"key": "income_tax_rate", "display_name": "Tax Rate on Pay", "category": "tax", "value": 0.30, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.6,
     "description": "All-in effective rate on salary and part-time income (federal, state, FICA)."},
    {"key": "rsu_tax_rate", "display_name": "RSU Tax Rate at Vest", "category": "tax", "value": 0.40, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.6, "description": "Effective tax on RSU income when it vests (and on an acquisition cash-out)."},
    {"key": "retirement_tax_rate", "display_name": "Retirement Tax Rate", "category": "tax", "value": 0.20, "unit": "pct",
     "sensitivity": "medium", "min": 0, "max": 0.5,
     "description": "Effective tax on withdrawals in retirement (one rate for 401(k) and taxable; Roth contributions come out tax-free)."},
]

BY_KEY: dict[str, dict] = {a["key"]: a for a in ASSUMPTIONS}

# Keys added by the planning v2 work (Alembic 0006planv2 backfills them into existing plans).
V2_KEYS = (
    "rsu_hold_fraction", "spending_floor", "commute_reduction", "payoff_mortgage", "plan_to_age", "ss_monthly_at_fra", "ss_claim_age",
    "ss_payable_share", "use_sepp", "success_target", "health_people", "aca_benchmark", "aca_income_cap",
    "medicare_cost", "health_excess_inflation", "stock_allocation_working", "stock_allocation_retired",
    "income_tax_rate",
)
# Keys v2 removes: age comes from the household's birth date.
REMOVED_KEYS = ("current_age",)


def default(key: str) -> float:
    return float(BY_KEY[key]["value"])
