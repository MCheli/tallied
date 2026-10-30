"""
Seed the database with Claudius Banks test data.

Creates a complete financial picture for the test persona including:
- Accounts (checking, savings, credit cards, mortgage, property, retirement, brokerage)
- Balance snapshots (monthly history)
- W2 records (2023-2025)
- Transactions (generated)
- Mortgage record
- Property valuation
- RSU grants and vest events
- Retirement account
- Vehicles

Usage: python scripts/seed_test_data.py [--reset]
  --reset: Drop and recreate all tables first
"""
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# Import all models to register them
import app.models  # noqa
from app.database import Base, SessionLocal, engine
from app.models.account import Account
from app.models.asset import Vehicle
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant, StockPrice, VestEvent
from app.models.planning import PlanProjection
from app.models.property import Mortgage, PropertyValuation
from app.models.retirement import RetirementAccount, RetirementHolding, RetirementSnapshot
from app.models.tenant import Tenant, TenantMembership
from app.models.transaction import Transaction
from app.models.user import User
from app.services.tenant_service import PLATFORM_TABLES, create_tenant_schema, drop_tenant_schema

TENANT_SCHEMA = "tenant_claudius"


MORTGAGE_CURRENT_BALANCE = 362450.75


def _months_ago(n: int) -> date:
    """First day of the month n months before today."""
    today = date.today()
    y, m = today.year, today.month - n
    while m <= 0:
        y -= 1
        m += 12
    return date(y, m, 1)


def seed(reset=False):
    if reset:
        print("Resetting database...")
        # Drop tenant schema first
        drop_tenant_schema(TENANT_SCHEMA)
        Base.metadata.drop_all(bind=engine)
        # Recreate only platform tables in public
        platform_tables = [t for t in Base.metadata.sorted_tables if t.name in PLATFORM_TABLES]
        Base.metadata.create_all(bind=engine, tables=platform_tables)
        _stamp_alembic_head()

    db = SessionLocal()

    try:
        print("Seeding Claudius Banks test data...")

        # ── User + Tenant ──
        import hashlib
        user = User(
            email="claudius@tallied.dev",
            password_hash=hashlib.sha256(b"demo123").hexdigest(),
            display_name="Claudius Banks",
            auth_provider="local",
        )
        db.add(user)
        db.flush()

        tenant = Tenant(
            slug=TENANT_SCHEMA,
            display_name="Claudius's Finances",
            schema_name=TENANT_SCHEMA,
        )
        db.add(tenant)
        db.flush()

        db.add(TenantMembership(
            user_id=user.id,
            tenant_id=tenant.id,
            role="owner",
            is_default=True,
        ))
        db.flush()
        print("  ✓ User + Tenant")

        # Create tenant schema with all financial tables
        create_tenant_schema(TENANT_SCHEMA)

        # Switch the session to the tenant schema for all financial data. The listener
        # re-applies search_path after every commit (the pool checkout hook resets it).
        from app.services.tenant_service import attach_tenant_search_path
        attach_tenant_search_path(db, TENANT_SCHEMA)

        # ── Accounts ──
        accounts = [
            Account(id="cb-checking", name="Checking Account (...4521)", institution="First National Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True),
            Account(id="cb-savings", name="Savings Account (...8834)", institution="First National Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True),
            Account(id="cb-hysa", name="High-Yield Savings (...2200)", institution="Ally Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True),
            Account(id="cb-credit", name="Visa Signature (...3391)", institution="Chase",
                    account_type="credit_card", display_group="Credit Cards", include_in_nw=True),
            Account(id="cb-brokerage", name="Microsoft Brokerage", institution="E-Trade",
                    account_type="investment_stock", display_group="Investments", include_in_nw=True),
            Account(id="cb-property", name="456 Oak Street Springfield MA 01101",
                    account_type="real_estate", display_group="Home Equity", include_in_nw=True),
            Account(id="cb-mortgage", name="MORTGAGE LOAN (...9100)", institution="First National Bank",
                    account_type="loan_mortgage", display_group="Home Equity", include_in_nw=True),
            Account(id="cb-401k", name="MICROSOFT 401(K) PLAN", institution="Fidelity",
                    account_type="investment_401k", display_group="Retirement", include_in_nw=True),
        ]
        for a in accounts:
            if not db.get(Account, a.id):
                db.add(a)
        db.flush()
        print("  ✓ Accounts (8)")

        # ── Balance Snapshots (monthly, 14 months) ──
        snap_count = 0
        # Dates are relative to today so every "last N months" default has data (FEED-005 / D3).
        base_date = _months_ago(14)
        balances = {
            "cb-checking": 10000, "cb-savings": 15000, "cb-hysa": 5000,
            "cb-credit": -800, "cb-brokerage": 45000, "cb-property": 520000,
            "cb-mortgage": -380000, "cb-401k": 160000,
        }

        for month_offset in range(15):
            snap_date = date(base_date.year + (base_date.month + month_offset - 1) // 12,
                           (base_date.month + month_offset - 1) % 12 + 1, 1)
            for acct_id, base_bal in balances.items():
                # Add some variation
                noise = random.uniform(-0.03, 0.05)
                bal = base_bal * (1 + noise * (month_offset / 12))
                if acct_id == "cb-mortgage":
                    # Paying down toward the mortgage statement balance (the two must agree, D2)
                    bal = -MORTGAGE_CURRENT_BALANCE - (14 - month_offset) * 850
                elif acct_id == "cb-401k":
                    bal = base_bal * (1 + 0.01 * month_offset)  # Growing
                elif acct_id == "cb-brokerage":
                    bal = base_bal * (1 + 0.008 * month_offset + random.uniform(-0.02, 0.03))

                db.add(BalanceSnapshot(
                    account_id=acct_id, snapshot_date=snap_date,
                    balance=Decimal(str(round(bal, 2))), source="seed",
                ))
                snap_count += 1
        db.flush()
        print(f"  ✓ Balance snapshots ({snap_count})")

        # ── Transactions (generated, ~100 per month) ──
        txn_count = 0
        merchants = [
            ("Whole Foods", "Groceries", -85), ("Trader Joe's", "Groceries", -65),
            ("Shell Gas", "Gas", -55), ("Starbucks", "Coffee Shops", -6),
            ("Amazon", "Shopping", -45), ("Netflix", "Entertainment & Recreation", -15),
            ("Spotify", "Entertainment & Recreation", -10), ("AT&T", "Phone", -85),
            ("Eversource", "Gas & Electric", -120), ("Comcast", "Internet & Cable", -80),
            ("Target", "Shopping", -35), ("CVS", "Medical", -25),
            ("Uber", "Auto & Transport", -18), ("DoorDash", "Restaurants & Bars", -28),
        ]

        for month_offset in range(15):
            month_date = base_date + timedelta(days=month_offset * 30)
            if month_date > date.today():
                break
            # Paycheck (2x/month)
            for pay_day in [1, 15]:
                d = month_date.replace(day=min(pay_day, 28))
                db.add(Transaction(
                    id=f"cb-txn-pay-{month_offset}-{pay_day}",
                    account_id="cb-checking", date=d,
                    amount=Decimal("5576.92"), merchant="Microsoft",
                    category="Paychecks", source="seed",
                ))
                txn_count += 1

            # Regular expenses
            for i, (merchant, category, avg_amount) in enumerate(merchants):
                for occurrence in range(random.randint(1, 3)):
                    d = month_date + timedelta(days=random.randint(0, 28))
                    amount = avg_amount * random.uniform(0.7, 1.3)
                    db.add(Transaction(
                        id=f"cb-txn-{month_offset}-{i}-{occurrence}",
                        account_id="cb-checking", date=d,
                        amount=Decimal(str(round(amount, 2))),
                        merchant=merchant, category=category, source="seed",
                    ))
                    txn_count += 1

            # Mortgage payment
            d = month_date.replace(day=1)
            db.add(Transaction(
                id=f"cb-txn-mortgage-{month_offset}",
                account_id="cb-checking", date=d,
                amount=Decimal("-2450.00"), merchant="First National Bank",
                category="Transfer", source="seed",
            ))
            txn_count += 1

        db.flush()
        print(f"  ✓ Transactions ({txn_count})")

        # ── W2 Records ──
        INCOME = {
            2023: {"gross_pay": 185432.50, "base_salary": 130000.00, "rsu_income": 55432.50,
                   "federal_tax": 32450.00, "state_tax": 8950.00, "social_security": 9932.40,
                   "medicare": 2688.77, "pretax_401k": 8500.00, "roth_401k": 4500.00,
                   "cafeteria_125": 2100.00, "transit": 780.00, "employer_health": 7800.00},
            2024: {"gross_pay": 198750.00, "base_salary": 138000.00, "rsu_income": 60750.00,
                   "federal_tax": 35200.00, "state_tax": 9800.00, "social_security": 10453.20,
                   "medicare": 2881.88, "pretax_401k": 9200.00, "roth_401k": 4800.00,
                   "cafeteria_125": 2200.00, "transit": 840.00, "employer_health": 8200.00},
            2025: {"gross_pay": 210000.00, "base_salary": 145000.00, "rsu_income": 65000.00,
                   "federal_tax": 38500.00, "state_tax": 10400.00, "social_security": 10918.20,
                   "medicare": 3045.00, "pretax_401k": 10000.00, "roth_401k": 5000.00,
                   "cafeteria_125": 2300.00, "transit": 900.00, "employer_health": 8600.00},
        }
        for year, data in INCOME.items():
            existing = db.query(W2Record).filter(W2Record.tax_year == year).first()
            if existing:
                continue
            db.add(W2Record(
                tax_year=year,
                gross_pay=Decimal(str(data["gross_pay"])),
                base_salary=Decimal(str(data["base_salary"])),
                rsu_income=Decimal(str(data["rsu_income"])),
                federal_tax=Decimal(str(data["federal_tax"])),
                state_tax=Decimal(str(data["state_tax"])),
                social_security=Decimal(str(data["social_security"])),
                medicare=Decimal(str(data["medicare"])),
                pretax_401k=Decimal(str(data["pretax_401k"])),
                roth_401k=Decimal(str(data["roth_401k"])),
                cafeteria_125=Decimal(str(data["cafeteria_125"])),
                transit=Decimal(str(data["transit"])),
                employer_health=Decimal(str(data["employer_health"])),
            ))
        db.flush()
        print("  ✓ W2 records (2023-2025)")

        # ── Mortgage ──
        M = {"rate": 4.25, "monthly_payment": 2450.00, "escrow": 450.00,
             "original_amount": 380000.00, "current_balance": MORTGAGE_CURRENT_BALANCE}
        db.add(Mortgage(
            account_id="cb-mortgage",
            rate=Decimal(str(M["rate"] / 100)),
            monthly_payment=Decimal(str(M["monthly_payment"])),
            escrow=Decimal(str(M["escrow"])),
            original_amount=Decimal(str(M["original_amount"])),
            current_balance=Decimal(str(M["current_balance"])),
            origination_date=date(2021, 6, 15),
            original_payoff_date=date(2051, 6, 1),
            property_address="456 Oak Street, Springfield, MA 01101",
        ))
        db.flush()
        print("  ✓ Mortgage")

        # ── Property Valuation ──
        db.add(PropertyValuation(
            account_id="cb-property",
            valuation_date=date.today(),
            value=Decimal("520000"),
            source="Zillow Estimate",
        ))
        db.flush()
        print("  ✓ Property valuation")

        # ── RSU Grants ──
        grants = [
            ("MSFT-001", date(2022, 5, 15), 200, 150, 50),
            ("MSFT-002", date(2023, 5, 15), 180, 120, 60),
            ("MSFT-003", date(2023, 11, 15), 150, 100, 50),
            ("MSFT-004", date(2024, 5, 15), 160, 53, 107),
            ("MSFT-005", date(2024, 11, 20), 200, 200, 0),
            ("MSFT-006", date(2025, 5, 15), 220, 0, 220),
            ("MSFT-007", date(2025, 11, 19), 180, 0, 180),
            ("MSFT-008", date(2025, 11, 20), 250, 250, 0),
        ]

        for gid, gdate, total, vested, unvested in grants:
            db.add(RSUGrant(
                id=gid, company="Microsoft", symbol="MSFT",
                grant_date=gdate, total_shares=total,
                vested_shares=vested, unvested_shares=unvested,
                sellable_shares=max(0, vested - 30),
                share_price=Decimal("95.50"),
            ))

            # Add vest events (3-year annual vest)
            for period in range(1, 4):
                vest_date = date(gdate.year + period, gdate.month, min(gdate.day, 28))
                shares = total // 3 + (1 if period <= total % 3 else 0)
                is_actual = vest_date <= date.today()
                fmv = Decimal(str(random.uniform(80, 110))) if is_actual else None

                db.add(VestEvent(
                    grant_id=gid, vest_date=vest_date, vest_period=period,
                    shares=shares, fmv_at_vest=fmv,
                    shares_withheld=int(shares * 0.37) if is_actual else None,
                    shares_released=shares if is_actual else None,
                    total_taxes_paid=Decimal(str(round(float(fmv or 0) * shares * 0.37, 2))) if is_actual else None,
                    is_actual=is_actual, vest_price=fmv,
                ))
        db.flush()
        print("  ✓ RSU grants (8) + vest events")

        # ── Stock Price ──
        db.add(StockPrice(
            symbol="MSFT", price_date=date.today(),
            close_price=Decimal("95.50"), source="seed",
        ))
        db.flush()
        print("  ✓ Stock price (MSFT)")

        # ── Retirement Account ──
        R = {"plan_name": "MICROSOFT CORPORATION 401(K) PLAN", "provider": "Fidelity Investments",
             "total_balance": 185432.50, "vested_balance": 185432.50, "roth_balance": 129802.75,
             "pretax_balance": 18543.25, "employer_match_balance": 37086.50,
             "pretax_deferral_rate": 10, "roth_deferral_rate": 2, "roth_basis": 85000.00,
             "account_return_pct": 12.3, "employee_contributions_lifetime": 42000.00,
             "employer_contributions_lifetime": 12500.00, "estimated_monthly_income": 4520,
             "statement_start": "2025-10-01", "statement_end": "2025-12-31",
             "fund_name": "Fidelity Freedom 2055 Fund", "fund_ticker": "FDEEX",
             "fund_gain_loss": 5432.50}
        db.add(RetirementAccount(
            plan_name=R["plan_name"], provider=R["provider"],
            total_balance=Decimal(str(R["total_balance"])),
            vested_balance=Decimal(str(R["vested_balance"])),
            roth_balance=Decimal(str(R["roth_balance"])),
            pretax_balance=Decimal(str(R["pretax_balance"])),
            employer_match_balance=Decimal(str(R["employer_match_balance"])),
            pretax_deferral_rate=Decimal(str(R["pretax_deferral_rate"] / 100)),
            roth_deferral_rate=Decimal(str(R["roth_deferral_rate"] / 100)),
            total_employee_contributions=Decimal(str(R["employee_contributions_lifetime"])),
            total_employer_contributions=Decimal(str(R["employer_contributions_lifetime"])),
            roth_basis=Decimal(str(R["roth_basis"])),
            account_return=Decimal(str(R["account_return_pct"] / 100)),
            estimated_monthly_income=Decimal(str(R["estimated_monthly_income"])),
            statement_start=date.fromisoformat(R["statement_start"]),
            statement_end=date.fromisoformat(R["statement_end"]),
            return_period_start=date(2022, 1, 1),
        ))
        db.flush()

        # Retirement holding
        db.add(RetirementHolding(
            retirement_account_id=1,
            fund_name=R["fund_name"], ticker=R["fund_ticker"],
            balance=Decimal(str(R["total_balance"])),
            allocation_pct=Decimal("1.0"),
            gain_loss=Decimal(str(R["fund_gain_loss"])),
        ))

        # Retirement snapshot
        db.add(RetirementSnapshot(
            retirement_account_id=1,
            snapshot_date=date.fromisoformat(R["statement_end"]),
            balance=Decimal(str(R["total_balance"])),
            roth_balance=Decimal(str(R["roth_balance"])),
            pretax_balance=Decimal(str(R["pretax_balance"])),
            employer_balance=Decimal(str(R["employer_match_balance"])),
            source="seed",
        ))
        db.flush()
        print("  ✓ Retirement account + holdings + snapshot")

        # ── Vehicles ──
        db.add(Vehicle(
            year=2019, make="Toyota", model="RAV4", trim="XLE",
            mileage=45000, condition="good",
            purchase_price=Decimal("28500"), purchase_date=date(2019, 8, 15),
            estimated_value=Decimal("22000"),
            value_last_updated=datetime.now(),
        ))
        db.add(Vehicle(
            year=2015, make="Honda", model="Civic", trim="LX",
            mileage=98000, condition="fair",
            purchase_price=Decimal("18200"), purchase_date=date(2015, 3, 20),
            estimated_value=Decimal("8500"),
            value_last_updated=datetime.now(),
        ))
        db.flush()
        print("  ✓ Vehicles (2)")

        # ── Planning Scenario ──
        # Every key in the one vocabulary (app/services/plan_assumptions.py) at its default, with
        # Claudius's own values on top. His birth date (1 January, 30 years ago) keeps him 30 all year.
        from app.models.planning import HouseholdProfile
        from app.schemas.planning import AssumptionInput
        from app.services.plan_assumptions import ASSUMPTIONS
        from app.services.planning_service import add_event, create_plan

        db.add(HouseholdProfile(birth_date=date(date.today().year - 30, 1, 1)))
        db.flush()
        claudius = {
            "retirement_age": 55, "rsu_pct_of_comp": 0.31, "monthly_cash_savings": 1500,
            "retirement_spending": 60000, "ss_monthly_at_fra": 2800, "ss_claim_age": 67,
        }
        # Go through the service so projections are computed the same way the API does.
        plan = create_plan(
            db,
            name="Retire at 55",
            description="Base retirement scenario",
            scenario_type="base",
            assumptions_input=[
                AssumptionInput(key=a["key"], value=claudius.get(a["key"], a["value"]), display_name=a["display_name"],
                                category=a["category"], sensitivity=a["sensitivity"], description=a["description"])
                for a in ASSUMPTIONS
            ],
            spending_rule="guardrails",
        )
        # Health cover before and after 65 is modelled by the plan itself (marketplace, then Medicare).
        add_event(db, plan.id, {"kind": "layoff", "label": "Layoff, back to work in 6 months", "start_age": 36,
                                "params": {"severance_weeks": 8, "gap_months": 6, "next_pay_pct": 0.9, "next_equity": 1}})
        add_event(db, plan.id, {"kind": "part_time", "label": "Part-time consulting", "start_age": 55,
                                "end_age": 58, "amount": 40000, "pct": 0})
        add_event(db, plan.id, {"kind": "recurring_expense", "label": "College", "start_age": 48,
                                "end_age": 51, "amount": 35000, "pct": 0, "enabled": False})
        n_proj = db.query(PlanProjection).filter_by(plan_id=plan.id).count()
        if n_proj:
            print(f"  ✓ Plan + {n_proj} projection rows")
        else:
            print("  ⚠ Plan saved but projections are empty (engine raised; see planning_service.create_plan)")

        # Seed schema descriptions (COMMENT ON) for the tenant schema
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "seed_schema_descriptions",
            Path(__file__).parent / "seed_schema_descriptions.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.seed_descriptions(TENANT_SCHEMA)

        print()
        print("✅ Claudius Banks test data seeded successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


def _stamp_alembic_head():
    """Record that the freshly built database matches the migration head."""
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.stamp(cfg, "head")
    print("  ✓ alembic stamped at head")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    seed(reset=reset)
