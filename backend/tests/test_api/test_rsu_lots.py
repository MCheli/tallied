"""RSU sell-today estimate: unallocated sellable shares are surfaced; tax rates come from settings (UND-RSU-002)."""
from datetime import date, timedelta
from decimal import Decimal


def _grant(db, gid, sellable, released_per_vest, vest_count=2):
    from app.models.investment import RSUGrant, VestEvent

    db.add(RSUGrant(id=gid, company="MSFT", symbol="MSFT", grant_date=date(2023, 5, 15), total_shares=300,
                    vested_shares=sum(released_per_vest), unvested_shares=0, sellable_shares=sellable))
    for i in range(vest_count):
        db.add(VestEvent(grant_id=gid, vest_period=i + 1, vest_date=date.today() - timedelta(days=400 + 365 * i),
                         shares=released_per_vest[i], shares_released=released_per_vest[i],
                         fmv_at_vest=Decimal("100"), is_actual=True))


def test_summary_reports_unallocated_sellable_shares_and_settings_rates(client, db_session, monkeypatch):
    from app.models.investment import StockPrice
    from app.config import settings

    _grant(db_session, "G-1", sellable=100, released_per_vest=[60, 40])      # fully matched to lots
    _grant(db_session, "G-2", sellable=170, released_per_vest=[40, 27])      # 103 sellable shares have no lot
    db_session.add(StockPrice(symbol="MSFT", price_date=date.today(), close_price=Decimal("200"), source="seed"))
    db_session.commit()
    monkeypatch.setattr(settings, "ltcg_rate", 0.2)
    monkeypatch.setattr(settings, "state_tax_rate", 0.09)

    res = client.get("/api/v1/rsu/summary")
    assert res.status_code == 200, res.text
    lots = res.json()["tax_lots"]
    assert lots["all"]["shares"] == 167
    assert lots["unallocated_sellable_shares"] == 103
    assert lots["assumed_rates"] == {"ltcg": 0.2, "stcg": 0.37, "state": 0.09}
    assert lots["lots"][0]["est_tax_rate"] == 0.29
    assert res.json()["symbol"] == "MSFT"
