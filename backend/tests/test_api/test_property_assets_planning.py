"""Property amortization needs an origination date; depreciation ignores priceless vehicles; plan table shape."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.asset import Vehicle
from app.models.property import Mortgage


def test_amortization_without_origination_date_is_422(client, db_session):
    db_session.add(Account(id="house", name="House", account_type="real_estate", display_group="Home Equity", include_in_nw=True))
    db_session.add(Mortgage(account_id="house", original_amount=Decimal("380000"), current_balance=Decimal("362450"),
                            rate=Decimal("0.0425"), monthly_payment=Decimal("2450"), origination_date=None))
    db_session.commit()
    res = client.get("/api/v1/property/amortization")
    assert res.status_code == 422
    assert "origination date" in res.json()["detail"]


def test_amortization_starts_from_the_mortgage_origination(client, db_session):
    db_session.add(Account(id="house", name="House", account_type="real_estate", display_group="Home Equity", include_in_nw=True))
    db_session.add(Mortgage(account_id="house", original_amount=Decimal("380000"), current_balance=Decimal("362450"),
                            rate=Decimal("0.0425"), monthly_payment=Decimal("2450"), escrow=Decimal("450"),
                            origination_date=date(2021, 6, 15)))
    db_session.commit()
    res = client.get("/api/v1/property/amortization")
    assert res.status_code == 200
    body = res.json()
    assert body["schedule"][0]["date"] == "2021-07-01"
    assert body["schedule"][0]["escrow"] == 450.0


def test_depreciation_only_counts_vehicles_with_a_purchase_price(client, db_session):
    db_session.add_all([
        Vehicle(year=2019, make="Toyota", model="RAV4", purchase_price=Decimal("28500"), estimated_value=Decimal("22000")),
        Vehicle(year=2015, make="Honda", model="Civic", purchase_price=None, estimated_value=Decimal("8500")),
        Vehicle(year=2022, make="Ford", model="Bronco", purchase_price=Decimal("40000"), estimated_value=None),
    ])
    db_session.commit()
    body = client.get("/api/v1/assets/summary").json()
    assert body["total_value"] == 30500.0
    assert body["total_purchase_price"] == 68500.0
    assert body["total_depreciation"] == 6500.0  # only the RAV4 has both figures
    assert body["vehicles_with_purchase_price"] == 2


def test_plan_table_reports_retirement_year_and_no_savings_columns(client, born_30):
    res = client.post("/api/v1/plans/", json={"name": "T", "scenario_type": "base", "assumptions": [
        {"key": "retirement_age", "value": 60},
    ]})
    assert res.status_code in (200, 201), res.text
    table = client.get(f"/api/v1/plans/{res.json()['id']}/table").json()
    assert table["current_age"] == 30 and table["retirement_age"] == 60
    assert table["retirement_year"] == date.today().year + 30
    assert "expenses_annual" not in table["metrics"] and "savings_rate" not in table["metrics"]
    first_row = table["rows"][str(table["years"][0])]
    assert "expenses_annual" not in first_row


def test_fleet_value_history_puts_every_vehicle_on_every_date(client, db_session):
    """VEH-CHART-001: stacked series need a value on every date; a gap made the stacked areas jagged."""
    from app.models.asset_value_history import AssetValueHistory

    rav4 = Vehicle(year=2019, make="Toyota", model="RAV4")
    civic = Vehicle(year=2015, make="Honda", model="Civic")
    db_session.add_all([rav4, civic])
    db_session.flush()
    db_session.add_all([
        AssetValueHistory(vehicle_id=rav4.id, date=date(2022, 1, 1), value=Decimal("28000"), source="purchase", is_projected=False),
        AssetValueHistory(vehicle_id=rav4.id, date=date(2024, 1, 1), value=Decimal("24000"), source="ai_estimate", is_projected=False),
        AssetValueHistory(vehicle_id=rav4.id, date=date(2099, 1, 1), value=Decimal("1000"), source="ai_estimate", is_projected=True),
        AssetValueHistory(vehicle_id=civic.id, date=date(2023, 1, 1), value=Decimal("9000"), source="purchase", is_projected=False),
        AssetValueHistory(vehicle_id=civic.id, date=date(2024, 1, 1), value=Decimal("8500"), source="ai_estimate", is_projected=False),
    ])
    db_session.commit()
    body = client.get("/api/v1/assets/value-history/aggregate").json()
    assert body["dates"] == ["2022-01-01", "2022-12-31", "2023-01-01", "2024-01-01", "2099-01-01"]
    civic_series = body["vehicles"]["2015 Honda Civic"]
    assert civic_series == [0, 0, 9000, 8500, 8500]                       # not owned, step on purchase, held after
    rav4_series = body["vehicles"]["2019 Toyota RAV4"]
    assert None not in rav4_series and rav4_series[2] == 26000            # interpolated between its own points
    assert body["total"][3] == 32500
    assert body["is_projected"] == [False, False, False, False, True]
