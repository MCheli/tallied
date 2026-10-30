"""Dashboard and Property agree with each other and with the lender (LOOK-NW-003)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant, VestEvent
from app.models.property import Mortgage, PropertyValuation
from app.services.compensation import comp_split


def _acct(db, id_, atype, group):
    db.add(Account(id=id_, name=id_, account_type=atype, display_group=group, include_in_nw=True, is_active=True))


def _snap(db, acct, d, bal, source="sync"):
    db.add(BalanceSnapshot(account_id=acct, snapshot_date=d, balance=Decimal(str(bal)), source=source))


def test_trend_carries_each_balance_forward_and_starts_when_the_picture_is_complete(client, db_session):
    _acct(db_session, "chk", "cash", "Cash")
    _acct(db_session, "house", "real_estate", "Home Equity")
    _acct(db_session, "mortgage", "loan_mortgage", "Home Equity")
    _acct(db_session, "k401", "investment_401k", "Retirement")
    _acct(db_session, "newcard", "credit_card", "Credit Cards")
    db_session.flush()
    _snap(db_session, "k401", date(2025, 12, 31), 300000, "statement")      # a statement from before the sync started
    _snap(db_session, "house", date(2026, 4, 4), 520000, "valuation")      # one valuation
    sync_days = [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 8, 31)]
    for d in sync_days:
        _snap(db_session, "chk", d, 10000)
        _snap(db_session, "mortgage", d, -380000)
    _snap(db_session, "k401", date(2026, 7, 1), 310000, "statement")
    _snap(db_session, "newcard", date(2026, 8, 31), -500)                   # opened recently: must not cut history
    db_session.commit()

    data = client.get("/api/v1/trends/net-worth").json()
    # Starts on the first day the established accounts all have a balance (the sync start), not
    # on the lone December statement where the house and mortgage were still missing.
    assert data["dates"] == [d.isoformat() for d in sync_days]
    base = 10000 + 520000 - 380000
    # No spikes: the house and the 401(k) count on every day at their last known value.
    assert data["totals"] == [base + 300000, base + 300000, base + 310000, base + 310000, base + 310000 - 500]
    assert data["groups"]["Home Equity"] == [140000.0] * 5


def test_property_equity_uses_the_synced_mortgage_balance_and_reports_escrow(client, db_session):
    _acct(db_session, "house", "real_estate", "Home Equity")
    _acct(db_session, "mortgage", "loan_mortgage", "Home Equity")
    db_session.flush()
    db_session.add(PropertyValuation(account_id="house", valuation_date=date(2026, 4, 4), value=Decimal("520000"), source="Realtor.com"))
    db_session.add(Mortgage(account_id="mortgage", rate=Decimal("0.0375"), monthly_payment=Decimal("3074.70"), escrow=Decimal("865.64"),
                            original_amount=Decimal("477000"), current_balance=Decimal("440688.82"), origination_date=date(2022, 4, 1)))
    _snap(db_session, "mortgage", date(2026, 10, 29), -434810.58)  # newer than the stale statement figure
    _snap(db_session, "house", date(2026, 4, 4), 520000, "valuation")  # what saving the valuation writes (D2)
    db_session.commit()

    s = client.get("/api/v1/property/summary").json()
    assert s["mortgage"]["balance"] == 434810.58
    assert s["equity"] == pytest.approx(520000 - 434810.58)
    assert s["mortgage"]["escrow"] == 865.64
    assert s["payment_breakdown"] == {"total": 3074.70, "principal": 850.28, "interest": 1358.78, "escrow": 865.64}
    snap = client.get("/api/v1/snapshot").json()
    home = next(layer for layer in snap["layers"] if layer["name"] == "Home Equity")
    assert home["total"] == pytest.approx(s["equity"])


def test_amortization_reproduces_the_lender_statement_and_ends_at_maturity(client, db_session):
    _acct(db_session, "mortgage", "loan_mortgage", "Home Equity")
    db_session.flush()
    db_session.add(Mortgage(account_id="mortgage", rate=Decimal("0.0375"), monthly_payment=Decimal("3074.70"), escrow=Decimal("865.64"),
                            original_amount=Decimal("477000"), current_balance=Decimal("434810.58"),
                            origination_date=date(2022, 4, 1), original_payoff_date=date(2052, 4, 1)))
    db_session.commit()
    data = client.get("/api/v1/property/amortization").json()
    rows = {r["date"]: r for r in data["schedule"]}
    oct_2026 = rows["2026-10-01"]
    assert (oct_2026["principal"], oct_2026["interest"], oct_2026["balance"]) == (847.63, 1361.43, 434810.58)
    assert data["schedule"][0]["date"] == "2022-05-01"
    assert data["summary"]["payoff_date"] == "2052-04-01"
    assert len(data["schedule"]) == 360


def test_comp_split_uses_the_w2_split_when_recorded(db_session):
    w2 = W2Record(tax_year=2025, gross_pay=Decimal("210000"), base_salary=Decimal("145000"), rsu_income=Decimal("65000"))
    db_session.add(w2)
    db_session.flush()
    split = comp_split(db_session, w2)
    assert (split.salary, split.rsu_income, split.source) == (145000.0, 65000.0, "w2")


def test_comp_split_derives_rsu_income_from_that_years_vests(client, db_session):
    db_session.add(RSUGrant(id="g1", company="MSFT", symbol="MSFT", total_shares=300))
    db_session.flush()
    db_session.add_all([
        VestEvent(grant_id="g1", vest_date=date(2025, 5, 15), vest_period=1, shares=100, fmv_at_vest=Decimal("400"), is_actual=True),
        VestEvent(grant_id="g1", vest_date=date(2025, 11, 15), vest_period=2, shares=50, fmv_at_vest=Decimal("420"), is_actual=True),
        VestEvent(grant_id="g1", vest_date=date(2024, 11, 15), vest_period=0, shares=10, fmv_at_vest=Decimal("300"), is_actual=True),
        VestEvent(grant_id="g1", vest_date=date(2026, 5, 15), vest_period=3, shares=150, fmv_at_vest=None, is_actual=False),
    ])
    db_session.add(W2Record(tax_year=2025, gross_pay=Decimal("250000")))
    db_session.commit()
    income = client.get("/api/v1/income/current").json()
    assert income["rsu_income"] == 100 * 400 + 50 * 420
    assert income["salary"] == 250000 - (100 * 400 + 50 * 420)
    assert income["source"] == "vests"
    assert client.get("/api/v1/snapshot").json()["total_comp_annual"] == 250000
