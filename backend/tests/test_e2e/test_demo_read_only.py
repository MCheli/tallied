"""DEMO-001 second layer: in demo mode a tenant session cannot write, even past the middleware."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError, OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.models.account import Account

pytestmark = pytest.mark.e2e


def test_read_only_tenant_session_refuses_writes_and_allows_reads(pg_engine, e2e_setup, seed_test_data, monkeypatch):
    from app.services import tenant_service

    monkeypatch.setattr(tenant_service, "SessionLocal", sessionmaker(bind=pg_engine))
    schema = e2e_setup["tenant_schema"]
    with tenant_service.tenant_session(schema, read_only=True) as db:
        assert db.execute(text("SELECT count(*) FROM accounts")).scalar() >= 1
        db.add(Account(id="demo-write", name="X", account_type="cash", display_group="Cash"))
        with pytest.raises((InternalError, OperationalError, ProgrammingError), match="read-only transaction"):
            db.commit()
        db.rollback()
        # Still read-only after a rollback starts a new transaction
        with pytest.raises((InternalError, OperationalError, ProgrammingError), match="read-only transaction"):
            db.execute(text("DELETE FROM accounts WHERE id = 'nope'"))
