"""
Seed human-readable descriptions for all database tables and key columns.

Uses PostgreSQL native COMMENT ON TABLE/COLUMN statements.
These descriptions appear in the Database Viewer when hovering over
table names and column names.

Usage: python scripts/seed_schema_descriptions.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import engine
from sqlalchemy import text

DESCRIPTIONS = {
    # ── Financial ──
    "accounts": {
        "_table": "Financial accounts you own — every balance snapshot and transaction links to an account. Accounts are grouped into liquidity layers (Cash, Investments, Home Equity, Retirement).",
        "id": "Unique account identifier (string, often from Monarch or Plaid import)",
        "name": "Display name shown in the UI (e.g., 'Checking Account (...4521)')",
        "institution": "Bank or brokerage name (e.g., 'Chase', 'Fidelity')",
        "account_type": "Type classification: cash, investment_stock, investment_401k, real_estate, loan_mortgage, credit_card",
        "display_group": "Which wealth layer this account belongs to: Cash, Investments, Retirement, Home Equity, Credit Cards, Other Loans",
        "include_in_nw": "Whether this account counts toward net worth calculation",
        "is_active": "Whether this account is visible in the UI. Inactive accounts are hidden but data is preserved.",
    },
    "balance_snapshots": {
        "_table": "Point-in-time balance reading for an account. Multiple snapshots over time build the net worth trend chart. Each snapshot records the balance on a specific date.",
        "account_id": "FK to accounts — which account this balance belongs to",
        "snapshot_date": "Date of the balance reading",
        "balance": "Dollar amount of the account balance on this date. Positive for assets, negative for liabilities.",
        "source": "Where this reading came from: 'seed', 'plaid', 'monarch', 'manual'",
    },
    "transactions": {
        "_table": "Individual debits and credits — every purchase, paycheck, and transfer. The raw material for spending analysis. Negative amounts are expenses, positive are income.",
        "account_id": "FK to accounts — which account this transaction occurred in",
        "date": "Date of the transaction",
        "amount": "Dollar amount. Negative = expense/outflow, Positive = income/deposit.",
        "merchant": "Name of the merchant or payee",
        "category": "Spending category (e.g., 'Groceries', 'Paychecks', 'Transfer')",
        "category_group": "Higher-level category grouping",
        "is_recurring": "Whether this is detected as a recurring expense",
        "source": "Data source: 'seed', 'plaid', 'monarch'",
    },
    "w2_records": {
        "_table": "Annual compensation summary — one row per tax year. The authoritative source for income data in the planning model. Populated from W2 PDF uploads or pay stubs.",
        "tax_year": "The calendar year this W2 covers (e.g., 2025)",
        "gross_pay": "Total compensation before any deductions — base salary + RSU + other",
        "base_salary": "Regular salary component (from pay stub YTD, not on W2)",
        "rsu_income": "RSU vesting income component (from pay stub YTD, not on W2)",
        "federal_tax": "Federal income tax withheld (W2 Box 2)",
        "state_tax": "State income tax withheld (W2 Box 17)",
        "social_security": "Social Security tax withheld (W2 Box 4)",
        "medicare": "Medicare tax withheld (W2 Box 6)",
        "pretax_401k": "Pre-tax 401(k) contributions (W2 Box 12 Code D)",
        "roth_401k": "Roth 401(k) contributions (W2 Box 12 Code AA)",
        "cafeteria_125": "Section 125 cafeteria plan deductions (FSA, dental, medical)",
        "transit": "Commuter/transit pre-tax benefit deductions",
        "employer_health": "Employer health insurance cost (W2 Box 12 Code DD)",
    },

    # ── Investments ──
    "rsu_grants": {
        "_table": "RSU (Restricted Stock Unit) grants from your employer. Each grant has a vesting schedule and tracks how many shares have vested, are sellable, or are still unvested.",
        "company": "Company that issued the grant",
        "symbol": "Stock ticker symbol (e.g., 'MSFT')",
        "grant_date": "Date the RSU grant was awarded",
        "total_shares": "Total number of shares in this grant",
        "vested_shares": "Shares that have vested (you own them)",
        "unvested_shares": "Shares that haven't vested yet (scheduled for future)",
        "sellable_shares": "Shares you can sell right now (vested minus those already sold/withheld)",
        "share_price": "Estimated current share price at time of last data import",
    },
    "vest_events": {
        "_table": "Individual vesting events within an RSU grant. Each event records when shares vested, the FMV at vest (cost basis), taxes withheld, and net shares received.",
        "grant_id": "FK to rsu_grants — which grant this vest belongs to",
        "vest_date": "Date shares vested (or will vest if is_actual=false)",
        "vest_period": "Which vesting period (1, 2, 3 typically for 3-year annual vesting)",
        "shares": "Number of shares in this vest event",
        "fmv_at_vest": "Fair market value per share at vest date — this is your cost basis for tax purposes",
        "shares_withheld": "Shares sold automatically to cover tax withholding",
        "shares_released": "Net shares received after tax withholding",
        "total_taxes_paid": "Total dollar amount of taxes withheld at vesting",
        "is_actual": "True = this vest has already occurred. False = scheduled future vest.",
    },
    "stock_prices": {
        "_table": "Daily stock price cache. Fetched from Yahoo Finance and cached to avoid repeated API calls. Used for RSU valuation and stock price charts.",
        "symbol": "Stock ticker symbol",
        "price_date": "Date of the price",
        "close_price": "Closing price on this date",
        "source": "Where the price came from: 'yahoo', 'seed', 'etrade_export'",
    },

    # ── Retirement ──
    "retirement_accounts": {
        "_table": "401(k) or other retirement account summary. Tracks total balance, Roth vs pretax breakdown, contribution rates, and provider details. Updated from statement PDF uploads.",
        "plan_name": "Official plan name (e.g., 'MICROSOFT CORPORATION 401(K) PLAN')",
        "provider": "Plan administrator (e.g., 'Fidelity Investments', 'T. Rowe Price')",
        "total_balance": "Total account balance across all contribution types",
        "roth_balance": "Balance in Roth (after-tax) sub-account",
        "pretax_balance": "Balance in pre-tax (traditional) sub-account",
        "employer_match_balance": "Balance from employer matching contributions",
        "pretax_deferral_rate": "Current pre-tax contribution rate as decimal (0.10 = 10%)",
        "roth_deferral_rate": "Current Roth contribution rate as decimal (0.02 = 2%)",
        "roth_basis": "Total lifetime Roth contributions (for tax-free withdrawal tracking)",
        "account_return": "Account return percentage since inception as decimal (0.1474 = 14.74%)",
    },
    "retirement_holdings": {
        "_table": "Individual fund holdings within a retirement account. Most 401(k)s hold one target-date fund at 100% allocation.",
        "fund_name": "Full fund name (e.g., 'Fidelity Freedom 2055 Fund')",
        "ticker": "Fund ticker symbol for live price lookup",
        "balance": "Current balance in this fund",
        "allocation_pct": "Percentage of total account allocated to this fund (1.0 = 100%)",
    },

    # ── Property ──
    "mortgages": {
        "_table": "Mortgage loan details. Updated from mortgage statement PDF uploads. Used for amortization schedule projection and equity calculation.",
        "account_id": "FK to accounts — the mortgage loan account",
        "rate": "Annual interest rate as decimal (0.0425 = 4.25%)",
        "monthly_payment": "Total monthly payment including principal, interest, and escrow",
        "current_balance": "Outstanding principal balance (updated from latest statement)",
        "original_amount": "Original loan amount at origination",
    },
    "property_valuations": {
        "_table": "Point-in-time property value estimates. Can come from Zillow, manual entry, or appraisals. Used for equity calculation (value - mortgage = equity).",
        "account_id": "FK to accounts — the real estate account",
        "valuation_date": "Date of the valuation",
        "value": "Estimated property value in dollars",
        "source": "Where the estimate came from: 'Zillow Estimate', 'Manual', 'Appraisal'",
    },

    # ── Assets ──
    "vehicles": {
        "_table": "Fixed capital assets — vehicles. Tracks purchase price, current estimated value (via AI), and depreciation. Market values can be refreshed on demand.",
        "year": "Model year of the vehicle",
        "make": "Manufacturer (e.g., 'Toyota', 'Honda')",
        "model": "Model name (e.g., 'RAV4', 'Civic')",
        "mileage": "Current odometer reading",
        "condition": "Condition rating: excellent, very_good, good, fair, poor",
        "purchase_price": "What you paid for the vehicle (for depreciation tracking)",
        "estimated_value": "Current estimated market value (from Claude AI estimation)",
    },

    # ── Planning ──
    "plan_versions": {
        "_table": "Named retirement scenarios (e.g., 'Retire at 60', 'Retire at 45'). Each plan has assumptions and year-by-year projections.",
        "name": "Plan name displayed in the UI",
        "scenario_type": "Classification: base, optimistic, pessimistic, custom",
        "is_active": "Whether this is the currently selected plan",
    },
    "plan_assumptions": {
        "_table": "Key-value assumptions that drive plan projections. Each assumption has a display name, category, and sensitivity rating.",
        "plan_id": "FK to plan_versions — which plan these assumptions belong to",
        "key": "Machine-readable key (e.g., 'retirement_age', 'total_comp_growth')",
        "display_name": "Human-readable name shown in the UI",
        "value": "Numeric value (rates as decimals: 0.04 = 4%)",
        "sensitivity": "Impact rating: high, medium, low",
    },

    # ── System ──
    "users": {
        "_table": "Application users. Supports Google SSO (production) and local email/password (dev mode). Each user has a display name and admin flag.",
        "email": "Login email address (unique)",
        "auth_provider": "How the user authenticates: 'google' or 'local'",
        "is_admin": "Whether the user has admin privileges",
    },
    "import_sessions": {
        "_table": "Tracks file upload → AI parsing → review → confirmation workflow. Each session represents one document being imported.",
        "status": "Workflow state: uploading, processing, review, confirmed, rejected, expired",
        "context": "Import context: income, retirement, property, rsu, general",
        "ai_summary": "Natural language summary of what the AI found in the document",
    },
    "plaid_links": {
        "_table": "Connected Plaid institutions for automatic bank transaction sync. Each link represents one connected bank/brokerage.",
        "item_id": "Plaid item identifier (unique per institution connection)",
        "access_token": "Encrypted Plaid access token for API calls",
        "institution_name": "Display name of the connected bank",
        "cursor": "Plaid sync cursor for incremental transaction updates",
    },
}


PLATFORM_TABLES = {"users", "tenants", "tenant_memberships"}


def seed_descriptions(schema_name: str = "public"):
    count = 0
    skip_tables = PLATFORM_TABLES if schema_name != "public" else set()
    with engine.connect() as conn:
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        for table_name, fields in DESCRIPTIONS.items():
            if table_name in skip_tables:
                continue
            for field_name, description in fields.items():
                # Escape single quotes in descriptions
                safe_desc = description.replace("'", "''")

                if field_name == "_table":
                    conn.execute(text(
                        f"COMMENT ON TABLE \"{table_name}\" IS '{safe_desc}'"
                    ))
                else:
                    try:
                        conn.execute(text(
                            f"COMMENT ON COLUMN \"{table_name}\".\"{field_name}\" IS '{safe_desc}'"
                        ))
                    except Exception as e:
                        print(f"  Warning: Could not comment {table_name}.{field_name}: {e}")
                        conn.rollback()
                        continue
                count += 1

        conn.commit()

    print(f"Seeded {count} COMMENT ON statements across {len(DESCRIPTIONS)} tables")


if __name__ == "__main__":
    import sys
    schema = sys.argv[1] if len(sys.argv) > 1 else "public"
    seed_descriptions(schema)
