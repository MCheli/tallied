"""Core API endpoint tests."""


def test_health(client):
    """Health check returns ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_snapshot_empty(client):
    """Snapshot returns valid structure with empty DB."""
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "net_worth" in data
    assert "layers" in data


def test_snapshot_with_data(client, seeded_db):
    """Snapshot returns correct net worth with seeded data."""
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["net_worth"] == 30000.0  # 12000 + 18000


def test_income_history(client, seeded_db):
    """Income history returns W2 records."""
    response = client.get("/api/income/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data["w2_records"]) == 1
    assert data["w2_records"][0]["tax_year"] == 2025
    assert data["w2_records"][0]["gross_pay"] == 210000.0


def test_income_current(client, seeded_db):
    """Current income returns breakdown."""
    response = client.get("/api/income/current")
    assert response.status_code == 200
    data = response.json()
    assert data["salary"] == 145000.0
    assert data["rsu_income"] == 65000.0
    assert data["total_comp"] == 210000.0


def test_accounts_list(client, seeded_db):
    """Accounts list returns all accounts."""
    response = client.get("/api/accounts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_transactions_list(client, seeded_db):
    """Transactions list returns empty when no transactions."""
    response = client.get("/api/transactions/")
    assert response.status_code == 200


def test_spending_by_category(client, seeded_db):
    """Spending by category works with no data."""
    response = client.get("/api/spending/by-category")
    assert response.status_code == 200


def test_large_transactions(client, seeded_db):
    """Large transactions endpoint works."""
    response = client.get("/api/transactions/large?threshold=500&days=30")
    assert response.status_code == 200


def test_import_config(client):
    """Import config returns guidance for each context."""
    for context in ["income", "retirement", "property", "rsu", "general"]:
        response = client.get(f"/api/v1/import/config/{context}")
        assert response.status_code == 200
        data = response.json()
        assert "guidance" in data
        assert "examples" in data
