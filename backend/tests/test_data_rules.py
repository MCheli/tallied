"""One source of truth and one spending definition (PRODUCT.md): snapshots, spending rules, planning ages, seed dates."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.transaction import Transaction


def _account(db, id_, group="Cash", include=True, atype="cash"):
    db.add(Account(id=id_, name=id_, account_type=atype, display_group=group, include_in_nw=include, is_active=True))


def test_spending_excludes_transfers_and_loan_payments(client, db_session):
    _account(db_session, "chk")
    today = date.today()
    db_session.add_all([
        Transaction(id="t1", account_id="chk", date=today, amount=Decimal("-85"), merchant="Whole Foods", category="Groceries", source="test"),
        Transaction(id="t2", account_id="chk", date=today, amount=Decimal("-2450"), merchant="Bank", category="Transfer", source="test"),
        Transaction(id="t3", account_id="chk", date=today, amount=Decimal("-300"), merchant="Visa", category="Credit Card Payment", source="test"),
        Transaction(id="t4", account_id="chk", date=today, amount=Decimal("5000"), merchant="Employer", category="Paychecks", source="test"),
        Transaction(id="t5", account_id="chk", date=today, amount=Decimal("-12"), merchant="Cafe", category=None, source="test"),
    ])
    db_session.commit()
    cats = {c["category"]: c["total"] for c in client.get("/api/v1/spending/by-category").json()}
    assert cats == {"Groceries": -85.0, "Uncategorized": -12.0}
    trend = client.get("/api/v1/spending/monthly-trend").json()
    assert trend[0]["total"] == -97.0
    assert "Transfer" in client.get("/api/v1/spending/excluded-categories").json()


def test_recurring_lists_bills_not_habits(client, db_session):
    _account(db_session, "chk")
    rows = []

    def tx(key, d, amount, merchant, category):
        rows.append(Transaction(id=key, account_id="chk", date=d, amount=Decimal(str(amount)), merchant=merchant,
                                category=category, source="test"))

    for i in range(4):  # July to October
        d = date(2026, 7 + i, 5)
        tx(f"ph{i}a", d, -90, "Phone Co", "Phone")                       # two lines: still a bill
        tx(f"ph{i}b", d + timedelta(days=1), -85, "Phone Co", "Phone")
        tx(f"el{i}", d, -400 + 30 * i, "Power Co", "Gas & Electric")      # varies a little
        tx(f"mort{i}", d, -2450, "Bank", "Transfer")                     # never spending
        tx(f"old{i}", date(2026, 3 + i, 5), -9.99, "Old Stream", "Streaming")   # stopped in June
        for k in range(6):                                               # a habit, many charges a month
            tx(f"pk{i}{k}", d + timedelta(days=k), -44, "Garage", "Software & AI")
        tx(f"wf{i}a", d, -40, "Whole Foods", "Groceries")                # steady but a habit category
        tx(f"am{i}a", d, -12, "Online Store", "Electronics")             # amounts all over the place
        tx(f"am{i}b", d + timedelta(days=3), -300, "Online Store", "Electronics")
    db_session.add_all(rows)
    db_session.commit()
    res = client.get("/api/v1/spending/recurring", params={"from_date": "2026-03-01", "to_date": "2026-10-31"}).json()
    assert [r["merchant"] for r in res] == ["Power Co", "Phone Co"]
    assert res[1]["avg_monthly"] == 175.0 and res[1]["months_seen"] == 4      # what the bill costs a month
    assert res[0]["avg_monthly"] == 355.0                                       # 400, 370, 340, 310 over four months


def test_snapshot_dedupes_same_day_rows_and_reports_as_of(client, db_session):
    _account(db_session, "chk")
    _account(db_session, "ira", group="Retirement", atype="investment_401k")
    _account(db_session, "hidden", include=False)
    d = date(2026, 10, 1)
    db_session.add_all([
        BalanceSnapshot(account_id="chk", snapshot_date=d, balance=Decimal("1000"), source="seed"),
        BalanceSnapshot(account_id="chk", snapshot_date=d, balance=Decimal("1200"), source="simplefin"),  # same day, newer row wins
        BalanceSnapshot(account_id="ira", snapshot_date=date(2026, 9, 30), balance=Decimal("5000"), source="seed"),
        BalanceSnapshot(account_id="hidden", snapshot_date=d, balance=Decimal("999"), source="seed"),
        # a year ago
        BalanceSnapshot(account_id="chk", snapshot_date=d - timedelta(days=380), balance=Decimal("700"), source="seed"),
        BalanceSnapshot(account_id="ira", snapshot_date=d - timedelta(days=400), balance=Decimal("4000"), source="seed"),
    ])
    db_session.commit()
    snap = client.get("/api/v1/snapshot").json()
    assert snap["net_worth"] == 6200.0 and snap["liquid_net_worth"] == 1200.0
    assert snap["as_of"] == "2026-10-01"
    cash = next(l for l in snap["layers"] if l["name"] == "Cash")
    assert cash["total"] == 1200.0  # excluded account not in the layer total
    assert {a["id"]: a["include_in_nw"] for a in cash["accounts"]} == {"chk": True, "hidden": False}
    assert snap["net_worth_12mo_change"] == 6200.0 - 4700.0

    trend = client.get("/api/v1/trends/net-worth").json()
    assert trend["groups"]["Cash"][-1] == 1200.0  # not 2200
    assert "Retirement" in trend["groups"]


def test_plan_uses_its_own_age_and_keeps_labels_on_update(client, db_session):
    from tests.conftest import set_household_age

    set_household_age(client, 40)  # age comes from the household birth date, never a typed assumption
    res = client.post("/api/v1/plans/", json={"name": "Test", "scenario_type": "base", "assumptions": [
        {"key": "retirement_age", "value": 62},
    ]})
    assert res.status_code in (200, 201), res.text
    plan = res.json()
    ages = [p["age"] for p in plan["projections"]]
    assert ages[0] == 40
    labels = {a["key"]: a for a in plan["assumptions"]}
    assert labels["retirement_age"]["display_name"] == "Retirement Age" and labels["retirement_age"]["category"] == "career"

    table = client.get(f"/api/v1/plans/{plan['id']}/table").json()
    assert table["years"][-1] == date.today().year + (62 - 40)

    res = client.put(f"/api/v1/plans/{plan['id']}", json={"assumptions": [
        {"key": a["key"], "value": (65 if a["key"] == "retirement_age" else a["value"])} for a in plan["assumptions"]
    ]})
    assert res.status_code == 200, res.text
    updated = {a["key"]: a for a in res.json()["assumptions"]}
    assert updated["retirement_age"]["display_name"] == "Retirement Age"
    assert updated["retirement_age"]["category"] == "career"
    assert client.get(f"/api/v1/plans/{plan['id']}/table").json()["years"][-1] == date.today().year + 25


def test_price_history_validates_symbol(client):
    res = client.get("/api/v1/rsu/price-history", params={"symbol": "../etc", "range": "5y"})
    assert res.status_code == 400
    res = client.get("/api/v1/rsu/price-history", params={"symbol": "MSFT", "range": "99y"})
    assert res.status_code == 400


def test_price_history_prefers_stored_prices_and_survives_yahoo_failing(client, db_session, monkeypatch):
    from app.config import settings
    from app.models.investment import StockPrice
    from app.services import stock_price

    today = date.today()
    week = (today - timedelta(days=14)).isoformat()
    db_session.add_all([
        StockPrice(symbol="MSFT", price_date=today - timedelta(days=14), close_price=Decimal("410.00"), source="yahoo"),
        StockPrice(symbol="MSFT", price_date=today, close_price=Decimal("425.50"), source="yahoo"),
    ])
    db_session.commit()
    yahoo = [{"date": (today - timedelta(days=21)).isoformat(), "price": 400.0}, {"date": week, "price": 399.0}]
    monkeypatch.setattr(stock_price, "fetch_price_history", lambda symbol, range_: yahoo)

    pts = client.get("/api/v1/rsu/price-history", params={"symbol": "MSFT"}).json()["points"]
    assert [p["price"] for p in pts] == [400.0, 410.0, 425.5]  # stored wins on its day and ends the series
    assert pts[-1]["date"] == today.isoformat()

    def down(symbol, range_):
        raise ValueError("Yahoo Finance error: timeout")
    monkeypatch.setattr(stock_price, "fetch_price_history", down)
    assert [p["price"] for p in client.get("/api/v1/rsu/price-history").json()["points"]] == [410.0, 425.5]
    assert client.get("/api/v1/rsu/price-history", params={"symbol": "AAPL"}).status_code == 502  # nothing stored

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(stock_price, "fetch_price_history", lambda s, r: (_ for _ in ()).throw(AssertionError("fetched")))
    assert len(client.get("/api/v1/rsu/price-history").json()["points"]) == 2  # the demo never calls Yahoo


def test_property_valuation_writes_the_balance_snapshot(client, db_session):
    from app.models.property import Mortgage

    _account(db_session, "house", group="Home Equity", atype="real_estate")
    db_session.add(Mortgage(account_id="house", original_amount=Decimal("380000"), current_balance=Decimal("362450"),
                            rate=Decimal("0.0425"), monthly_payment=Decimal("2450")))
    db_session.commit()
    res = client.post("/api/v1/property/valuation", json={"value": 530000, "source": "Zillow", "valuation_date": "2026-10-15"})
    assert res.status_code == 200, res.text
    snap = db_session.query(BalanceSnapshot).filter_by(account_id="house").one()
    assert float(snap.balance) == 530000 and snap.source == "valuation" and snap.snapshot_date == date(2026, 10, 15)
    assert client.get("/api/v1/snapshot").json()["net_worth"] == 530000.0


def test_seed_months_ago_helper():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("seed", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "seed_test_data.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    d = seed._months_ago(14)
    assert d.day == 1
    delta_months = (date.today().year - d.year) * 12 + (date.today().month - d.month)
    assert delta_months == 14
    source = (pathlib.Path(__file__).resolve().parents[2] / "scripts" / "seed_test_data.py").read_text()
    assert "Roberts" not in source and "Ashland" not in source  # the persona's address only


def test_price_cache_keeps_seed_rows(db_session, monkeypatch):
    from app.models.investment import StockPrice
    from app.services import stock_price

    db_session.add(StockPrice(symbol="MSFT", price_date=date.today(), close_price=Decimal("95.50"), source="seed"))
    db_session.commit()
    monkeypatch.setattr(stock_price, "fetch_price", lambda symbol: 531.01)
    assert stock_price.get_or_fetch_price(db_session, "MSFT") == 95.5  # today's row wins, whatever wrote it
    rows = db_session.query(StockPrice).filter_by(symbol="MSFT", price_date=date.today()).all()
    assert {r.source: float(r.close_price) for r in rows} == {"seed": 95.5}
    db_session.add(StockPrice(symbol="AAPL", price_date=date.today() - timedelta(days=1), close_price=Decimal("1"), source="seed"))
    db_session.commit()
    assert stock_price.get_or_fetch_price(db_session, "AAPL") == 531.01  # no row for today: fetched and cached



def test_refunds_net_spending_but_income_does_not(client, db_session):
    _account(db_session, "card", group="Credit Cards", atype="credit_card")
    today = date.today()
    db_session.add_all([
        Transaction(id="r1", account_id="card", date=today, amount=Decimal("-250"), merchant="Car auction", category="Car Auctions", category_group="Auto & Transport", source="test"),
        Transaction(id="r2", account_id="card", date=today, amount=Decimal("250"), merchant="Car auction", category="Car Auctions", category_group="Auto & Transport", source="test"),
        Transaction(id="r3", account_id="card", date=today, amount=Decimal("-120"), merchant="Shop", category="Shopping", category_group="Shopping", source="test"),
        Transaction(id="r4", account_id="card", date=today, amount=Decimal("20"), merchant="Shop", category="Shopping", category_group="Shopping", source="test"),
        Transaction(id="r5", account_id="card", date=today, amount=Decimal("5000"), merchant="Employer", category="Paycheck", category_group="Income", source="test"),
        Transaction(id="r6", account_id="card", date=today, amount=Decimal("75"), merchant="Venmo", category=None, source="test"),
    ])
    db_session.commit()
    cats = {c["category"]: c["total"] for c in client.get("/api/v1/spending/by-category").json()}
    assert cats == {"Car Auctions": 0.0, "Shopping": -100.0}       # refunded deposit nets to zero; returns net
    assert client.get("/api/v1/spending/monthly-trend").json()[0]["total"] == -100.0


def test_cash_notable_transactions_are_cash_accounts_only(client, db_session):
    """CASH-NOTABLE-001: a card purchase does not move cash, and savings to checking is not a withdrawal."""
    _account(db_session, "chk")
    _account(db_session, "sav")
    db_session.add(Account(id="card", name="Card", account_type="credit_card", display_group="Credit Cards", include_in_nw=True))
    d = date.today()
    db_session.add_all([
        Transaction(id="w1", account_id="chk", date=d, amount=Decimal("-1500"), merchant="Rent", source="test"),
        Transaction(id="c1", account_id="card", date=d, amount=Decimal("-900"), merchant="Online Store", source="test"),
        Transaction(id="s1", account_id="sav", date=d, amount=Decimal("-5000"), merchant="Transfer to checking", source="test"),
        Transaction(id="s2", account_id="chk", date=d, amount=Decimal("5000"), merchant="Transfer from savings", source="test"),
    ])
    db_session.commit()
    res = client.get("/api/v1/transactions/large", params={"threshold": 500, "days": 30, "account_type": "cash"}).json()
    assert [t["id"] for t in res] == ["w1"]

