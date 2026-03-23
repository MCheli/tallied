"""Tests for empty database state — all endpoints should return valid responses, not 500s.

Verifies that a brand new user with no financial data can load every page
without errors. This is the state a new Google SSO user is in after first login.
"""
import pytest


def test_snapshot_empty(client):
    res = client.get("/api/snapshot")
    assert res.status_code == 200
    data = res.json()
    assert data["net_worth"] == 0.0
    assert data["layers"] == []


def test_accounts_empty(client):
    res = client.get("/api/accounts/")
    assert res.status_code == 200
    assert res.json() == []


def test_transactions_empty(client):
    res = client.get("/api/transactions/?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_spending_by_category_empty(client):
    res = client.get("/api/spending/by-category")
    assert res.status_code == 200
    assert res.json() == []


def test_spending_recurring_empty(client):
    res = client.get("/api/spending/recurring")
    assert res.status_code == 200
    assert res.json() == []


def test_spending_monthly_trend_empty(client):
    res = client.get("/api/spending/monthly-trend")
    assert res.status_code == 200
    assert res.json() == []


def test_income_current_empty(client):
    """Should return zeros, not 404."""
    res = client.get("/api/income/current")
    assert res.status_code == 200
    data = res.json()
    assert data["salary"] == 0
    assert data["total_comp"] == 0


def test_income_history_empty(client):
    res = client.get("/api/income/history")
    assert res.status_code == 200
    data = res.json()
    assert data["w2_records"] == []


def test_rsu_summary_empty(client):
    res = client.get("/api/rsu/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["held_shares"] == 0
    assert data["held_value"] == 0


def test_rsu_grants_empty(client):
    res = client.get("/api/rsu/grants")
    assert res.status_code == 200
    data = res.json()
    assert data["grants"] == []


def test_retirement_summary_empty(client):
    res = client.get("/api/retirement/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["account"] is None
    assert data["holdings"] == []


def test_property_summary_empty(client):
    res = client.get("/api/property/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["property"] is None
    assert data["mortgage"] is None


def test_assets_summary_empty(client):
    res = client.get("/api/assets/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_value"] == 0
    assert data["vehicle_count"] == 0


def test_trends_net_worth_empty(client):
    res = client.get("/api/trends/net-worth")
    assert res.status_code == 200
    data = res.json()
    assert data["dates"] == []


def test_trends_balances_empty(client):
    res = client.get("/api/trends/balances")
    assert res.status_code == 200
    data = res.json()
    assert data["accounts"] == []


def test_trends_cash_flow_empty(client):
    res = client.get("/api/trends/cash-flow")
    assert res.status_code == 200
    data = res.json()
    assert data["months"] == []


def test_plans_empty(client):
    res = client.get("/api/plans/")
    assert res.status_code == 200
    assert res.json() == []


def test_plaid_links_empty(client):
    res = client.get("/api/plaid/links")
    assert res.status_code == 200
    assert res.json() == []


def test_transactions_large_empty(client):
    res = client.get("/api/transactions/large?threshold=500&days=30")
    assert res.status_code == 200
    assert res.json() == []
