"""Test configuration — in-memory SQLite for fast isolated tests.

Production uses PostgreSQL with schema-per-tenant. Tests use SQLite with
mocked tenant context for speed and zero-dependency CI.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add project root to path for script imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import Base, get_db
from app.dependencies import get_tenant_db, get_tenant_context, TenantContext
from app.main import app, v1

# In-memory SQLite for tests (fast, no Docker needed)
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine)

# Mock tenant context for all tests
MOCK_TENANT_CTX = TenantContext(
    user_id=1, email="test@test.com", tenant_id=1, tenant_schema="public"
)


def _sqlite_year_month(column):
    """SQLite-compatible year_month for tests."""
    return func.strftime("%Y-%m", column)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once for the test session."""
    import app.models  # noqa — register all models

    with patch("app.api.spending.year_month", _sqlite_year_month), \
         patch("app.api.trends.year_month", _sqlite_year_month):
        # In SQLite tests, create ALL tables in one schema (no tenant isolation)
        Base.metadata.create_all(bind=test_engine)
        yield
        Base.metadata.drop_all(bind=test_engine)


# Modules that hold their own reference to SessionLocal (imported at module load). The
# unit suite must never reach the real database, so each one is pointed at the test
# connection for the duration of a test.
_SESSIONLOCAL_OWNERS = (
    "app.dependencies", "app.services.audit_service", "app.api.email_import",
    "app.services.sync_scheduler", "app.services.tenant_service", "app.middleware.usage_logger", "app.database",
)


@pytest.fixture(scope="session", autouse=True)
def _ci_like_settings():
    """Unit tests behave the same with or without a local backend/.env."""
    from app.config import settings

    settings.dev_mode = True
    settings.secret_key = "unit-test-secret-key-not-for-production"
    settings.credential_key = ""
    settings.anthropic_api_key = ""
    settings.email_webhook_secret = ""
    yield


@pytest.fixture(autouse=True)
def db_session(request):
    """Provide a clean SQLite session for each unit test. e2e tests use the real Postgres untouched."""
    import importlib

    if request.node.get_closest_marker("e2e"):
        yield None
        return

    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    bound_factory = sessionmaker(bind=connection)

    # Override dependencies on both app instances (main, v1)
    for a in (app, v1):
        a.dependency_overrides[get_db] = lambda: session
        a.dependency_overrides[get_tenant_db] = lambda: session
        a.dependency_overrides[get_tenant_context] = lambda: MOCK_TENANT_CTX

    patched = []
    for name in _SESSIONLOCAL_OWNERS:
        mod = importlib.import_module(name)
        if hasattr(mod, "SessionLocal"):
            patched.append((mod, mod.SessionLocal))
            mod.SessionLocal = bound_factory

    yield session

    for mod, original in patched:
        mod.SessionLocal = original
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def patch_year_month():
    """Patch year_month to use SQLite strftime in all test API calls."""
    with patch("app.api.spending.year_month", _sqlite_year_month), \
         patch("app.api.trends.year_month", _sqlite_year_month):
        yield


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def set_household_age(client, age: int) -> None:
    """Planning computes age from the household birth date; 1 January keeps the age exact all year."""
    from datetime import date

    res = client.put("/api/v1/plans/household", json={"birth_date": f"{date.today().year - age}-01-01"})
    assert res.status_code == 200, res.text


@pytest.fixture
def born_30(client):
    set_household_age(client, 30)


@pytest.fixture
def seeded_db(db_session):
    """Seed the test database with Claudius Banks data."""
    from decimal import Decimal
    from datetime import date
    from app.models.account import Account
    from app.models.income import W2Record
    from app.models.balance import BalanceSnapshot

    # Add basic accounts
    accounts = [
        Account(id="test-checking", name="Checking (...4521)", institution="Test Bank",
                account_type="cash", display_group="Cash", include_in_nw=True),
        Account(id="test-savings", name="Savings (...8834)", institution="Test Bank",
                account_type="cash", display_group="Cash", include_in_nw=True),
    ]
    for a in accounts:
        db_session.add(a)

    # Add W2
    db_session.add(W2Record(
        tax_year=2025, gross_pay=Decimal("210000"),
        base_salary=Decimal("145000"), rsu_income=Decimal("65000"),
        federal_tax=Decimal("38500"), state_tax=Decimal("10400"),
        social_security=Decimal("10918.20"), medicare=Decimal("3045"),
        pretax_401k=Decimal("10000"), roth_401k=Decimal("5000"),
    ))

    # Add balance snapshots
    db_session.add(BalanceSnapshot(
        account_id="test-checking", snapshot_date=date.today(),
        balance=Decimal("12000"), source="test",
    ))
    db_session.add(BalanceSnapshot(
        account_id="test-savings", snapshot_date=date.today(),
        balance=Decimal("18000"), source="test",
    ))

    db_session.commit()
    return db_session
