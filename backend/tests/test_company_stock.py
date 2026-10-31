"""LOOK-NW-004: vested company shares count in net worth and liquid net worth."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.investment import RSUGrant, VestEvent
from app.services import company_stock


def _grants(db):
    db.add_all([
        RSUGrant(id="g1", company="MSFT", symbol="MSFT", total_shares=200, sellable_shares=120, unvested_shares=50),
        RSUGrant(id="g2", company="MSFT", symbol="MSFT", total_shares=50, sellable_shares=30, unvested_shares=0),
    ])
    db.flush()
    db.add(VestEvent(grant_id="g1", vest_date=date(2026, 9, 15), vest_period=3, shares=60, shares_withheld=20,
                     shares_released=40, fmv_at_vest=Decimal("400"), is_actual=True))
    db.add(VestEvent(grant_id="g1", vest_date=date(2027, 3, 15), vest_period=4, shares=50, is_actual=False))
    db.commit()


def test_company_stock_is_sellable_shares_at_the_days_close_and_past_days_exclude_later_vests(db_session):
    _grants(db_session)
    company_stock.record_values(db_session, [(date(2026, 9, 1), 380.0), (date(2026, 10, 30), 400.0)], today=date(2026, 10, 30))
    db_session.commit()
    rows = {r.snapshot_date: float(r.balance) for r in db_session.query(BalanceSnapshot).filter_by(account_id="company-stock")}
    assert rows == {date(2026, 9, 1): (150 - 40) * 380.0, date(2026, 10, 30): 150 * 400.0}
    acct = db_session.get(Account, "company-stock")
    assert acct.display_group == "Company Stock" and acct.include_in_nw


def test_snapshot_counts_company_stock_in_net_worth_and_liquid_net_worth(client, db_session):
    _grants(db_session)
    db_session.add(Account(id="chk", name="Checking", account_type="cash", display_group="Cash", include_in_nw=True))
    db_session.add(BalanceSnapshot(account_id="chk", snapshot_date=date(2026, 10, 30), balance=Decimal("1000"), source="seed"))
    company_stock.record_values(db_session, [(date(2026, 10, 30), 400.0)], today=date(2026, 10, 30))
    db_session.commit()
    snap = client.get("/api/v1/snapshot").json()
    assert snap["net_worth"] == 61_000 and snap["liquid_net_worth"] == 61_000
    assert any(layer["name"] == "Company Stock" and layer["total"] == 60_000 for layer in snap["layers"])


def test_past_holdings_keep_each_grants_share_of_its_releases_when_shares_were_sold(db_session):
    """g1 released 100 shares and holds 25 (sold 75%), g2 released 40 and holds all 40, g3 sold everything."""
    db_session.add_all([
        RSUGrant(id="g1", company="MSFT", symbol="MSFT", total_shares=100, sellable_shares=25, unvested_shares=0),
        RSUGrant(id="g2", company="MSFT", symbol="MSFT", total_shares=40, sellable_shares=40, unvested_shares=0),
        RSUGrant(id="g3", company="MSFT", symbol="MSFT", total_shares=60, sellable_shares=0, unvested_shares=0),
    ])
    db_session.flush()
    for grant, day, released in [("g1", date(2026, 1, 15), 50), ("g1", date(2026, 7, 15), 50),
                                 ("g2", date(2026, 9, 15), 40), ("g3", date(2025, 6, 1), 60)]:
        db_session.add(VestEvent(grant_id=grant, vest_date=day, shares=released, shares_released=released,
                                 shares_withheld=0, is_actual=True))
    db_session.commit()

    held_on = company_stock.holdings(db_session, today=date(2026, 10, 30))
    assert held_on(date(2026, 10, 30)) == 65  # exactly today's sellable shares
    assert held_on(date(2026, 8, 1)) == 25    # g1 both releases at 25%, g2 not vested yet, g3 sold
    assert held_on(date(2026, 2, 1)) == 12.5  # g1's first release at 25%
    assert held_on(date(2025, 12, 31)) == 0   # g3's shares were sold: never counted


def test_rebuild_replaces_the_written_history(db_session, monkeypatch):
    from app.services import stock_price

    _grants(db_session)
    db_session.add(Account(id="chk", name="Checking", account_type="cash", display_group="Cash", include_in_nw=True))
    db_session.add(BalanceSnapshot(account_id="chk", snapshot_date=date(2026, 9, 1), balance=Decimal("1"), source="seed"))
    db_session.add(BalanceSnapshot(account_id="company-stock", snapshot_date=date(2026, 9, 7), balance=Decimal("999999"),
                                   source="company_stock"))
    db_session.commit()
    monkeypatch.setattr(stock_price, "price_series",
                        lambda db, symbol, range_, today=None: [{"date": "2026-09-07", "price": 390.0}])
    monkeypatch.setattr(stock_price, "get_or_fetch_price", lambda db, symbol: 400.0)

    assert company_stock.refresh(db_session, today=date(2026, 10, 30)) == 1  # history exists: only today
    company_stock.refresh(db_session, today=date(2026, 10, 30), rebuild=True)
    rows = {r.snapshot_date: float(r.balance) for r in db_session.query(BalanceSnapshot).filter_by(account_id="company-stock")}
    assert rows == {date(2026, 9, 7): 110 * 390.0, date(2026, 10, 30): 150 * 400.0}
