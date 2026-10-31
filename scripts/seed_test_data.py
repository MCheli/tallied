"""
Seed the database with the Claudius Banks test household (the public demo and the dev fixture).

One simulation drives every table, so the pages agree with each other:

- Payroll: biweekly Microsoft paychecks (salary, 401(k) deferrals, benefits, withholding, the Social
  Security wage cap), from three tax years back to today. Each completed year becomes a W-2.
- RSUs: a hire grant plus an annual award each September, vesting quarterly over four years. Vests
  in the past are actual (FMV = the close that day, shares withheld for tax); later ones are scheduled.
  He sells 60 percent of each release and keeps the rest, so the vested shares held are known on
  every day and the company-stock balance history is written from them.
- Cash: every transaction is posted to a ledger (checking, savings, high-yield savings, two credit
  cards). Card statements are paid in full each month, surplus cash is swept to savings and the
  brokerage, and the balance snapshots are read from the ledger, so balances and transactions agree.
- Investments: the brokerage and the 401(k) follow one market index; the 401(k) gets each paycheck's
  deferrals and the employer match. Quarterly 401(k) statements come from the same numbers.
- House: the mortgage amortizes exactly as the Property page computes it; the house value moves
  from the purchase price to today's estimate and every valuation is also a balance.

All dates are relative to the day the seed runs (it is re-run nightly for the demo), and the random
draws are keyed by calendar date, so a given day's transactions are the same on every run.

Stock prices: daily MSFT closes from Yahoo Finance when reachable (the RSU page charts Yahoo's history,
so vest prices then match its chart); otherwise a deterministic synthetic path of similar shape.

Usage: python scripts/seed_test_data.py [--reset] [--offline]
  --reset:   Drop and recreate all tables first
  --offline: Do not fetch prices; use the synthetic path
"""
import calendar
import json
import math
import random
import sys
from datetime import date, timedelta
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
from app.models.property_value_history import PropertyValueHistory
from app.models.retirement import RetirementAccount, RetirementHolding, RetirementSnapshot
from app.models.tenant import Tenant, TenantMembership
from app.models.transaction import Transaction
from app.models.user import User
from app.services.tenant_service import PLATFORM_TABLES, create_tenant_schema, drop_tenant_schema

TENANT_SCHEMA = "tenant_claudius"
SYMBOL = "MSFT"

# ── The household's fixed facts ──────────────────────────────────────────────
SALARY_NOW = 145_000.00          # since the most recent 1 September (raises are each September)
RAISE = 0.04
HIRE_DATE = date(2020, 8, 10)
HOUSE_PURCHASE = (date(2021, 6, 15), 475_000.00)
HOUSE_VALUE_NOW = 520_000.00
MORTGAGE = {"original": 380_000.00, "rate": 0.0425, "years": 30, "origination": date(2021, 6, 15), "escrow": 795.00}
PRETAX_401K, ROTH_401K, MATCH = 0.07, 0.04, 0.50    # deferral rates; employer matches 50% of deferrals
SEC125_YEAR, TRANSIT_YEAR = 2_400.00, 900.00
FED_RATE, STATE_RATE = 0.155, 0.05                   # paycheck withholding on taxable wages
RSU_WITHHOLD = 0.35                                  # sell-to-cover: 22% federal + 5% MA + FICA
RSU_KEEP = 0.40                                      # share of each release he keeps (sells the rest)
SS_WAGE_BASE = {2022: 147_000, 2023: 160_200, 2024: 168_600, 2025: 176_100, 2026: 184_500}
HISTORY_MONTHS = 24                                  # transactions and balances run this far back


def _months_ago(n: int) -> date:
    """First day of the month n months before today."""
    today = date.today()
    y, m = today.year, today.month - n
    while m <= 0:
        y -= 1
        m += 12
    return date(y, m, 1)


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _day_rng(d: date, salt: int = 0) -> random.Random:
    """Randomness keyed by calendar date, so the same day always gets the same draws."""
    return random.Random(d.toordinal() * 31 + salt)


def _money(x: float) -> Decimal:
    return Decimal(str(round(x, 2)))


# ── Prices ───────────────────────────────────────────────────────────────────

def _synthetic_closes(start: date, today: date, p0: float, p1: float, vol: float, salt: int) -> dict[date, float]:
    """Business-day closes from p0 to p1: a random walk pinned at both ends (a Brownian bridge)."""
    days = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    days = [d for d in days if d.weekday() < 5] or [today]
    walk, w = [], 0.0
    for d in days:
        w += _day_rng(d, salt).gauss(0, vol)
        walk.append(w)
    n = max(1, len(days) - 1)
    drift = math.log(p1 / p0)
    return {d: round(p0 * math.exp(drift * i / n + walk[i] - walk[-1] * i / n), 2) for i, d in enumerate(days)}


def _stock_closes(start: date, today: date, offline: bool) -> tuple[dict[date, float], str]:
    if not offline:
        try:
            from app.services.stock_price import fetch_price_history
            pts = fetch_price_history(SYMBOL, "10y", "1d")
            closes = {date.fromisoformat(p["date"]): float(p["price"]) for p in pts}
            closes = {d: p for d, p in closes.items() if start <= d <= today}
            if len(closes) > 250 and min(closes) <= start + timedelta(days=10):
                return closes, "yahoo"
            print("  ⚠ Yahoo history too short; using the synthetic price path")
        except ValueError as e:
            print(f"  ⚠ Yahoo unavailable ({e}); using the synthetic price path")
    return _synthetic_closes(start, today, 205.0, 520.0, 0.016, salt=7), "seed"


def _price_on(closes: dict[date, float], sorted_days: list[date], d: date) -> float:
    """The close on d, or the last close before it."""
    import bisect
    i = bisect.bisect_right(sorted_days, d) - 1
    return closes[sorted_days[max(i, 0)]]


# ── Payroll ──────────────────────────────────────────────────────────────────

def _salary_on(d: date, today: date) -> float:
    last_sep1 = date(today.year if today >= date(today.year, 9, 1) else today.year - 1, 9, 1)
    steps = 0
    s = last_sep1
    while d < s:
        steps += 1
        s = date(s.year - 1, 9, 1)
    return SALARY_NOW / (1 + RAISE) ** steps


def _ss_base(year: int) -> float:
    if year in SS_WAGE_BASE:
        return SS_WAGE_BASE[year]
    last = max(SS_WAGE_BASE)
    return SS_WAGE_BASE[last] * 1.04 ** (year - last)


def _paydays(start: date, today: date) -> list[date]:
    """Every other Friday, aligned so the most recent complete Sunday–Saturday week has a payday."""
    days_since_saturday = (today.weekday() - 5) % 7 or 7
    anchor = today - timedelta(days=days_since_saturday + 1)   # Friday of the last completed week
    out, d = [], anchor
    while d >= start:
        out.append(d)
        d -= timedelta(days=14)
    d = anchor + timedelta(days=14)
    while d <= today:
        out.append(d)
        d += timedelta(days=14)
    return sorted(out)


def _run_payroll(paydays: list[date], vest_income: dict[date, float], today: date) -> list[dict]:
    """One dict per paycheck with every deduction; the SS wage base counts RSU vests as wages."""
    vest_by_year: dict[int, list[tuple[date, float]]] = {}
    for d, v in vest_income.items():
        vest_by_year.setdefault(d.year, []).append((d, v))
    out = []
    ytd_ss: dict[int, float] = {}
    ytd_med: dict[int, float] = {}
    counted_vests: set[date] = set()
    for pd in paydays:
        y = pd.year
        # RSU wages that vested by this payday count toward the year's SS and Medicare wages
        for vd, v in vest_by_year.get(y, []):
            if vd <= pd and vd not in counted_vests:
                counted_vests.add(vd)
                ytd_ss[y] = ytd_ss.get(y, 0.0) + v
                ytd_med[y] = ytd_med.get(y, 0.0) + v
        gross = _salary_on(pd, today) / 26
        pretax, roth = gross * PRETAX_401K, gross * ROTH_401K
        sec125, transit = SEC125_YEAR / 26, TRANSIT_YEAR / 26
        taxable = gross - pretax - sec125 - transit
        fica_wages = gross - sec125 - transit
        ss_room = max(0.0, _ss_base(y) - ytd_ss.get(y, 0.0))
        ss = 0.062 * min(fica_wages, ss_room)
        med_before = ytd_med.get(y, 0.0)
        medicare = 0.0145 * fica_wages + 0.009 * max(0.0, med_before + fica_wages - max(200_000, med_before))
        ytd_ss[y] = ytd_ss.get(y, 0.0) + fica_wages
        ytd_med[y] = med_before + fica_wages
        fed, state = taxable * FED_RATE, taxable * STATE_RATE
        net = gross - pretax - roth - sec125 - transit - fed - state - ss - medicare
        out.append({"date": pd, "gross": gross, "pretax": pretax, "roth": roth, "sec125": sec125,
                    "transit": transit, "fed": fed, "state": state, "ss": ss, "medicare": medicare,
                    "net": round(net, 2)})
    return out


# ── RSUs ─────────────────────────────────────────────────────────────────────

def _quarter_dates_after(d: date, n: int) -> list[date]:
    """n quarterly vest dates (15 Feb/May/Aug/Nov), starting at least 80 days after d."""
    first = d + timedelta(days=80)
    out = []
    y, m = first.year, first.month
    while len(out) < n:
        if m in (2, 5, 8, 11):
            v = date(y, m, 15)
            if v >= first:
                out.append(v)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _grants(today: date) -> list[tuple[str, date, float]]:
    """(id, grant date, award value in dollars): the hire grant, then one award each 15 September."""
    out = [("MSFT-HIRE-2020", date(2020, 8, 31), 60_000.0)]
    y = 2021
    while date(y, 9, 15) <= today:
        out.append((f"MSFT-SA-{y}", date(y, 9, 15), 35_000.0 + 10_000.0 * min(y - 2021, 3) + 5_000.0 * max(0, y - 2024)))
        y += 1
    return out


def seed(reset=False, offline=False):
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
    today = date.today()
    start = _months_ago(HISTORY_MONTHS)

    try:
        print("Seeding Claudius Banks test data...")

        # ── User + Tenant ──
        from app.services.passwords import hash_password
        user = User(
            email="claudius@tallied.dev",
            password_hash=hash_password("demo123"),
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
            Account(id="cb-checking", name="Checking (...4521)", institution="First National Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True, opened_date=date(2018, 7, 2)),
            Account(id="cb-savings", name="Savings (...8834)", institution="First National Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True, opened_date=date(2018, 7, 2)),
            Account(id="cb-hysa", name="High-Yield Savings (...2200)", institution="Ally Bank",
                    account_type="cash", display_group="Cash", include_in_nw=True, opened_date=date(2020, 11, 4)),
            Account(id="cb-credit", name="Visa Signature (...3391)", institution="Chase",
                    account_type="credit_card", display_group="Credit Cards", include_in_nw=True),
            Account(id="cb-amex", name="Blue Cash Preferred (...1007)", institution="American Express",
                    account_type="credit_card", display_group="Credit Cards", include_in_nw=True),
            Account(id="cb-brokerage", name="Individual Brokerage (...6612)", institution="Vanguard",
                    account_type="investment_stock", display_group="Investments", include_in_nw=True),
            Account(id="cb-property", name="456 Oak Street Springfield MA 01101",
                    account_type="real_estate", display_group="Home Equity", include_in_nw=True),
            Account(id="cb-mortgage", name="Mortgage (...9100)", institution="First National Bank",
                    account_type="loan_mortgage", display_group="Home Equity", include_in_nw=True,
                    opened_date=MORTGAGE["origination"]),
            Account(id="cb-401k", name="Microsoft 401(k) Plan", institution="Fidelity",
                    account_type="investment_401k", display_group="Retirement", include_in_nw=True),
        ]
        db.add_all(accounts)
        db.flush()
        print(f"  ✓ Accounts ({len(accounts)})")

        # ── Stock prices ──
        closes, price_source = _stock_closes(date(2020, 6, 1), today, offline)
        price_today = closes[max(closes)]
        closes[today] = price_today          # today's row is the price every page uses today
        price_days = sorted(closes)
        db.add_all(StockPrice(symbol=SYMBOL, price_date=d, close_price=_money(p), source=price_source if d != today else "seed")
                   for d, p in closes.items())
        db.flush()
        print(f"  ✓ Stock prices ({len(closes)} daily closes, {price_source}; today ${price_today:,.2f})")

        # ── RSU grants and vests ──
        vest_income: dict[date, float] = {}       # vest date -> taxable income (shares x FMV)
        kept_by_date: dict[date, int] = {}        # vest date -> shares kept after the sale
        sales: list[tuple[date, float]] = []      # (date, proceeds) of the shares sold at each vest
        n_vests = 0
        for gid, gdate, value in _grants(today):
            grant_price = _price_on(closes, price_days, gdate)
            total = round(value / grant_price)
            dates = _quarter_dates_after(gdate, 16)
            per = [total // 16 + (1 if i < total % 16 else 0) for i in range(16)]
            vested = sellable = 0
            for period, (vd, shares) in enumerate(zip(dates, per), start=1):
                actual = vd <= today
                ev = VestEvent(grant_id=gid, vest_date=vd, vest_period=period, shares=shares, is_actual=actual)
                if actual:
                    fmv = _price_on(closes, price_days, vd)
                    withheld = round(shares * RSU_WITHHOLD)
                    released = shares - withheld
                    # Everything held before the house purchase was sold for the down payment.
                    kept = 0 if vd < HOUSE_PURCHASE[0] else round(released * RSU_KEEP)
                    ev.fmv_at_vest = ev.vest_price = _money(fmv)
                    ev.shares_withheld, ev.shares_released = withheld, released
                    ev.total_taxes_paid = _money(withheld * fmv)
                    vest_income[vd] = vest_income.get(vd, 0.0) + shares * fmv
                    kept_by_date[vd] = kept_by_date.get(vd, 0) + kept
                    sale_day = vd + timedelta(days=3 if vd.weekday() < 3 else 5)
                    sales.append((sale_day, (released - kept) * _price_on(closes, price_days, sale_day)))
                    vested += shares
                    sellable += kept
                db.add(ev)
                n_vests += 1
            db.add(RSUGrant(id=gid, company="Microsoft", symbol=SYMBOL, grant_date=gdate, total_shares=total,
                            vested_shares=vested, unvested_shares=total - vested, sellable_shares=sellable,
                            share_price=_money(grant_price)))
        db.flush()
        print(f"  ✓ RSU grants ({len(_grants(today))}) + vest events ({n_vests})")

        # ── Payroll and W-2s ──
        first_w2_year = today.year - 3
        paychecks = _run_payroll(_paydays(date(first_w2_year, 1, 1), today), vest_income, today)
        for year in range(first_w2_year, today.year):
            pcs = [p for p in paychecks if p["date"].year == year]
            rsu = sum(v for d, v in vest_income.items() if d.year == year)
            base = sum(p["gross"] for p in pcs)
            pretax = sum(p["pretax"] for p in pcs)
            sec125 = sum(p["sec125"] for p in pcs)
            transit = sum(p["transit"] for p in pcs)
            fica_wages = base - sec125 - transit + rsu
            medicare_wages = fica_wages
            db.add(W2Record(
                tax_year=year,
                gross_pay=_money(base + rsu),
                w2_wages=_money(base + rsu - pretax - sec125 - transit),
                base_salary=_money(base),
                rsu_income=_money(rsu),
                federal_tax=_money(sum(p["fed"] for p in pcs) + 0.22 * rsu),
                state_tax=_money(sum(p["state"] for p in pcs) + STATE_RATE * rsu),
                social_security=_money(0.062 * min(fica_wages, _ss_base(year))),
                medicare=_money(0.0145 * medicare_wages + 0.009 * max(0.0, medicare_wages - 200_000)),
                pretax_401k=_money(pretax),
                roth_401k=_money(sum(p["roth"] for p in pcs)),
                cafeteria_125=_money(sec125),
                transit=_money(transit),
                employer_health=_money(8_600 * 1.05 ** (year - 2025)),
            ))
        db.flush()
        print(f"  ✓ W-2 records ({first_w2_year}-{today.year - 1})")

        # ── Mortgage schedule (the same arithmetic as GET /property/amortization) ──
        r = MORTGAGE["rate"] / 12
        n = MORTGAGE["years"] * 12
        p_and_i = round(MORTGAGE["original"] * r / (1 - (1 + r) ** -n), 2)
        payment = round(p_and_i + MORTGAGE["escrow"], 2)
        mortgage_after: list[tuple[date, float]] = []     # (month date, balance after that payment)
        bal, md = MORTGAGE["original"], MORTGAGE["origination"].replace(day=1)
        while bal > 0 and len(mortgage_after) < n:
            principal = min(payment - bal * r - MORTGAGE["escrow"], bal)
            bal -= principal
            md = _add_months(md, 1)
            mortgage_after.append((md, max(bal, 0.0)))

        def mortgage_balance(d: date) -> float:
            b = MORTGAGE["original"]
            for md_, bal_ in mortgage_after:
                if md_ > d:
                    break
                b = bal_
            return b

        mortgage_now = mortgage_balance(today)

        # ── House value: purchase price to today's estimate, with a little seasonality ──
        pdate, pprice = HOUSE_PURCHASE
        span_years = (today - pdate).days / 365.25

        def house_value(d: date) -> float:
            t = (d - pdate).days / 365.25
            trend = pprice * (HOUSE_VALUE_NOW / pprice) ** (t / span_years)
            season = 1 + 0.008 * math.sin((d.timetuple().tm_yday - 100) / 365.25 * 2 * math.pi)
            season_now = 1 + 0.008 * math.sin((today.timetuple().tm_yday - 100) / 365.25 * 2 * math.pi)
            return round(trend * season / season_now / 100) * 100

        # ── Market index for the brokerage and the 401(k): about 9% a year over the window ──
        index = _synthetic_closes(start - timedelta(days=7), today, 100.0, 100.0 * 1.09 ** (HISTORY_MONTHS / 12), 0.002, salt=11)
        index_days = sorted(index)

        def idx(d: date) -> float:
            return _price_on(index, index_days, d)

        # ── Transactions: one ledger for every cash and card account ──
        txns: list[dict] = []
        bal_of = {"cb-checking": 6_400.00, "cb-savings": 15_000.00, "cb-hysa": 16_500.00,
                  "cb-credit": -1_420.00, "cb-amex": -560.00}
        statement = {"cb-credit": -1_420.00, "cb-amex": -560.00}
        brokerage = 54_000.00
        k401 = {"pretax": 71_000.00, "roth": 31_500.00, "employer": 35_500.00}
        k401_contrib = {"employee": 0.0, "employer": 0.0, "roth": 0.0}
        k401_quarters: list[tuple[date, dict]] = []
        snapshots: dict[str, list[tuple[date, float]]] = {}
        counter = [0]

        def post(d: date, acct: str, amount: float, merchant: str, category: str, group: str,
                 recurring: bool = False, notes: str | None = None) -> None:
            counter[0] += 1
            amount = round(amount, 2)
            bal_of[acct] = round(bal_of[acct] + amount, 2)
            txns.append({"id": f"cb-txn-{counter[0]:05d}", "account_id": acct, "date": d, "amount": _money(amount),
                         "merchant": merchant, "category": category, "category_group": group,
                         "is_recurring": recurring, "notes": notes, "source": "seed"})

        def spend(d: date, acct: str, amount: float, merchant: str, category: str, group: str, recurring: bool = False):
            post(d, acct, -abs(amount), merchant, category, group, recurring)

        def transfer(d: date, src: str, dst: str | None, amount: float, out_label: str, in_label: str) -> None:
            post(d, src, -amount, out_label, "Transfer", "Transfers")
            if dst:
                post(d, dst, amount, in_label, "Transfer", "Transfers")

        paycheck_on = {p["date"]: p for p in paychecks}
        sale_on: dict[date, float] = {}
        for sd, proceeds in sales:
            sale_on[sd] = sale_on.get(sd, 0.0) + proceeds

        # One-off purchases, placed by days before today so the recent past always has some.
        one_offs = {
            300: [("cb-credit", 2_149.00, "Wayfair", "Furniture", "Home")],
            286: [("cb-credit", -180.00, "Wayfair", "Furniture", "Home")],          # price-adjustment refund
            150: [("cb-credit", 812.40, "Firestone Complete Auto Care", "Auto Maintenance", "Auto & Transport")],
            58: [("cb-credit", 1_299.99, "Best Buy", "Electronics", "Shopping")],
            44: [("cb-credit", -89.99, "Best Buy", "Electronics", "Shopping")],     # returned the laptop sleeve
            480: [("cb-checking", 1_850.00, "Bay State Heating & Cooling", "Home Services", "Home")],
            610: [("cb-credit", 1_240.65, "The Home Depot", "Home Improvement", "Home")],
            33: [("cb-credit", 486.20, "Lakeside Animal Hospital", "Pets", "Pets")],
            95: [("cb-credit", 640.00, "Ticketmaster", "Entertainment & Recreation", "Entertainment")],
        }

        restaurants = [("Chipotle", 15, 6), ("Panera Bread", 17, 5), ("Main Street Pizza", 32, 10),
                       ("Pho 99", 38, 8), ("Sakura Sushi", 64, 18), ("Riverside Grill", 78, 22),
                       ("Shake Shack", 24, 6), ("Olive Garden", 58, 15), ("Oak Street Tavern", 46, 14)]
        groceries = [("Big Y", 96, 30), ("Trader Joe's", 74, 20), ("Whole Foods Market", 88, 28)]

        d = start
        while d <= today:
            rng = _day_rng(d)
            dom, dow, month = d.day, d.weekday(), d.month
            last_dom = calendar.monthrange(d.year, month)[1]

            # Money in
            if d in paycheck_on:
                pc = paycheck_on[d]
                post(d, "cb-checking", pc["net"], "Microsoft Corp Payroll", "Paycheck", "Income",
                     notes=f"Gross {pc['gross']:,.2f}; 401(k) {pc['pretax'] + pc['roth']:,.2f}")
                emp = pc["pretax"] + pc["roth"]
                k401["pretax"] += pc["pretax"]
                k401["roth"] += pc["roth"]
                k401["employer"] += emp * MATCH
                k401_contrib["employee"] += emp
                k401_contrib["roth"] += pc["roth"]
                k401_contrib["employer"] += emp * MATCH
            if d in sale_on:
                post(d, "cb-checking", sale_on[d], "E*TRADE Securities - MSFT Sale", "Transfer", "Transfers",
                     notes="Proceeds from selling part of an RSU release")
            if dom == last_dom:
                post(d, "cb-hysa", bal_of["cb-hysa"] * 0.039 / 12, "Ally Bank Interest", "Interest", "Income")
                post(d, "cb-savings", bal_of["cb-savings"] * 0.005 / 12, "Interest Paid", "Interest", "Income")

            # Housing and bills
            if dom == 1:
                post(d, "cb-checking", -payment, "First National Bank Mortgage", "Mortgage Payment", "Transfers",
                     recurring=True, notes=f"P&I {p_and_i:,.2f} + escrow {MORTGAGE['escrow']:,.2f}")
                spend(d, "cb-checking", 50.00, "Springfield Food Bank", "Charity", "Gifts & Donations", True)
            if dom == 27:
                spend(d, "cb-credit", 11.99, "Spotify", "Streaming", "Entertainment", True)
            if dom == 5:
                spend(d, "cb-checking", 168.42, "GEICO", "Auto Insurance", "Auto & Transport", True)
            if dom == 7:
                spend(d, "cb-credit", 80.00, "Xfinity Internet", "Internet & Cable", "Bills & Utilities", True)
            if dom == 29 or (dom == last_dom and last_dom < 29):
                spend(d, "cb-credit", 2.99, "Apple iCloud+", "Streaming", "Entertainment", True)
            if dom == 10:
                spend(d, "cb-credit", round(68.40 + rng.choice([0, 0, 0, 12.99]), 2), "Chewy", "Pets", "Pets", True)
            if dom == 12:
                spend(d, "cb-credit", 15.49, "Netflix", "Streaming", "Entertainment", True)
            if dom == 28:
                spend(d, "cb-checking", 27.85, "Haven Life Insurance", "Life Insurance", "Insurance", True)
            if dom == 17:
                spend(d, "cb-credit", 24.99, "Planet Fitness", "Fitness", "Health & Wellness", True)
            if dom == 18:
                summer = 1.25 if month in (7, 8) else 1.0
                spend(d, "cb-checking", round(118 * summer * rng.uniform(0.92, 1.08), 2), "Eversource Electric",
                      "Gas & Electric", "Bills & Utilities", True)
            if dom == 19:
                spend(d, "cb-credit", 13.99, "Disney+", "Streaming", "Entertainment", True)
                heat = {12: 165, 1: 210, 2: 190, 3: 140, 11: 110, 4: 85, 10: 60}.get(month, 34)
                spend(d, "cb-checking", round(heat * rng.uniform(0.9, 1.1), 2), "Columbia Gas", "Gas & Electric",
                      "Bills & Utilities")
            if dom == 22:
                spend(d, "cb-credit", 92.40, "Verizon Wireless", "Phone", "Bills & Utilities", True)
            if dom == 24 and month in (1, 4, 7, 10):
                spend(d, "cb-checking", round(rng.uniform(148, 176), 2), "Springfield Water & Sewer", "Water",
                      "Bills & Utilities")
            if dow == 3 and (d.toordinal() // 7) % 2 == 0:
                spend(d, "cb-checking", 165.00, "BrightHome Cleaning", "Home Services", "Home")
            if dom == 26:
                spend(d, "cb-credit", round(rng.uniform(18, 34), 2), "E-ZPass MA", "Tolls", "Auto & Transport")
            if dom == 15 and month == 2:
                spend(d, "cb-checking", 212.50, "City of Springfield Excise Tax", "Taxes", "Taxes")
                spend(d, "cb-checking", 78.75, "City of Springfield Excise Tax", "Taxes", "Taxes")
            if dom == 20 and month == 3:
                spend(d, "cb-credit", 139.00, "Amazon Prime", "Shopping", "Shopping")

            # Everyday spending
            if rng.random() < (0.14 if dow < 5 else 0.36):
                m, base, sd = rng.choice(groceries)
                spend(d, "cb-amex", max(18, rng.gauss(base, sd)), m, "Groceries", "Food & Dining")
            if dow == 5 and rng.random() < 0.38:
                spend(d, "cb-amex", max(70, rng.gauss(195, 50)), "Costco Wholesale", "Groceries", "Food & Dining")
            if rng.random() < (0.26 if dow < 4 else 0.62):
                m, base, sd = rng.choice(restaurants)
                spend(d, "cb-credit", max(9, rng.gauss(base, sd)), m, "Restaurants", "Food & Dining")
            if dow < 5 and rng.random() < 0.35:
                spend(d, "cb-credit", round(rng.uniform(4.2, 9.8), 2), rng.choice(["Starbucks", "Dunkin'"]),
                      "Coffee Shops", "Food & Dining")
            if rng.random() < 0.09:
                spend(d, "cb-credit", round(rng.uniform(24, 58), 2), "DoorDash", "Food Delivery", "Food & Dining")
            if rng.random() < 0.13:
                spend(d, "cb-amex", round(rng.uniform(38, 62), 2), rng.choice(["Shell", "Mobil", "Cumberland Farms"]),
                      "Gas", "Auto & Transport")
            if rng.random() < 0.21:
                spend(d, "cb-credit", round(max(8, rng.gauss(52, 30)), 2), "Amazon", "Shopping", "Shopping")
            if rng.random() < 0.025:
                post(d, "cb-credit", round(rng.uniform(19, 75), 2), "Amazon", "Shopping", "Shopping",
                     notes="Return")
            if rng.random() < 0.07:
                spend(d, "cb-credit", round(max(15, rng.gauss(68, 30)), 2), "Target", "Shopping", "Shopping")
            if rng.random() < (0.05 if month in (11, 12, 1, 2) else 0.11):
                spend(d, "cb-credit", round(max(12, rng.gauss(88, 55)), 2), rng.choice(["The Home Depot", "Lowe's"]),
                      "Home Improvement", "Home")
            if rng.random() < 0.045:
                spend(d, "cb-credit", round(rng.uniform(22, 190), 2),
                      rng.choice(["Uniqlo", "Nordstrom Rack", "REI", "Old Navy", "L.L.Bean", "Gap"]),
                      "Clothing", "Shopping")
            if rng.random() < 0.05:
                spend(d, "cb-credit", round(rng.uniform(12, 36), 2), rng.choice(["Uber", "Lyft"]),
                      "Taxi & Rideshare", "Auto & Transport")
            if rng.random() < 0.05:
                spend(d, "cb-credit", round(rng.uniform(9, 42), 2), "CVS Pharmacy", "Pharmacy", "Health & Wellness")
            if rng.random() < 0.04:
                spend(d, "cb-credit", round(rng.uniform(14, 70), 2),
                      rng.choice(["AMC Theatres", "Steam", "Springfield Thunderbirds", "Barnes & Noble"]),
                      "Entertainment & Recreation", "Entertainment")
            if dom == 8 + (month % 3) * 7:
                spend(d, "cb-credit", 36.00 + rng.choice([0, 6]), "Great Clips", "Personal Care", "Personal")
            if month in (11, 12) and dom <= 22 and rng.random() < 0.18:
                spend(d, "cb-credit", round(rng.uniform(25, 140), 2), rng.choice(["Amazon", "Target", "Etsy", "Macy's"]),
                      "Gifts", "Gifts & Donations")

            # Seasonal and periodic costs
            if (month, dom) in ((3, 11), (9, 16)):
                spend(d, "cb-credit", 185.00, "Springfield Dental Associates", "Dentist", "Health & Wellness")
            if (month, dom) == (5, 6):
                spend(d, "cb-credit", 420.00, "GreenScape Lawn & Landscape", "Lawn & Garden", "Home")
            if (month, dom) == (10, 9):
                spend(d, "cb-checking", 189.00, "Bay State Heating & Cooling", "Home Services", "Home")
            if (month, dom) in ((1, 20), (7, 13)):
                spend(d, "cb-credit", round(rng.uniform(160, 240), 2), "Lakeside Animal Hospital", "Pets", "Pets")
            if (month, dom) in ((1, 9), (4, 11), (7, 9), (10, 14)):
                spend(d, "cb-credit", round(rng.uniform(72, 96), 2), "Jiffy Lube", "Auto Maintenance", "Auto & Transport")
            # Trips: a February ski weekend, Memorial Day on the Cape, an August flight away, Thanksgiving home
            trips = {
                (2, 14): [("cb-credit", 640.00, "Green Mountain Ski Lodge", "Hotels", "Travel"),
                          ("cb-credit", 298.00, "Mountain Lift Tickets", "Entertainment & Recreation", "Entertainment")],
                (5, 26): [("cb-credit", 912.00, "Airbnb", "Travel", "Travel")],
                (6, 10): [("cb-credit", 784.60, "Delta Air Lines", "Travel", "Travel")],
                (8, 16): [("cb-credit", 1_368.20, "Marriott Hotels", "Hotels", "Travel"),
                          ("cb-credit", 412.75, "Hertz Rent-A-Car", "Travel", "Travel")],
                (9, 28): [("cb-credit", 462.40, "JetBlue Airways", "Travel", "Travel")],
                (4, 18): [("cb-credit", 186.00, "Amtrak", "Travel", "Travel")],
                (4, 20): [("cb-credit", 694.30, "Hilton New York Midtown", "Hotels", "Travel")],
                (10, 12): [("cb-credit", 528.90, "Hampton Inn Bar Harbor", "Hotels", "Travel")],
                (12, 21): [("cb-credit", 395.80, "JetBlue Airways", "Travel", "Travel")],
            }
            for acct, amt, merchant, cat, grp in trips.get((month, dom), []):
                spend(d, acct, amt, merchant, cat, grp)
            for acct, amt, merchant, cat, grp in one_offs.get((today - d).days, []):
                post(d, acct, -amt, merchant, cat, grp)

            # Card statements close (Chase on the 3rd, Amex on the 12th) and are paid in full later
            if dom == 3:
                statement["cb-credit"] = bal_of["cb-credit"]
            if dom == 12:
                statement["cb-amex"] = bal_of["cb-amex"]
            if dom == 25 and statement["cb-credit"] < 0:
                amt = -statement["cb-credit"]
                post(d, "cb-checking", -amt, "Chase Card Autopay", "Credit Card Payment", "Transfers")
                post(d, "cb-credit", amt, "Payment Thank You - Web", "Credit Card Payment", "Transfers")
                statement["cb-credit"] = 0.0
            if dom == 2 and statement["cb-amex"] < 0:
                amt = -statement["cb-amex"]
                post(d, "cb-checking", -amt, "American Express ACH Pmt", "Credit Card Payment", "Transfers")
                post(d, "cb-amex", amt, "Payment Received - Thank You", "Credit Card Payment", "Transfers")
                statement["cb-amex"] = 0.0

            # Savings: $400 to the brokerage each month, and what checking holds above $7,000 is swept out
            if dom == 4:
                transfer(d, "cb-checking", None, 400.00, "Vanguard Automatic Investment", "")
                brokerage += 400.00
            if dom == 28 and bal_of["cb-checking"] > 7_500:
                sweep = math.floor((bal_of["cb-checking"] - 7_000) / 100) * 100
                to_hysa = math.floor(sweep * 0.6 / 100) * 100
                transfer(d, "cb-checking", "cb-hysa", to_hysa, "Transfer to Ally Savings", "Transfer from Checking")
                if sweep - to_hysa > 0:
                    transfer(d, "cb-checking", None, sweep - to_hysa, "Transfer to Vanguard", "")
                    brokerage += sweep - to_hysa
            if bal_of["cb-checking"] < 1_500:
                top_up = math.ceil((4_000 - bal_of["cb-checking"]) / 500) * 500
                transfer(d, "cb-hysa", "cb-checking", top_up, "Transfer to Checking", "Transfer from Ally Savings")

            # Markets move the brokerage and the 401(k)
            prev = d - timedelta(days=1)
            move = idx(d) / idx(prev)
            brokerage *= move
            k401 = {k: v * (move * 0.85 + 0.15) for k, v in k401.items()}   # 85% stock / 15% bond funds
            if d.month in (3, 6, 9, 12) and dom == last_dom:
                k401_quarters.append((d, dict(k401)))

            # Snapshots each Saturday (the recap's weeks end on Saturday) and today
            if dow == 5 or d == today:
                for acct in ("cb-checking", "cb-savings", "cb-hysa", "cb-credit", "cb-amex"):
                    snapshots.setdefault(acct, []).append((d, bal_of[acct]))
                snapshots.setdefault("cb-brokerage", []).append((d, brokerage))
                snapshots.setdefault("cb-401k", []).append((d, sum(k401.values())))
                snapshots.setdefault("cb-mortgage", []).append((d, -mortgage_balance(d)))
            d += timedelta(days=1)

        db.bulk_insert_mappings(Transaction, txns)
        db.flush()
        print(f"  ✓ Transactions ({len(txns)})")

        # ── Mortgage ──
        db.add(Mortgage(
            account_id="cb-mortgage",
            rate=Decimal(str(MORTGAGE["rate"])),
            monthly_payment=_money(payment),
            escrow=_money(MORTGAGE["escrow"]),
            original_amount=_money(MORTGAGE["original"]),
            current_balance=_money(mortgage_now),
            origination_date=MORTGAGE["origination"],
            original_payoff_date=_add_months(MORTGAGE["origination"].replace(day=1), n),
            property_address="456 Oak Street, Springfield, MA 01101",
        ))
        db.flush()
        print(f"  ✓ Mortgage (balance ${mortgage_now:,.2f}, payment ${payment:,.2f})")

        # ── Property: valuations (monthly estimates + today) and the purchase ──
        val_dates = sorted({_add_months(start, i) for i in range(HISTORY_MONTHS + 1)} | {today})
        val_dates = [vd for vd in val_dates if vd <= today]
        for vd in val_dates:
            db.add(PropertyValuation(account_id="cb-property", valuation_date=vd, value=_money(house_value(vd)),
                                     source="Realtor.com estimate"))
            db.add(PropertyValueHistory(account_id="cb-property", date=vd, value=_money(house_value(vd)),
                                        source="realtor_estimate", is_projected=False))
        db.add(PropertyValueHistory(account_id="cb-property", date=pdate, value=_money(pprice), source="sale",
                                    is_projected=False, details=json.dumps({"note": "Purchase (closing statement)"})))
        # Earlier estimates each quarter back to the purchase, so the value line runs from the sale to today.
        qd = _add_months(pdate.replace(day=1), 3)
        while qd < start:
            db.add(PropertyValueHistory(account_id="cb-property", date=qd, value=_money(house_value(qd)),
                                        source="realtor_estimate", is_projected=False))
            qd = _add_months(qd, 3)
        db.flush()
        prop_snaps = []
        for sd, _ in snapshots["cb-mortgage"]:
            latest = max(vd for vd in val_dates if vd <= sd) if any(vd <= sd for vd in val_dates) else val_dates[0]
            prop_snaps.append((sd, house_value(latest)))
        snapshots["cb-property"] = prop_snaps
        print(f"  ✓ Property valuations ({len(val_dates)}) + value history")

        # ── Balance snapshots ──
        snap_rows = [
            {"account_id": acct, "snapshot_date": sd, "balance": _money(v), "source": "seed"}
            for acct, rows in snapshots.items() for sd, v in rows
        ]
        # Company stock: the vested shares he holds on each day x that day's close (services/company_stock.py
        # writes today's figure the same way: sellable shares x today's price).
        from app.services.company_stock import ACCOUNT_ID as CS_ACCOUNT
        from app.services.company_stock import SOURCE as CS_SOURCE
        from app.services.company_stock import _account as cs_account
        cs_account(db, SYMBOL)
        for sd, _ in snapshots["cb-checking"]:
            held = sum(k for vd, k in kept_by_date.items() if vd <= sd)
            snap_rows.append({"account_id": CS_ACCOUNT, "snapshot_date": sd,
                              "balance": _money(held * _price_on(closes, price_days, sd)), "source": CS_SOURCE})
        db.bulk_insert_mappings(BalanceSnapshot, snap_rows)
        db.flush()
        print(f"  ✓ Balance snapshots ({len(snap_rows)}, weekly from {start})")

        # ── 401(k): quarterly statements, the latest one as the account, holdings ──
        # Statements before the simulated window are walked back at ~2% a quarter less contributions.
        quarters = list(k401_quarters)
        first_q, first_bal = (quarters[0] if quarters else (today, dict(k401)))
        back = []
        q_date, q_bal = first_q, dict(first_bal)
        for _ in range(6):
            q_date = _add_months(q_date.replace(day=1), -3)
            q_date = q_date.replace(day=calendar.monthrange(q_date.year, q_date.month)[1])
            q_bal = {"pretax": (q_bal["pretax"] - 2_300) / 1.02, "roth": (q_bal["roth"] - 1_150) / 1.02,
                     "employer": (q_bal["employer"] - 1_720) / 1.02}
            back.append((q_date, dict(q_bal)))
        quarters = sorted(back) + quarters
        stmt_end, stmt = quarters[-1]
        stmt_total = sum(stmt.values())
        ret = RetirementAccount(
            plan_name="Microsoft Corporation 401(k) Plan", provider="Fidelity Investments", account_id="cb-401k",
            total_balance=_money(stmt_total), vested_balance=_money(stmt_total),
            roth_balance=_money(stmt["roth"]), pretax_balance=_money(stmt["pretax"]),
            employer_match_balance=_money(stmt["employer"]),
            pretax_deferral_rate=Decimal(str(PRETAX_401K)), roth_deferral_rate=Decimal(str(ROTH_401K)),
            total_employee_contributions=_money(78_400 + k401_contrib["employee"]),
            total_employer_contributions=_money(36_900 + k401_contrib["employer"]),
            roth_basis=_money(24_600 + k401_contrib["roth"]),
            account_return=Decimal(str(round(idx(stmt_end) / idx(date(stmt_end.year, 1, 1)) * 0.85 + 0.15 - 1, 4)))
            if date(stmt_end.year, 1, 1) >= start else Decimal("0.0712"),
            return_period_start=date(stmt_end.year, 1, 1),
            statement_start=_add_months(stmt_end.replace(day=1), -2),
            statement_end=stmt_end,
            estimated_monthly_income=_money(round(stmt_total * 0.026, -1)),
        )
        db.add(ret)
        db.flush()
        for qd, qb in quarters:
            db.add(RetirementSnapshot(retirement_account_id=ret.id, snapshot_date=qd, balance=_money(sum(qb.values())),
                                      roth_balance=_money(qb["roth"]), pretax_balance=_money(qb["pretax"]),
                                      employer_balance=_money(qb["employer"]), source="statement"))
        basis = 78_400 + 36_900 + k401_contrib["employee"] + k401_contrib["employer"]
        funds = [("Fidelity 500 Index Fund", "FXAIX", 0.55), ("Fidelity Mid Cap Index Fund", "FSMDX", 0.10),
                 ("Fidelity Total International Index Fund", "FTIHX", 0.20), ("Fidelity U.S. Bond Index Fund", "FXNAX", 0.15)]
        gain_weight = {"FXAIX": 1.25, "FSMDX": 1.0, "FTIHX": 0.7, "FXNAX": 0.15}
        total_gain = stmt_total - basis
        norm = sum(w * gain_weight[t] for _, t, w in funds)
        for name, ticker, w in funds:
            db.add(RetirementHolding(retirement_account_id=ret.id, fund_name=name, ticker=ticker,
                                     balance=_money(stmt_total * w), allocation_pct=Decimal(str(w)),
                                     gain_loss=_money(total_gain * w * gain_weight[ticker] / norm)))
        db.flush()
        print(f"  ✓ 401(k) account + {len(funds)} holdings + {len(quarters)} statements (latest {stmt_end})")

        # ── Vehicles: the owner's own estimate, with a value line from purchase to today ──
        from app.services.valuation import store_vehicle_valuation
        cars = [
            (Vehicle(year=2019, make="Toyota", model="RAV4", trim="XLE AWD", mileage=58_400, condition="good",
                     purchase_price=Decimal("29800"), purchase_date=date(2019, 8, 15)), 21_400, 9.0,
                     "Owner's estimate from recent private-party listings for a 2019 RAV4 XLE AWD with about 58,000 miles in good condition."),
            (Vehicle(year=2015, make="Honda", model="Civic", trim="LX", mileage=112_300, condition="fair",
                     purchase_price=Decimal("13500"), purchase_date=date(2017, 6, 3)), 8_900, 8.0,
                     "Owner's estimate: a 2015 Civic LX with 112,000 miles and some door dings; private-party value."),
        ]
        for v, value, dep, note in cars:
            db.add(v)
            db.flush()
            store_vehicle_valuation(db, v, value=value, annual_depreciation_pct=dep, reasoning=note,
                                    source="manual", model=None, confidence=None, today=today)
        db.flush()
        print("  ✓ Vehicles (2) + value history")

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

        db.commit()
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
    seed(reset="--reset" in sys.argv, offline="--offline" in sys.argv)
