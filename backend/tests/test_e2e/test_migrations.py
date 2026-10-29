"""The Alembic chain builds an empty database (NFR-MIG-001).

Creates a scratch database next to the e2e one, runs `alembic upgrade head`
against it, checks every platform table exists and a tenant schema can be
created, then drops the scratch database.
"""
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.test_e2e.conftest import PG_URL

pytestmark = pytest.mark.e2e

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[2]


def _with_database(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


@pytest.fixture
def scratch_database():
    name = f"tallied_migtest_{uuid.uuid4().hex[:8]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield _with_database(PG_URL, name)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_alembic_upgrade_head_builds_an_empty_database(scratch_database, monkeypatch):
    from app.config import settings
    from app.services.tenant_service import PLATFORM_TABLES

    monkeypatch.setattr(settings, "database_url", scratch_database)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")

    engine = create_engine(scratch_database)
    try:
        with engine.connect() as conn:
            public = {r[0] for r in conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ))}
            assert PLATFORM_TABLES <= public, f"missing platform tables: {PLATFORM_TABLES - public}"
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version

            # A tenant schema can be built the way the app does it
            from app.services.tenant_service import tenant_tables
            from app.database import Base
            conn.execute(text('CREATE SCHEMA "tenant_migtest01"'))
            conn.execute(text('SET search_path TO "tenant_migtest01"'))
            Base.metadata.create_all(bind=conn, tables=tenant_tables())
            conn.commit()
            n = conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tenant_migtest01'"
            )).scalar()
            assert n >= 20
    finally:
        engine.dispose()
