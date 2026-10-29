"""Security regressions: API key permissions, suspended users, legacy mount, webhook URLs, SQL runner guards."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
import jwt
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import dependencies
from app.config import settings
from app.models.api_key import ApiKey
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User
from app.services.sql_runner import QueryRejected, validate_sql


def _request(method: str, headers: dict | None = None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": method, "path": "/api/v1/accounts/", "headers": raw_headers,
             "query_string": b"", "client": ("127.0.0.1", 1234)}
    return Request(scope)


@pytest.fixture
def platform_rows(db_session):
    """A user, tenant and membership in the SQLite session; dependencies read through the same connection."""
    user = User(email="keyuser@test.dev", password_hash="", display_name="Key User", auth_provider="local",
                is_admin=False, is_active=True, status="active")
    tenant = Tenant(slug="tenant_keyuser", display_name="Key", schema_name="tenant_keyuser1", is_active=True)
    db_session.add_all([user, tenant])
    db_session.flush()
    db_session.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner", is_default=True))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind())
    with patch.object(dependencies, "SessionLocal", factory):
        yield user, tenant, db_session


def _make_key(db, user, tenant, permissions):
    raw = ApiKey.generate_key()
    db.add(ApiKey(user_id=user.id, tenant_id=tenant.id, name=permissions, key_prefix=raw[:12],
                  key_hash=ApiKey.hash_key(raw), permissions=permissions))
    db.commit()
    return raw


def test_read_only_api_key_cannot_use_mutating_methods(platform_rows):
    user, tenant, db = platform_rows
    raw = _make_key(db, user, tenant, "read")
    ctx = dependencies.get_tenant_context(_request("GET", {"X-API-Key": raw}))
    assert ctx.auth_method == "api_key" and ctx.permissions == "read"
    assert ctx.tenant_schema == tenant.schema_name
    with pytest.raises(HTTPException) as exc:
        dependencies.get_tenant_context(_request("POST", {"X-API-Key": raw}))
    assert exc.value.status_code == 403


def test_write_api_key_can_mutate_but_is_not_admin(platform_rows):
    user, tenant, db = platform_rows
    raw = _make_key(db, user, tenant, "write")
    ctx = dependencies.get_tenant_context(_request("DELETE", {"X-API-Key": raw}))
    assert ctx.permissions == "write"
    with pytest.raises(HTTPException) as exc:
        dependencies.require_admin(ctx)
    assert exc.value.status_code == 403
    assert dependencies.require_permission("write")(ctx) is ctx
    with pytest.raises(HTTPException):
        dependencies.require_permission("admin")(ctx)


def test_suspended_user_api_key_is_rejected(platform_rows):
    user, tenant, db = platform_rows
    raw = _make_key(db, user, tenant, "admin")
    user.status = "suspended"
    db.commit()
    with pytest.raises(HTTPException) as exc:
        dependencies.get_tenant_context(_request("GET", {"X-API-Key": raw}))
    assert exc.value.status_code == 401


def test_refresh_rejects_suspended_user(client, db_session):
    user = User(email="suspended@test.dev", password_hash="", display_name="S", auth_provider="local",
                is_active=True, status="suspended")
    db_session.add(user)
    db_session.commit()
    refresh = jwt.encode(
        {"sub": str(user.id), "type": "refresh", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        settings.secret_key, algorithm="HS256",
    )
    client.cookies.set("tallied_refresh", refresh)
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 401


def test_legacy_api_mount_is_gone(client):
    legacy_base = "/api"  # the un-versioned mount removed in SEC-8
    assert client.get(legacy_base + "/health").status_code == 404
    assert client.get(legacy_base + "/snapshot").status_code == 404
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/hook",
    "http://localhost:8000/hook",
    "http://10.0.0.5/hook",
    "http://192.168.1.10/hook",
    "http://169.254.169.254/latest/meta-data",
    "ftp://example.com/hook",
    "not a url",
])
def test_webhook_rejects_private_or_invalid_urls(client, url):
    res = client.post("/api/v1/webhooks/", json={"url": url, "events": ["import.completed"]})
    assert res.status_code == 400, res.text


def test_webhook_accepts_public_ip_url(client):
    res = client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook", "events": ["import.completed"]})
    assert res.status_code == 201, res.text


@pytest.mark.parametrize("sql", [
    "DELETE FROM accounts",
    "SELECT * FROM public.users",
    'SELECT * FROM "public"."users"',
    'SELECT * FROM "tenant_abc".accounts',
    "SELECT * FROM pg_catalog.pg_authid",
    "SELECT 1; DROP TABLE accounts",
    "SET ROLE postgres",
    "SELECT set_config('search_path', 'public', false); SELECT 1",
    "COPY (SELECT 1) TO PROGRAM 'id'",
])
def test_sql_runner_rejects_dangerous_text(sql):
    with pytest.raises(QueryRejected):
        validate_sql(sql, 100)


def test_sql_runner_adds_limit_and_caps_it():
    assert validate_sql("select * from accounts", 50).endswith("LIMIT 50")
    assert validate_sql("select * from accounts", 100000).endswith("LIMIT 1000")
    assert validate_sql("select * from accounts limit 5", 100).endswith("limit 5")


def test_sql_runner_runs_select_on_sqlite(client, seeded_db):
    res = client.post("/api/v1/admin/query", json={"sql": "SELECT count(*) AS n FROM accounts", "limit": 10})
    assert res.status_code == 200, res.text
    assert res.json()["rows"][0]["n"] == 2


def test_login_is_rate_limited_per_ip(client):
    from app.middleware.rate_limit import login_limiter

    login_limiter._requests.clear()
    with patch.object(login_limiter, "requests_per_hour", 2):
        codes = [
            client.post("/api/v1/auth/login", json={"email": "nobody@test.dev", "password": "x"}).status_code
            for _ in range(3)
        ]
    login_limiter._requests.clear()
    assert codes[:2] == [401, 401]
    assert codes[2] == 429
