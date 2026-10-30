"""SPEND-PACE-001 and RECAP-001: month-to-date spending pace and the weekly recap."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.investment import RSUGrant, StockPrice, VestEvent
from app.models.transaction import Transaction
from app.services.weekly_recap import last_completed_week, month_pace, weekly_recap

_n = 0


def _tx(db, d, amount, merchant="Shop", category="Shopping"):
    global _n
    _n += 1
    db.add(Transaction(id=f"t{_n}", account_id="chk", date=d, amount=Decimal(str(amount)), merchant=merchant,
                       category=category, is_recurring=False))


def _account(db):
    db.add(Account(id="chk", name="Checking", account_type="cash", display_group="Cash", include_in_nw=True))
    db.flush()


def test_month_pace_runs_this_month_to_today_against_all_of_last_month(db_session):
    _account(db_session)
    _tx(db_session, date(2026, 9, 1), -100)
    _tx(db_session, date(2026, 9, 30), -50)
    _tx(db_session, date(2026, 10, 2), -40)
    _tx(db_session, date(2026, 10, 2), 10)  # refund nets spending
    _tx(db_session, date(2026, 10, 3), -500, category="Transfer")  # never spending
    _tx(db_session, date(2026, 10, 3), 3000, "Payroll", "Paycheck")  # income is not a refund
    db_session.commit()

    pace = month_pace(db_session, date(2026, 10, 3))
    assert pace["month"] == "2026-10" and pace["last_month"] == "2026-09"
    assert pace["this_month"] == [0, 30, 30]
    assert len(pace["last_month_series"]) == 30 and pace["last_month_series"][0] == 100
    assert pace["last_month_total"] == 150
    assert pace["same_day_last_month"] == 100
    assert pace["days_in_month"] == 31


def test_month_pace_for_a_past_month_is_complete(db_session):
    _account(db_session)
    _tx(db_session, date(2026, 2, 28), -20)
    db_session.commit()
    pace = month_pace(db_session, date(2026, 10, 30), date(2026, 2, 10))
    assert len(pace["this_month"]) == 28 and pace["this_total"] == 20
    assert pace["same_day_last_month"] == 0  # Jan 28


def test_last_completed_week_is_sunday_to_saturday_before_today():
    assert last_completed_week(date(2026, 10, 30)) == date(2026, 10, 18)  # Friday → Oct 18–24
    assert last_completed_week(date(2026, 10, 25)) == date(2026, 10, 18)  # Sunday → the week just ended
    assert last_completed_week(date(2026, 10, 24)) == date(2026, 10, 11)  # Saturday is not over yet


def test_weekly_recap_compares_the_week_with_the_prior_four_and_looks_ahead(db_session):
    _account(db_session)
    db_session.add_all([
        BalanceSnapshot(account_id="chk", snapshot_date=date(2026, 10, 17), balance=Decimal("1000"), source="seed"),
        BalanceSnapshot(account_id="chk", snapshot_date=date(2026, 10, 24), balance=Decimal("1250"), source="seed"),
    ])
    # Prior four weeks: $400 of groceries in total → $100 a week
    for d in (date(2026, 9, 21), date(2026, 9, 28), date(2026, 10, 5), date(2026, 10, 12)):
        _tx(db_session, d, -100, "Market", "Groceries")
    # A monthly bill charged on the 30th for three months is due again on the 30th
    for d in (date(2026, 7, 30), date(2026, 8, 30), date(2026, 9, 30)):
        _tx(db_session, d, -60, "Phone Co", "Phone")
    # The week
    _tx(db_session, date(2026, 10, 18), -150, "Market", "Groceries")
    _tx(db_session, date(2026, 10, 20), -300, "Hardware", "Home Improvement")
    _tx(db_session, date(2026, 10, 21), -25, "Corner", None)
    _tx(db_session, date(2026, 10, 22), 3624.67, "Inc Payroll", "Paycheck")
    _tx(db_session, date(2026, 10, 23), -900, "Card", "Credit Card Payment")
    db_session.add(RSUGrant(id="g1", company="MSFT", symbol="MSFT", total_shares=100, sellable_shares=0, unvested_shares=100))
    db_session.flush()
    db_session.add_all([
        VestEvent(grant_id="g1", vest_date=date(2026, 10, 27), vest_period=1, shares=10, is_actual=False),
        VestEvent(grant_id="g1", vest_date=date(2026, 11, 15), vest_period=2, shares=5, is_actual=False),
        VestEvent(grant_id="g1", vest_date=date(2026, 12, 1), vest_period=3, shares=10, is_actual=False),
        StockPrice(symbol="MSFT", price_date=date(2026, 10, 24), close_price=Decimal("400")),
    ])
    db_session.commit()

    r = weekly_recap(db_session, date(2026, 10, 30))
    assert (r["week_start"], r["week_end"], r["complete"]) == ("2026-10-18", "2026-10-24", True)
    assert r["net_worth_change"] == 250
    assert r["spending"] == 475 and r["prior_weekly_avg"] == 100 + 15  # Sep 30 phone bill is in the prior four weeks
    assert r["transaction_count"] == 3 and r["uncategorized"] == 1
    assert r["income"] == 3624.67
    assert r["categories"][0] == {"category": "Home Improvement", "total": 300, "prior_avg": 0}
    assert {"category": "Groceries", "total": 150, "prior_avg": 100} in r["categories"]
    assert [x["merchant"] for x in r["largest"]] == ["Hardware", "Market", "Corner"]
    assert r["upcoming_bills"] == [{"merchant": "Phone Co", "category": "Phone", "date": "2026-10-30", "amount": 60}]
    # Vests look 30 days ahead (to Nov 23): Oct 27 and Nov 15, not Dec 1
    assert r["upcoming_vests"] == [{"date": "2026-10-27", "shares": 10, "est_value": 4000},
                                   {"date": "2026-11-15", "shares": 5, "est_value": 2000}]
    assert r["previous_week"] == "2026-10-11" and r["next_week"] is None
    assert r["headline"] == (
        "You spent $475, 313% more than your 4-week average of $115; the most went to Home Improvement ($300). "
        "Net worth rose $250. Next week: 1 bill (~$60). RSU vests Oct 27, Nov 15: 15 shares (~$6,000).")


def test_headline_for_an_empty_or_ordinary_week():
    from app.services.weekly_recap import headline
    empty = {"spending": 0, "prior_weekly_avg": 0, "categories": [], "net_worth_change": None,
             "upcoming_bills": [], "upcoming_vests": []}
    assert headline(empty) == "No spending this week."
    usual = {**empty, "spending": 118, "prior_weekly_avg": 115, "net_worth_change": -40,
             "categories": [{"category": "Groceries", "total": 80, "prior_avg": 70}]}
    assert headline(usual) == "You spent $118, about your usual week; the most went to Groceries ($80). Net worth fell $40."


def test_weekly_recap_any_day_picks_its_week_and_empty_data_is_zero(client):
    r = client.get("/api/v1/recap/weekly", params={"week_start": "2026-10-14"}).json()
    assert (r["week_start"], r["week_end"]) == ("2026-10-11", "2026-10-17")
    assert r["spending"] == 0 and r["net_worth_change"] is None and r["categories"] == []
    assert r["next_week"] is not None
    pace = client.get("/api/v1/recap/month-pace").json()
    assert pace["this_total"] == 0 and pace["last_month_total"] == 0


def test_recap_email_has_subject_html_and_text_with_the_vests(client, db_session):
    from app.services.recap_email import render

    r = {"week_start": "2026-09-27", "week_end": "2026-10-03", "spending": 1371.01, "prior_weekly_avg": 1411.67,
         "net_worth_change": 327.3, "net_worth_end": 750251.71, "income": 3624.67, "uncategorized": 0,
         "headline": "You spent $1,371, about your usual week.", "categories": [{"category": "Gas & Electric", "total": 378.97, "prior_avg": 109.29}],
         "largest": [{"date": "2026-10-01", "merchant": "Eversource <utility>", "category": "Gas & Electric", "amount": 378.97}],
         "upcoming_bills": [], "upcoming_vests": [{"date": "2026-11-15", "shares": 68, "est_value": 13246.4}]}
    mail = render(r, "https://money.example.com/")
    assert mail["subject"] == "Weekly recap Sep 27 – Oct 3, 2026: spent $1,371, net worth +$327"
    assert "RSU vest, 68 shares" in mail["html"] and "~$13,246" in mail["html"]
    assert "Eversource &lt;utility&gt;" in mail["html"]  # merchant names are escaped
    assert "https://money.example.com/recap?week=2026-09-27" in mail["html"]
    assert "Nov 15 RSU vest, 68 shares: ~$13,246" in mail["text"]

    res = client.get("/api/v1/recap/weekly/email", params={"week_start": "2026-10-20"})
    assert res.status_code == 200 and res.json()["subject"].startswith("Weekly recap Oct 18 – 24, 2026: spent $0")
