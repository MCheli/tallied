"""planning v2: household birth date, life events, spending rule and profile, new assumption keys

Revision ID: 0005planv2
Revises: 0004nwbackfill
Create Date: 2026-10-29

docs/requirements/planning-v2.md. Per tenant schema:
  - household_profile: one row with the household's birth date (age is computed from it, never typed)
  - plan_events: one row per life event in a plan (layoff, acquisition, part-time years, ...), with params
  - plan_versions.spending_rule (fixed | guardrails | vpw) and spending_profile (flat | smile)
  - existing plans get the new assumption keys at their defaults; nothing existing is overwritten
  - the fixed current_age assumption is removed (it defaulted to 30 and never advanced); the page asks
    for the birth date instead
Runs on an empty database (no tenant schemas: nothing to do).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005planv2"
down_revision: Union[str, None] = "0004nwbackfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of the v2 keys in app/services/plan_assumptions.py at the time of this migration:
# (key, display name, category, default, sensitivity, description)
NEW_ASSUMPTIONS = [
    ("rsu_hold_fraction", "RSU Kept as Company Stock", "career", 0.5, "medium",
     "Share of after-tax vested RSUs kept as company stock; the rest is sold into the taxable portfolio."),
    ("spending_floor", "Spending Floor", "spending", 0.75, "medium",
     "Guardrails and VPW only: a path counts as a failure when real spending falls below this share of the target."),
    ("commute_reduction", "Work Costs That Stop", "spending", 0.5, "low",
     "Share of commuting and transport spending that stops at retirement."),
    ("payoff_mortgage", "Pay Off the Mortgage at Retirement", "spending", 0, "low",
     "Pay the remaining mortgage from savings in the first retired year."),
    ("plan_to_age", "Plan to Age", "retirement", 95, "medium", "The money has to last to this age."),
    ("ss_monthly_at_fra", "Social Security at Full Age", "retirement", 0, "medium",
     "Monthly benefit at full retirement age in today's dollars, from ssa.gov/myaccount. 0 means not counted."),
    ("ss_claim_age", "Social Security Claim Age", "retirement", 67, "medium",
     "With a full retirement age of 67, claiming at 62 pays 70%; each year of delay to 70 adds 8%."),
    ("ss_payable_share", "Social Security Paid After 2034", "retirement", 1.0, "medium",
     "Share of scheduled benefits paid from 2034 (2025 Trustees Report: about 81% if Congress does not act)."),
    ("use_sepp", "Use 72(t) Payments Before 59½", "retirement", 0, "low",
     "Retiring before 55: substantially equal periodic payments from the 401(k) without the 10% penalty."),
    ("success_target", "Target Chance of Success", "retirement", 0.85, "low",
     "The bar 'what would need to be true' aims for."),
    ("health_people", "People Insured", "health", 1, "medium",
     "People the household buys health cover for in retirement."),
    ("aca_benchmark", "Pre-65 Premium per Person", "health", 15000, "medium",
     "Unsubsidised benchmark marketplace premium per person, today's dollars."),
    ("aca_income_cap", "Premium Cap (Share of Income)", "health", 0.0996, "low",
     "Below 400% of the poverty line the benchmark premium is capped at this share of MAGI."),
    ("medicare_cost", "Medicare-Age Health Cost per Person", "health", 8500, "medium",
     "Part B and D, Medigap and out-of-pocket per person per year from 65."),
    ("health_excess_inflation", "Health Cost Inflation Above CPI", "health", 0.02, "low",
     "Health costs grow at inflation plus this much a year."),
    ("stock_allocation_working", "Stocks While Working", "markets", 0.9, "medium",
     "Stock share of the portfolio while working."),
    ("stock_allocation_retired", "Stocks in Retirement", "markets", 0.6, "medium",
     "Stock share of the portfolio in retirement."),
    ("income_tax_rate", "Tax Rate on Pay", "tax", 0.3, "medium",
     "All-in effective rate on salary and part-time income (federal, state, FICA)."),
]
REMOVED_KEYS = ["current_age"]


def _tenant_schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"
    )).fetchall()]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS household_profile (
                id SERIAL PRIMARY KEY,
                birth_date DATE,
                updated_at TIMESTAMP DEFAULT now()
            )
        """))
        conn.execute(sa.text(
            "ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS spending_rule VARCHAR NOT NULL DEFAULT 'fixed'"
        ))
        conn.execute(sa.text(
            "ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS spending_profile VARCHAR NOT NULL DEFAULT 'flat'"
        ))
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS plan_events (
                id SERIAL PRIMARY KEY,
                plan_id INTEGER NOT NULL REFERENCES plan_versions(id) ON DELETE CASCADE,
                kind VARCHAR NOT NULL,
                label VARCHAR NOT NULL,
                start_age INTEGER NOT NULL,
                end_age INTEGER,
                amount NUMERIC NOT NULL DEFAULT 0,
                pct NUMERIC NOT NULL DEFAULT 0,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                params JSON,
                created_at TIMESTAMP DEFAULT now()
            )
        """))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_plan_events_plan_id ON plan_events (plan_id)"))
        for key, name, category, value, sensitivity, description in NEW_ASSUMPTIONS:
            conn.execute(sa.text("""
                INSERT INTO plan_assumptions (plan_id, key, display_name, category, value, description, sensitivity)
                SELECT pv.id, :key, :name, :category, :value, :description, :sensitivity
                FROM plan_versions pv
                WHERE NOT EXISTS (SELECT 1 FROM plan_assumptions pa WHERE pa.plan_id = pv.id AND pa.key = :key)
            """), {"key": key, "name": name, "category": category, "value": value,
                   "description": description, "sensitivity": sensitivity})
        conn.execute(sa.text("DELETE FROM plan_assumptions WHERE key = ANY(:keys)"), {"keys": REMOVED_KEYS})
    conn.execute(sa.text("SET search_path TO public"))


def downgrade() -> None:
    conn = op.get_bind()
    keys = [k for k, *_ in NEW_ASSUMPTIONS]
    for schema in _tenant_schemas(conn):
        conn.execute(sa.text(f'SET search_path TO "{schema}"'))
        conn.execute(sa.text("DROP TABLE IF EXISTS plan_events"))
        conn.execute(sa.text("DROP TABLE IF EXISTS household_profile"))
        conn.execute(sa.text("ALTER TABLE plan_versions DROP COLUMN IF EXISTS spending_rule"))
        conn.execute(sa.text("ALTER TABLE plan_versions DROP COLUMN IF EXISTS spending_profile"))
        conn.execute(sa.text("DELETE FROM plan_assumptions WHERE key = ANY(:keys)"), {"keys": keys})
        # current_age comes back at the old default so the v1 engine has an age again.
        conn.execute(sa.text("""
            INSERT INTO plan_assumptions (plan_id, key, display_name, category, value, description, sensitivity)
            SELECT pv.id, 'current_age', 'Current Age', 'career', 30, '', 'low' FROM plan_versions pv
            WHERE NOT EXISTS (SELECT 1 FROM plan_assumptions pa WHERE pa.plan_id = pv.id AND pa.key = 'current_age')
        """))
    conn.execute(sa.text("SET search_path TO public"))
