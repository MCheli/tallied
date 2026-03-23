"""
E2E test fixtures — uses a REAL PostgreSQL database with isolated tenant schemas.

Requirements:
  - PostgreSQL running: docker compose up -d postgres
  - Connection: postgresql://tallied:tallied_dev@localhost/tallied

Each test module gets its own temporary tenant schema that is torn down afterwards.

IMPORTANT: The parent tests/conftest.py has autouse fixtures that override DB
dependencies to use SQLite. We must undo those overrides here so e2e tests
hit the real PostgreSQL database.
"""
import hashlib
import os
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Database connection ────────────────────────────────────────────────────────

PG_URL = os.getenv(
    "E2E_DATABASE_URL",
    "postgresql://tallied:tallied_dev@localhost/tallied",
)

ALGORITHM = "HS256"
SECRET_KEY = "tallied-dev-secret-change-in-production"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── Undo parent conftest autouse overrides ─────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """Remove the SQLite dependency overrides set by the parent conftest.

    The parent tests/conftest.py has autouse fixtures that override get_db,
    get_tenant_db, and get_tenant_context to use in-memory SQLite. For E2E
    tests we need the REAL dependencies so requests hit PostgreSQL.
    """
    from app.main import app, v1, legacy
    from app.database import get_db
    from app.dependencies import get_tenant_db, get_tenant_context

    # Clear any overrides that the parent conftest may have set
    for a in (app, v1, legacy):
        a.dependency_overrides.pop(get_db, None)
        a.dependency_overrides.pop(get_tenant_db, None)
        a.dependency_overrides.pop(get_tenant_context, None)

    yield

    # Re-clear after test in case anything re-set them
    for a in (app, v1, legacy):
        a.dependency_overrides.pop(get_db, None)
        a.dependency_overrides.pop(get_tenant_db, None)
        a.dependency_overrides.pop(get_tenant_context, None)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def pg_engine():
    """Create a SQLAlchemy engine connected to the real PostgreSQL database."""
    engine = create_engine(PG_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def test_schema_name():
    """Generate a unique schema name for this test module."""
    return f"test_e2e_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def test_user_email():
    """Generate a unique email for the test user."""
    return f"e2e_test_{uuid.uuid4().hex[:8]}@tallied.dev"


@pytest.fixture(scope="module")
def e2e_setup(pg_engine, test_schema_name, test_user_email):
    """
    Create a test user, tenant, membership, and tenant schema in PostgreSQL.

    Returns a dict with IDs and metadata needed by tests.
    Tears everything down after the module completes.
    """
    Session = sessionmaker(bind=pg_engine)

    # Ensure platform tables exist (they should from app startup, but be safe)
    with pg_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'users')"
        ))
        if not result.scalar():
            pytest.skip("Platform tables not created. Run the app once first.")

    db = Session()
    try:
        # 1. Create test user
        db.execute(text(
            "INSERT INTO users (email, password_hash, display_name, auth_provider, is_admin, is_active) "
            "VALUES (:email, :pw, :name, 'local', false, true) RETURNING id"
        ), {
            "email": test_user_email,
            "pw": _hash_password("testpass123"),
            "name": "E2E Test User",
        })
        user_row = db.execute(text(
            "SELECT id FROM users WHERE email = :email"
        ), {"email": test_user_email}).fetchone()
        user_id = user_row[0]

        # 2. Create tenant
        db.execute(text(
            "INSERT INTO tenants (slug, display_name, schema_name, is_active) "
            "VALUES (:slug, :display, :schema, true) RETURNING id"
        ), {
            "slug": test_schema_name,
            "display": "E2E Test Tenant",
            "schema": test_schema_name,
        })
        tenant_row = db.execute(text(
            "SELECT id FROM tenants WHERE slug = :slug"
        ), {"slug": test_schema_name}).fetchone()
        tenant_id = tenant_row[0]

        # 3. Create membership
        db.execute(text(
            "INSERT INTO tenant_memberships (user_id, tenant_id, role, is_default) "
            "VALUES (:uid, :tid, 'owner', true)"
        ), {"uid": user_id, "tid": tenant_id})

        # 4. Create the tenant schema and populate with financial tables
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{test_schema_name}"'))
        db.commit()

        # Use the app's own create_tenant_schema to ensure tables match
        from app.services.tenant_service import create_tenant_schema
        create_tenant_schema(test_schema_name)

        setup_data = {
            "user_id": user_id,
            "user_email": test_user_email,
            "tenant_id": tenant_id,
            "tenant_schema": test_schema_name,
        }

        yield setup_data

    finally:
        # Teardown: drop schema and remove platform rows
        try:
            db.rollback()
            db.execute(text(f'DROP SCHEMA IF EXISTS "{test_schema_name}" CASCADE'))
            db.execute(text(
                "DELETE FROM tenant_memberships WHERE tenant_id IN "
                "(SELECT id FROM tenants WHERE schema_name = :schema)"
            ), {"schema": test_schema_name})
            db.execute(text(
                "DELETE FROM api_keys WHERE user_id IN "
                "(SELECT id FROM users WHERE email = :email)"
            ), {"email": test_user_email})
            db.execute(text(
                "DELETE FROM tenants WHERE schema_name = :schema"
            ), {"schema": test_schema_name})
            db.execute(text(
                "DELETE FROM users WHERE email = :email"
            ), {"email": test_user_email})
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"WARNING: e2e teardown failed: {exc}")
        finally:
            db.close()


@pytest.fixture(scope="module")
def seed_test_data(pg_engine, e2e_setup):
    """Seed baseline financial data into the test tenant schema.

    Creates accounts, balance snapshots, and transactions so that all test
    classes can rely on a known data set without depending on execution order.
    Returns a dict with the created IDs for use in assertions.
    """
    Session = sessionmaker(bind=pg_engine)
    db = Session()
    schema = e2e_setup["tenant_schema"]

    try:
        db.execute(text(f'SET search_path TO "{schema}"'))

        # ── Accounts ──────────────────────────────────────────────────────
        # Use "Seed" prefix to avoid collisions with accounts created by
        # TestAccountManagement (which tests the POST /accounts/ flow).
        # accounts.id is a string (UUID) with no auto-generation, so we
        # must supply it explicitly.
        checking_id = str(uuid.uuid4())
        savings_id = str(uuid.uuid4())
        retirement_id = str(uuid.uuid4())

        db.execute(text(
            "INSERT INTO accounts (id, name, institution, account_type, display_group, include_in_nw, is_active) "
            "VALUES (:id, :name, :inst, :atype, :dgroup, true, true)"
        ), {"id": checking_id, "name": "Seed Checking (...1234)", "inst": "Test Bank", "atype": "cash", "dgroup": "cash"})

        db.execute(text(
            "INSERT INTO accounts (id, name, institution, account_type, display_group, include_in_nw, is_active) "
            "VALUES (:id, :name, :inst, :atype, :dgroup, true, true)"
        ), {"id": savings_id, "name": "Seed Savings (...5678)", "inst": "Test Bank", "atype": "cash", "dgroup": "cash"})

        db.execute(text(
            "INSERT INTO accounts (id, name, institution, account_type, display_group, include_in_nw, is_active) "
            "VALUES (:id, :name, :inst, :atype, :dgroup, true, true)"
        ), {"id": retirement_id, "name": "Seed 401(k) at Fidelity", "inst": "Fidelity", "atype": "retirement_401k", "dgroup": "retirement"})

        # ── Balance snapshots ─────────────────────────────────────────────
        today = date.today().isoformat()
        for aid, bal in [(checking_id, 12000), (savings_id, 18000), (retirement_id, 185000)]:
            db.execute(text(
                "INSERT INTO balance_snapshots (account_id, snapshot_date, balance, source) "
                "VALUES (:aid, :d, :b, 'e2e_seed')"
            ), {"aid": aid, "d": today, "b": bal})

        # ── Transactions ──────────────────────────────────────────────────
        txns = [
            {"id": str(uuid.uuid4()), "account_id": checking_id, "date": today,
             "amount": -85.50, "merchant": "Whole Foods", "category": "Groceries",
             "category_group": "Food & Drink", "source": "e2e_seed", "is_recurring": False},
            {"id": str(uuid.uuid4()), "account_id": checking_id, "date": today,
             "amount": -1200.00, "merchant": "Landlord", "category": "Rent",
             "category_group": "Housing", "source": "e2e_seed", "is_recurring": False},
            {"id": str(uuid.uuid4()), "account_id": checking_id, "date": today,
             "amount": -45.00, "merchant": "Netflix", "category": "Entertainment",
             "category_group": "Entertainment", "source": "e2e_seed", "is_recurring": False},
        ]
        for t in txns:
            db.execute(text(
                "INSERT INTO transactions (id, account_id, date, amount, merchant, category, category_group, source, is_recurring) "
                "VALUES (:id, :account_id, :date, :amount, :merchant, :category, :category_group, :source, :is_recurring)"
            ), t)

        db.commit()

        # Reset search_path so the connection doesn't leak tenant schema
        # into other fixtures that share the same pg_engine pool.
        db.execute(text("SET search_path TO public"))
        db.commit()

        yield {
            "checking_id": checking_id,
            "savings_id": savings_id,
            "retirement_id": retirement_id,
        }

    finally:
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            pass
        db.close()


def _make_jwt(user_id: int, email: str, tenant_id: int, tenant_schema: str) -> str:
    """Create a JWT token matching the app's auth format."""
    expire = datetime.now(timezone.utc) + timedelta(hours=72)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "tenant_id": tenant_id,
            "tenant_schema": tenant_schema,
            "exp": expire,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


@pytest.fixture(scope="module")
def auth_token(e2e_setup):
    """Create a valid JWT for the test user/tenant."""
    return _make_jwt(
        e2e_setup["user_id"],
        e2e_setup["user_email"],
        e2e_setup["tenant_id"],
        e2e_setup["tenant_schema"],
    )


@pytest.fixture(scope="module")
def client(auth_token):
    """
    FastAPI TestClient with the JWT cookie pre-set.

    Uses the root app and prefixes paths with /api/v1/.
    """
    from app.main import app

    c = TestClient(app)
    c.cookies.set("tallied_token", auth_token)
    return c


# ── Second tenant fixtures (for isolation tests) ──────────────────────────────


@pytest.fixture(scope="module")
def second_tenant_setup(pg_engine, e2e_setup):
    """Create a second user + tenant for isolation testing."""
    Session = sessionmaker(bind=pg_engine)
    db = Session()
    schema2 = f"test_e2e_{uuid.uuid4().hex[:8]}"
    email2 = f"e2e_test2_{uuid.uuid4().hex[:8]}@tallied.dev"

    try:
        db.execute(text(
            "INSERT INTO users (email, password_hash, display_name, auth_provider, is_admin, is_active) "
            "VALUES (:email, :pw, :name, 'local', false, true)"
        ), {"email": email2, "pw": _hash_password("testpass456"), "name": "E2E Test User 2"})

        user_row = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email2}).fetchone()
        user_id_2 = user_row[0]

        db.execute(text(
            "INSERT INTO tenants (slug, display_name, schema_name, is_active) "
            "VALUES (:slug, :display, :schema, true)"
        ), {"slug": schema2, "display": "E2E Test Tenant 2", "schema": schema2})

        tenant_row = db.execute(text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": schema2}).fetchone()
        tenant_id_2 = tenant_row[0]

        db.execute(text(
            "INSERT INTO tenant_memberships (user_id, tenant_id, role, is_default) "
            "VALUES (:uid, :tid, 'owner', true)"
        ), {"uid": user_id_2, "tid": tenant_id_2})

        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema2}"'))
        db.commit()

        from app.services.tenant_service import create_tenant_schema
        create_tenant_schema(schema2)

        token2 = _make_jwt(user_id_2, email2, tenant_id_2, schema2)

        yield {
            "user_id": user_id_2,
            "user_email": email2,
            "tenant_id": tenant_id_2,
            "tenant_schema": schema2,
            "token": token2,
        }

    finally:
        try:
            db.rollback()
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema2}" CASCADE'))
            db.execute(text(
                "DELETE FROM tenant_memberships WHERE tenant_id IN "
                "(SELECT id FROM tenants WHERE schema_name = :schema)"
            ), {"schema": schema2})
            db.execute(text(
                "DELETE FROM api_keys WHERE user_id IN "
                "(SELECT id FROM users WHERE email = :email)"
            ), {"email": email2})
            db.execute(text("DELETE FROM tenants WHERE schema_name = :schema"), {"schema": schema2})
            db.execute(text("DELETE FROM users WHERE email = :email"), {"email": email2})
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"WARNING: second tenant teardown failed: {exc}")
        finally:
            db.close()


@pytest.fixture(scope="module")
def client2(second_tenant_setup):
    """TestClient authenticated as the second tenant user."""
    from app.main import app

    c = TestClient(app)
    c.cookies.set("tallied_token", second_tenant_setup["token"])
    return c
