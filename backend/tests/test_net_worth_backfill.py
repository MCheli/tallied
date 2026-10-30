"""Decision D2 for data saved before D2: the house and the 401(k) count in net worth (NW-001)."""
from datetime import date
from decimal import Decimal

import pytest

from app.api.import_unified import CONTEXT_CONFIG, _record_retirement_balance
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.property import PropertyValuation
from app.models.retirement import RetirementAccount
from app.services.balances import backfill_asset_balances, ensure_retirement_account


def _setup_household(db):
    """Claudius-shaped data as it existed before D2: valuations and a 401(k) statement, no snapshots for either."""
    db.add_all([
        Account(id="chk", name="Checking", account_type="cash", display_group="Cash", include_in_nw=True, is_active=True),
        Account(id="house", name="456 Oak Street", account_type="real_estate", display_group="Home Equity", include_in_nw=True, is_active=True),
        Account(id="mortgage", name="Mortgage", account_type="loan_mortgage", display_group="Home Equity", include_in_nw=True, is_active=True),
    ])
    db.flush()
    db.add_all([
        BalanceSnapshot(account_id="chk", snapshot_date=date(2026, 10, 29), balance=Decimal("10000"), source="sync"),
        BalanceSnapshot(account_id="mortgage", snapshot_date=date(2026, 10, 29), balance=Decimal("-380000"), source="sync"),
        PropertyValuation(account_id="house", valuation_date=date(2026, 3, 22), value=Decimal("510000"), source="Realtor.com"),
        PropertyValuation(account_id="house", valuation_date=date(2026, 4, 4), value=Decimal("520000"), source="Realtor.com"),
        RetirementAccount(plan_name="MICROSOFT 401(K) PLAN", provider="Fidelity", total_balance=Decimal("95000"), statement_end=date(2025, 12, 31)),
    ])
    db.commit()


def test_backfill_puts_the_house_and_the_401k_into_net_worth(client, db_session):
    _setup_household(db_session)
    before = client.get("/api/v1/snapshot").json()["net_worth"]
    assert before == pytest.approx(10000 - 380000)

    counts = backfill_asset_balances(db_session)
    db_session.commit()
    assert counts == {"property": 1, "retirement": 1}

    after = client.get("/api/v1/snapshot").json()["net_worth"]
    assert after == pytest.approx(10000 - 380000 + 520000 + 95000)

    k401 = db_session.query(Account).filter_by(account_type="investment_401k").one()
    assert k401.display_group == "Retirement" and k401.include_in_nw
    assert db_session.query(RetirementAccount).one().account_id == k401.id


def test_backfill_is_idempotent_and_never_overrides_a_newer_balance(db_session):
    _setup_household(db_session)
    db_session.add(BalanceSnapshot(account_id="house", snapshot_date=date(2026, 5, 1), balance=Decimal("530000"), source="valuation"))
    db_session.commit()
    first = backfill_asset_balances(db_session)
    second = backfill_asset_balances(db_session)
    assert first == {"property": 0, "retirement": 1}
    assert second == {"property": 0, "retirement": 0}
    house = db_session.query(BalanceSnapshot).filter_by(account_id="house").all()
    assert [float(s.balance) for s in house] == [530000.0]


def test_existing_401k_account_is_reused_not_duplicated(db_session):
    db_session.add(Account(id="cb-401k", name="401k", account_type="investment_401k", display_group="Retirement", include_in_nw=True, is_active=True))
    ret = RetirementAccount(plan_name="Plan", total_balance=Decimal("1"))
    db_session.add(ret)
    db_session.flush()
    assert ensure_retirement_account(db_session, ret).id == "cb-401k"
    assert db_session.query(Account).filter_by(account_type="investment_401k").count() == 1


def test_401k_import_creates_the_account_instead_of_skipping(db_session):
    db_session.add(RetirementAccount(plan_name="Plan", total_balance=Decimal("1234.56"), statement_end=date(2026, 9, 30)))
    db_session.flush()
    _record_retirement_balance(db_session)
    db_session.flush()
    snap = db_session.query(BalanceSnapshot).one()
    assert float(snap.balance) == 1234.56 and snap.snapshot_date == date(2026, 9, 30)


def test_401k_import_without_a_balance_fails_loudly(db_session):
    db_session.add(RetirementAccount(plan_name="Plan", total_balance=None))
    db_session.flush()
    with pytest.raises(ValueError, match="net worth was not updated"):
        _record_retirement_balance(db_session)


def test_rsu_import_keeps_the_scheduled_quantity_on_future_vests():
    prompt = CONTEXT_CONFIG["rsu"]["prompt"]
    assert "scheduled Granted Qty." in prompt and "future periods" in prompt
