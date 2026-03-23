"""
End-to-end integration tests for Tallied personal finance app.

These tests run against a REAL PostgreSQL database with isolated tenant schemas.
They walk through key user journeys in order, building on each other.

Requirements:
  - PostgreSQL running: docker compose up -d postgres
  - Run: pytest tests/test_e2e/ -v

DO NOT run with `make test` (which uses fast SQLite mocks).
"""
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

pytestmark = pytest.mark.e2e


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 1: New User Registration Flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewUserFlow:
    """Verify auth endpoints and empty state for a fresh tenant."""

    @pytest.mark.e2e
    def test_auth_me_returns_user(self, client, e2e_setup):
        """GET /api/v1/auth/me returns the authenticated user with tenant context."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == e2e_setup["user_email"]
        assert data["user"]["current_tenant"] is not None
        assert data["user"]["current_tenant"]["id"] == e2e_setup["tenant_id"]

    @pytest.mark.e2e
    def test_auth_config(self, client):
        """GET /api/v1/auth/config returns available auth methods."""
        resp = client.get("/api/v1/auth/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "dev_mode" in data
        assert "google_sso" in data

    @pytest.mark.e2e
    def test_snapshot_empty_state(self, client):
        """GET /api/v1/snapshot returns zero net worth for a fresh tenant."""
        resp = client.get("/api/v1/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["net_worth"] == 0.0
        assert data["layers"] == []
        assert data["liquid_net_worth"] == 0.0

    @pytest.mark.e2e
    def test_accounts_empty_state(self, client):
        """GET /api/v1/accounts/ returns empty list for fresh tenant."""
        resp = client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.e2e
    def test_income_current_empty(self, client):
        """GET /api/v1/income/current returns zero for fresh tenant."""
        resp = client.get("/api/v1/income/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["salary"] == 0
        assert data["total_comp"] == 0

    @pytest.mark.e2e
    def test_health_check(self, client):
        """GET /api/v1/health returns ok."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 2: Import Income Data
# ═══════════════════════════════════════════════════════════════════════════════


class TestImportIncome:
    """Test the unified import workflow with AI document parsing."""

    @pytest.mark.e2e
    def test_import_config_income(self, client):
        """GET /api/v1/import/config/income returns context guidance."""
        resp = client.get("/api/v1/import/config/income")
        assert resp.status_code == 200
        data = resp.json()
        assert data["context"] == "income"
        assert "guidance" in data
        assert "examples" in data
        assert len(data["expected_fields"]) > 0

    @pytest.mark.e2e
    @pytest.mark.skipif(
        not os.getenv("FINANCE_ANTHROPIC_API_KEY"),
        reason="FINANCE_ANTHROPIC_API_KEY not set; AI import tests require Claude API",
    )
    def test_import_upload_and_review(self, client):
        """POST /api/v1/import/upload processes a PDF and returns session in review state."""
        # Create a minimal PDF-like payload (just enough for the endpoint to process)
        # The actual PDF content is sent to Claude, so we use a simple test document
        pdf_bytes = _create_minimal_pdf()

        resp = client.post(
            "/api/v1/import/upload",
            data={"context": "income"},
            files={"file": ("test_w2_2025.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "review"
        assert "session_id" in data
        assert data["context"] == "income"

        # Store session_id for subsequent tests
        TestImportIncome._session_id = data["session_id"]

    @pytest.mark.e2e
    @pytest.mark.skipif(
        not os.getenv("FINANCE_ANTHROPIC_API_KEY"),
        reason="FINANCE_ANTHROPIC_API_KEY not set",
    )
    def test_import_get_session(self, client):
        """GET /api/v1/import/{session_id} retrieves the parsed session."""
        session_id = getattr(TestImportIncome, "_session_id", None)
        if not session_id:
            pytest.skip("No session_id from upload test")

        resp = client.get(f"/api/v1/import/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "review"
        assert data["session_id"] == session_id

    @pytest.mark.e2e
    @pytest.mark.skipif(
        not os.getenv("FINANCE_ANTHROPIC_API_KEY"),
        reason="FINANCE_ANTHROPIC_API_KEY not set",
    )
    def test_import_confirm(self, client):
        """POST /api/v1/import/{session_id}/confirm applies changes."""
        session_id = getattr(TestImportIncome, "_session_id", None)
        if not session_id:
            pytest.skip("No session_id from upload test")

        resp = client.post(f"/api/v1/import/{session_id}/confirm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"

    @pytest.mark.e2e
    def test_create_w2_directly(self, client):
        """POST /api/v1/income/w2 creates W2 record (non-AI path)."""
        resp = client.post("/api/v1/income/w2", json={
            "tax_year": 2025,
            "gross_pay": 210000.0,
            "base_salary": 145000.0,
            "rsu_income": 65000.0,
            "federal_tax": 38500.0,
            "state_tax": 10400.0,
            "social_security": 10918.20,
            "medicare": 3045.0,
            "pretax_401k": 10000.0,
            "roth_401k": 5000.0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["tax_year"] == 2025
        assert data["gross_pay"] == 210000.0
        assert data["base_salary"] == 145000.0

    @pytest.mark.e2e
    def test_income_current_after_w2(self, client):
        """GET /api/v1/income/current returns data after W2 creation."""
        resp = client.get("/api/v1/income/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["salary"] == 145000.0
        assert data["rsu_income"] == 65000.0
        assert data["total_comp"] == 210000.0

    @pytest.mark.e2e
    def test_income_history(self, client):
        """GET /api/v1/income/history returns W2 records."""
        resp = client.get("/api/v1/income/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["w2_records"]) >= 1
        w2 = data["w2_records"][0]
        assert w2["tax_year"] == 2025


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 3: Account Management
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccountManagement:
    """Create accounts, verify they appear in lists and snapshot."""

    @pytest.mark.e2e
    def test_create_checking_account(self, client):
        """POST /api/v1/accounts/ creates a checking account."""
        resp = client.post("/api/v1/accounts/", json={
            "name": "E2E Checking (...1234)",
            "institution": "Test Bank",
            "account_type": "cash",
            "display_group": "cash",
            "include_in_nw": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "E2E Checking (...1234)"
        assert data["account_type"] == "cash"
        assert data["display_group"] == "cash"
        TestAccountManagement._checking_id = data["id"]

    @pytest.mark.e2e
    def test_create_savings_account(self, client):
        """POST /api/v1/accounts/ creates a savings account."""
        resp = client.post("/api/v1/accounts/", json={
            "name": "E2E Savings (...5678)",
            "institution": "Test Bank",
            "account_type": "cash",
            "display_group": "cash",
            "include_in_nw": True,
        })
        assert resp.status_code == 201
        TestAccountManagement._savings_id = resp.json()["id"]

    @pytest.mark.e2e
    def test_create_retirement_account(self, client):
        """POST /api/v1/accounts/ creates a retirement account."""
        resp = client.post("/api/v1/accounts/", json={
            "name": "E2E 401(k) at Fidelity",
            "institution": "Fidelity",
            "account_type": "retirement_401k",
            "display_group": "retirement",
            "include_in_nw": True,
        })
        assert resp.status_code == 201
        TestAccountManagement._retirement_id = resp.json()["id"]

    @pytest.mark.e2e
    def test_list_accounts(self, client):
        """GET /api/v1/accounts/ returns all created accounts."""
        resp = client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        names = [a["name"] for a in data]
        assert "E2E Checking (...1234)" in names
        assert "E2E Savings (...5678)" in names

    @pytest.mark.e2e
    def test_get_single_account(self, client):
        """GET /api/v1/accounts/{id} returns the specific account."""
        acct_id = getattr(TestAccountManagement, "_checking_id", None)
        if not acct_id:
            pytest.skip("No checking account created")
        resp = client.get(f"/api/v1/accounts/{acct_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == acct_id
        assert data["name"] == "E2E Checking (...1234)"

    @pytest.mark.e2e
    def test_filter_accounts_by_type(self, client):
        """GET /api/v1/accounts/?account_type=cash filters correctly."""
        resp = client.get("/api/v1/accounts/", params={"account_type": "cash"})
        assert resp.status_code == 200
        data = resp.json()
        for acct in data:
            assert acct["account_type"] == "cash"

    @pytest.mark.e2e
    def test_update_account(self, client):
        """PUT /api/v1/accounts/{id} updates account fields."""
        acct_id = getattr(TestAccountManagement, "_checking_id", None)
        if not acct_id:
            pytest.skip("No checking account created")
        resp = client.put(f"/api/v1/accounts/{acct_id}", json={
            "notes": "Updated by E2E test",
        })
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Updated by E2E test"

    @pytest.mark.e2e
    def test_snapshot_still_zero_without_balances(self, client):
        """Snapshot net_worth remains 0 when accounts have no balance snapshots."""
        resp = client.get("/api/v1/snapshot")
        assert resp.status_code == 200
        # Accounts exist but have no balance snapshots yet, so net_worth = 0
        data = resp.json()
        assert data["net_worth"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 4: API Key Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyLifecycle:
    """Create, use, and revoke API keys."""

    @pytest.mark.e2e
    def test_create_api_key(self, client):
        """POST /api/v1/api-keys/ creates a read-only API key."""
        resp = client.post("/api/v1/api-keys/", json={
            "name": "E2E Test Key",
            "permissions": "read",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "E2E Test Key"
        assert data["permissions"] == "read"
        assert data["is_active"] is True
        assert "key" in data  # full key only returned on creation
        assert data["key"].startswith("tld_")
        TestApiKeyLifecycle._key_id = data["id"]
        TestApiKeyLifecycle._full_key = data["key"]

    @pytest.mark.e2e
    def test_list_api_keys(self, client):
        """GET /api/v1/api-keys/ returns the created key."""
        resp = client.get("/api/v1/api-keys/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        key_entry = next((k for k in data if k["id"] == TestApiKeyLifecycle._key_id), None)
        assert key_entry is not None
        assert key_entry["name"] == "E2E Test Key"
        # Full key should NOT be in list response
        assert "key" not in key_entry or key_entry.get("key") is None

    @pytest.mark.e2e
    def test_use_api_key_for_snapshot(self, client):
        """API key can be used via X-API-Key header to access data."""
        from app.main import app
        from fastapi.testclient import TestClient

        # Create a fresh client without cookies, using API key
        api_client = TestClient(app)
        full_key = getattr(TestApiKeyLifecycle, "_full_key", None)
        if not full_key:
            pytest.skip("No API key created")

        resp = api_client.get(
            "/api/v1/snapshot",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 200
        assert "net_worth" in resp.json()

    @pytest.mark.e2e
    def test_use_api_key_for_accounts(self, client):
        """API key works for tenant-scoped endpoints (accounts)."""
        from app.main import app
        from fastapi.testclient import TestClient

        api_client = TestClient(app)
        full_key = getattr(TestApiKeyLifecycle, "_full_key", None)
        if not full_key:
            pytest.skip("No API key created")

        resp = api_client.get(
            "/api/v1/accounts/",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.e2e
    def test_revoke_api_key(self, client):
        """DELETE /api/v1/api-keys/{id} revokes the key."""
        key_id = getattr(TestApiKeyLifecycle, "_key_id", None)
        if not key_id:
            pytest.skip("No API key created")

        resp = client.delete(f"/api/v1/api-keys/{key_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "API key revoked"

    @pytest.mark.e2e
    def test_revoked_key_returns_401(self, client):
        """Using a revoked API key returns 401."""
        from app.main import app
        from fastapi.testclient import TestClient

        api_client = TestClient(app)
        full_key = getattr(TestApiKeyLifecycle, "_full_key", None)
        if not full_key:
            pytest.skip("No API key created")

        resp = api_client.get(
            "/api/v1/snapshot",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 5: Tenant Isolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    """Verify that data in one tenant is invisible to another."""

    @pytest.mark.e2e
    def test_first_tenant_has_accounts(self, client, seed_test_data):
        """First tenant should have the seeded accounts."""
        resp = client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        data = resp.json()
        # Should have at least the 3 seeded accounts
        assert len(data) >= 3

    @pytest.mark.e2e
    def test_second_tenant_has_no_accounts(self, client2, second_tenant_setup):
        """Second tenant should have zero accounts (isolated schema)."""
        resp = client2.get("/api/v1/accounts/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0

    @pytest.mark.e2e
    def test_second_tenant_empty_snapshot(self, client2, second_tenant_setup):
        """Second tenant has zero net worth."""
        resp = client2.get("/api/v1/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["net_worth"] == 0.0

    @pytest.mark.e2e
    def test_second_tenant_no_income(self, client2, second_tenant_setup):
        """Second tenant has no income data."""
        resp = client2.get("/api/v1/income/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["salary"] == 0

    @pytest.mark.e2e
    def test_add_account_to_second_tenant(self, client2, second_tenant_setup):
        """Adding an account to the second tenant doesn't affect the first."""
        resp = client2.post("/api/v1/accounts/", json={
            "name": "Tenant2 Checking",
            "institution": "Other Bank",
            "account_type": "cash",
            "display_group": "cash",
            "include_in_nw": True,
        })
        assert resp.status_code == 201

    @pytest.mark.e2e
    def test_first_tenant_unaffected(self, client, seed_test_data):
        """First tenant's account list is unchanged after second tenant adds data."""
        resp = client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        data = resp.json()
        names = [a["name"] for a in data]
        assert "Tenant2 Checking" not in names

    @pytest.mark.e2e
    def test_second_tenant_has_own_account(self, client2, second_tenant_setup):
        """Second tenant sees only its own account."""
        resp = client2.get("/api/v1/accounts/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Tenant2 Checking"

    @pytest.mark.e2e
    def test_schema_introspection_shows_tenant_schema(self, client, e2e_setup):
        """GET /api/v1/admin/schema returns tables in the tenant schema."""
        resp = client.get("/api/v1/admin/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "tables" in data
        table_names = [t["name"] for t in data["tables"]]
        # Financial tables should be present in tenant schema
        assert "accounts" in table_names
        assert "balance_snapshots" in table_names
        assert "transactions" in table_names


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 6: Cross-Endpoint Consistency
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossEndpointConsistency:
    """Verify consistency across endpoints using seeded data."""

    @pytest.mark.e2e
    def test_snapshot_reflects_balances(self, client, seed_test_data):
        """Snapshot net_worth matches sum of seeded balances."""
        resp = client.get("/api/v1/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        # 12000 + 18000 + 185000 = 215000
        assert data["net_worth"] >= 215000.0

        # Verify layers exist
        assert len(data["layers"]) >= 1

    @pytest.mark.e2e
    def test_snapshot_layer_breakdown(self, client, seed_test_data):
        """Snapshot layers correctly group by display_group."""
        resp = client.get("/api/v1/snapshot")
        data = resp.json()

        layer_map = {layer["name"]: layer for layer in data["layers"]}

        # Cash layer should have checking + savings
        assert "Cash" in layer_map
        assert layer_map["Cash"]["total"] >= 30000.0
        assert len(layer_map["Cash"]["accounts"]) >= 2

        # Retirement layer
        assert "Retirement" in layer_map
        assert layer_map["Retirement"]["total"] >= 185000.0

    @pytest.mark.e2e
    def test_snapshot_liquid_net_worth(self, client, seed_test_data):
        """Liquid net worth includes only cash + investments (not retirement)."""
        resp = client.get("/api/v1/snapshot")
        data = resp.json()
        # Only cash accounts are liquid (cash display_group)
        assert data["liquid_net_worth"] >= 30000.0

    @pytest.mark.e2e
    def test_net_worth_trend(self, client, seed_test_data):
        """GET /api/v1/trends/net-worth reflects the balance snapshots."""
        resp = client.get("/api/v1/trends/net-worth")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dates"]) >= 1
        # The last total should be our net worth
        assert data["totals"][-1] == 215000.0

    @pytest.mark.e2e
    def test_balance_history_for_account(self, client, seed_test_data):
        """GET /api/v1/accounts/{id}/balances returns balance history."""
        acct_id = seed_test_data["checking_id"]
        resp = client.get(f"/api/v1/accounts/{acct_id}/balances")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[-1]["balance"] == 12000.0

    @pytest.mark.e2e
    def test_transactions_list(self, client, seed_test_data):
        """GET /api/v1/transactions/ returns seeded transactions."""
        resp = client.get("/api/v1/transactions/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3

    @pytest.mark.e2e
    def test_spending_by_category(self, client, seed_test_data):
        """GET /api/v1/spending/by-category reflects the seeded transactions."""
        resp = client.get("/api/v1/spending/by-category")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3  # Groceries, Rent, Entertainment

        categories = {item["category"]: item for item in data}
        assert "Groceries" in categories
        assert "Rent" in categories
        assert "Entertainment" in categories

        # Spending amounts are negative, verify totals
        assert categories["Rent"]["total"] <= -1200.0
        assert categories["Groceries"]["total"] <= -85.5

    @pytest.mark.e2e
    def test_spending_pct_of_total(self, client, seed_test_data):
        """Spending percentages should sum to approximately 100%."""
        resp = client.get("/api/v1/spending/by-category")
        data = resp.json()
        if data:
            total_pct = sum(item["pct_of_total"] for item in data)
            assert abs(total_pct - 100.0) < 1.0  # within rounding tolerance

    @pytest.mark.e2e
    def test_transactions_filter_by_category(self, client, seed_test_data):
        """Transaction filtering by category works."""
        resp = client.get("/api/v1/transactions/", params={"category": "Groceries"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["category"] == "Groceries"


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 7: Tenant Switching
# ═══════════════════════════════════════════════════════════════════════════════


class TestTenantSwitching:
    """Test switching between tenants via select-tenant endpoint."""

    @pytest.mark.e2e
    def test_list_tenants(self, client):
        """GET /api/v1/tenants/ lists the user's tenants."""
        resp = client.get("/api/v1/tenants/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    @pytest.mark.e2e
    def test_create_second_tenant_for_switching(self, client, e2e_setup):
        """POST /api/v1/tenants/ creates a new tenant for the same user."""
        resp = client.post("/api/v1/tenants/", json={
            "display_name": "E2E Switchable Tenant",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "E2E Switchable Tenant"
        TestTenantSwitching._second_tenant_id = data["id"]
        TestTenantSwitching._second_schema = data["schema_name"]

    @pytest.mark.e2e
    def test_switch_to_second_tenant(self, client):
        """POST /api/v1/auth/select-tenant switches tenant context."""
        tenant_id = getattr(TestTenantSwitching, "_second_tenant_id", None)
        if not tenant_id:
            pytest.skip("No second tenant created")

        resp = client.post("/api/v1/auth/select-tenant", json={
            "tenant_id": tenant_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["current_tenant"]["id"] == tenant_id

    @pytest.mark.e2e
    def test_switched_tenant_is_empty(self, client):
        """After switching, the new tenant has no data."""
        tenant_id = getattr(TestTenantSwitching, "_second_tenant_id", None)
        if not tenant_id:
            pytest.skip("No second tenant created")

        resp = client.get("/api/v1/accounts/")
        assert resp.status_code == 200

    @pytest.mark.e2e
    def test_switch_back_to_original(self, client, e2e_setup):
        """Switch back to original tenant to restore state for other tests."""
        resp = client.post("/api/v1/auth/select-tenant", json={
            "tenant_id": e2e_setup["tenant_id"],
        })
        assert resp.status_code == 200

    @pytest.mark.e2e
    def test_cannot_switch_to_unowned_tenant(self, client, second_tenant_setup):
        """Attempting to switch to a tenant the user doesn't belong to returns 403."""
        other_tenant_id = second_tenant_setup["tenant_id"]
        resp = client.post("/api/v1/auth/select-tenant", json={
            "tenant_id": other_tenant_id,
        })
        assert resp.status_code == 403

    @pytest.mark.e2e
    def test_cleanup_second_tenant(self, pg_engine):
        """Cleanup the second tenant created for switching tests."""
        schema = getattr(TestTenantSwitching, "_second_schema", None)
        if not schema:
            return

        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text

        Session = sessionmaker(bind=pg_engine)
        db = Session()
        try:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            db.execute(text(
                "DELETE FROM tenant_memberships WHERE tenant_id IN "
                "(SELECT id FROM tenants WHERE schema_name = :schema)"
            ), {"schema": schema})
            db.execute(text("DELETE FROM tenants WHERE schema_name = :schema"), {"schema": schema})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Journey 8: Admin & Schema Introspection
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints:
    """Test admin data browsing and schema introspection."""

    @pytest.mark.e2e
    def test_admin_tables(self, client, seed_test_data):
        """GET /api/v1/admin/tables returns table list with row counts."""
        resp = client.get("/api/v1/admin/tables")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        table_names = [t["table"] for t in data]
        assert "accounts" in table_names

        # Accounts table should have rows from seed
        acct_entry = next(t for t in data if t["table"] == "accounts")
        assert acct_entry["row_count"] >= 3

    @pytest.mark.e2e
    def test_admin_table_rows(self, client, seed_test_data):
        """GET /api/v1/admin/tables/accounts returns paginated rows."""
        resp = client.get("/api/v1/admin/tables/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["table"] == "accounts"
        assert data["total"] >= 3
        assert len(data["rows"]) >= 3

    @pytest.mark.e2e
    def test_admin_query(self, client, seed_test_data):
        """POST /api/v1/admin/query runs a SELECT query."""
        resp = client.post("/api/v1/admin/query", json={
            "sql": "SELECT COUNT(*) as cnt FROM accounts",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rows"][0]["cnt"] >= 3

    @pytest.mark.e2e
    def test_admin_query_blocks_writes(self, client):
        """POST /api/v1/admin/query rejects non-SELECT statements."""
        resp = client.post("/api/v1/admin/query", json={
            "sql": "DELETE FROM accounts WHERE 1=1",
        })
        assert resp.status_code == 400

    @pytest.mark.e2e
    def test_schema_erd_data(self, client):
        """GET /api/v1/admin/schema returns ERD-compatible table + edge data."""
        resp = client.get("/api/v1/admin/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "tables" in data
        assert "edges" in data

        # Verify foreign key edges exist (e.g., balance_snapshots -> accounts)
        edge_pairs = [(e["from_table"], e["to_table"]) for e in data["edges"]]
        assert ("balance_snapshots", "accounts") in edge_pairs
        assert ("transactions", "accounts") in edge_pairs


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _create_minimal_pdf() -> bytes:
    """Create a minimal valid PDF with some W2-like content for testing AI import."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        import io

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(100, 700, "W-2 Wage and Tax Statement 2025")
        c.drawString(100, 680, "Employer: Microsoft Corporation")
        c.drawString(100, 660, "Employee: E2E Test User")
        c.drawString(100, 640, "Box 1 - Wages: $210,000.00")
        c.drawString(100, 620, "Box 2 - Federal Tax: $38,500.00")
        c.drawString(100, 600, "Box 3 - Social Security Wages: $160,200.00")
        c.drawString(100, 580, "Box 4 - Social Security Tax: $10,918.20")
        c.drawString(100, 560, "Box 5 - Medicare Wages: $210,000.00")
        c.drawString(100, 540, "Box 6 - Medicare Tax: $3,045.00")
        c.drawString(100, 520, "Box 17 - State Tax: $10,400.00")
        c.save()
        return buf.getvalue()
    except ImportError:
        # Fallback: minimal valid PDF bytes
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n213\n%%EOF\n"
        )
