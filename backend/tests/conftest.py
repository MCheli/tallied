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
from app.main import app, v1, legacy

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


@pytest.fixture(autouse=True)
def db_session():
    """Provide a clean database session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)

    # Override dependencies on all three app instances (main, v1, legacy)
    for a in (app, v1, legacy):
        a.dependency_overrides[get_db] = lambda: session
        a.dependency_overrides[get_tenant_db] = lambda: session
        a.dependency_overrides[get_tenant_context] = lambda: MOCK_TENANT_CTX

    yield session

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
