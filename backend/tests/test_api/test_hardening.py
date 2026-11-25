"""Security hardening, November 2026: webhook delivery re-checks its target, CSRF origin check,
admin-only webhooks and database credentials for API keys, DB-credential expiry, invalid-key throttle."""
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.dependencies import TenantContext, get_tenant_context
from app.main import app, v1
from app.models.db_credential import DbCredential
from app.models.webhook import WebhookSubscription
from app.services import db_credentials as dbc
from app.services import webhook_service as ws


def _addrinfo(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return lambda host, port, **kw: [(family, socket.SOCK_STREAM, 6, "", (ip, port))]


def _sub(url="https://hooks.example.com/tallied"):
    return WebhookSubscription(id=5, user_id=1, tenant_id=1, url=url, events="import.completed", secret="s3cret")


def _mock_client(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


# ── Webhooks: DNS rebinding and the test-endpoint oracle ─────────────────────

def test_delivery_refuses_a_host_that_now_resolves_to_a_private_address():
    """Saved while public, then re-pointed at 10.0.0.5: nothing is sent."""
    def handler(request):
        raise AssertionError("no request may leave for a private address")

    with patch.object(ws.socket, "getaddrinfo", _addrinfo("10.0.0.5")), patch.object(ws, "_client", _mock_client(handler)):
        result = ws.send_test_event(_sub())
    assert result == {"success": False, "error": "Webhook URL must point at a public host"}


def test_delivery_connects_to_the_checked_ip_with_the_original_host_and_sni():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(204)

    with patch.object(ws.socket, "getaddrinfo", _addrinfo("93.184.216.34")), patch.object(ws, "_client", _mock_client(handler)):
        result = ws.send_test_event(_sub("https://hooks.example.com:8443/tallied?x=1"))
    assert result == {"success": True, "status_code": 204}
    req = seen[0]
    assert req.url.host == "93.184.216.34" and req.url.port == 8443 and req.url.path == "/tallied" and req.url.query == b"x=1"
    assert req.headers["host"] == "hooks.example.com:8443"
    assert req.extensions["sni_hostname"] == "hooks.example.com"
    assert req.headers["x-webhook-signature"] == ws.sign_payload(req.content, "s3cret")


def test_scheduled_delivery_also_rechecks_and_counts_a_failure(db_session):
    sub = WebhookSubscription(user_id=1, tenant_id=1, url="https://hooks.example.com/t", events="import.completed", secret="s")
    db_session.add(sub)
    db_session.commit()
    with patch.object(ws.socket, "getaddrinfo", _addrinfo("127.0.0.1")), \
         patch.object(ws, "_client", _mock_client(lambda r: httpx.Response(200))):
        assert ws.deliver_webhook("import.completed", 1, {"n": 1}, db_session) == 0
    db_session.refresh(sub)
    assert sub.failure_count == 1


@pytest.mark.parametrize("failure", [httpx.ConnectError("Connection refused"), httpx.ReadTimeout("timed out"), 503])
def test_test_endpoint_failure_is_generic(failure):
    def handler(request):
        if isinstance(failure, int):
            return httpx.Response(failure, text="internal banner v1.2")
        raise failure

    with patch.object(ws.socket, "getaddrinfo", _addrinfo("93.184.216.34")), patch.object(ws, "_client", _mock_client(handler)):
        result = ws.send_test_event(_sub())
    assert result == {"success": False, "error": ws.TEST_FAILED}


def test_redirects_are_not_followed():
    def handler(request):
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})
        raise AssertionError("followed a redirect")

    with patch.object(ws.socket, "getaddrinfo", _addrinfo("93.184.216.34")), patch.object(ws, "_client", _mock_client(handler)):
        assert ws.send_test_event(_sub())["success"] is False
    assert ws._client().follow_redirects is False


def test_webhook_routes_still_create_update_delete(client, db_session):
    res = client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook", "events": ["import.completed"]})
    assert res.status_code == 201, res.text
    hook = res.json()
    assert hook["secret"] and db_session.get(WebhookSubscription, hook["id"]).secret == hook["secret"]
    res = client.put(f"/api/v1/webhooks/{hook['id']}", json={"url": "http://10.0.0.1/x"})
    assert res.status_code == 400
    res = client.put(f"/api/v1/webhooks/{hook['id']}", json={"events": ["balance.updated"], "is_active": False})
    assert res.status_code == 200 and res.json()["events"] == ["balance.updated"] and res.json()["is_active"] is False
    assert client.delete(f"/api/v1/webhooks/{hook['id']}").status_code == 200
    assert db_session.get(WebhookSubscription, hook["id"]) is None


# ── API keys below admin cannot add outbound channels ────────────────────────

@pytest.fixture
def write_key_ctx():
    ctx = TenantContext(user_id=1, email="test@test.com", tenant_id=1, tenant_schema="public",
                        auth_method="api_key", permissions="write")
    for a in (app, v1):
        a.dependency_overrides[get_tenant_context] = lambda: ctx
    yield ctx


def test_write_api_key_cannot_create_or_repoint_webhooks(client, db_session, write_key_ctx):
    sub = WebhookSubscription(user_id=1, tenant_id=1, url="https://8.8.8.8/a", events="import.completed", secret="s")
    db_session.add(sub)
    db_session.commit()
    assert client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook", "events": ["import.completed"]}).status_code == 403
    assert client.put(f"/api/v1/webhooks/{sub.id}", json={"url": "https://8.8.4.4/b"}).status_code == 403
    assert client.delete(f"/api/v1/webhooks/{sub.id}").status_code == 200  # removing one is still fine


def test_write_api_key_cannot_issue_db_credentials(client, write_key_ctx):
    with patch.object(dbc, "create_db_credential", side_effect=AssertionError("must not create a role")):
        res = client.post("/api/v1/db-credentials/", json={"name": "x", "access_level": "readwrite"})
    assert res.status_code == 403


# ── Database credentials: Postgres-side expiry, connection cap, naive timestamps ─

class _Recorder:
    def __init__(self):
        self.statements = []

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params or {}))

    def commit(self):
        pass


def test_db_role_is_created_with_valid_until_and_a_connection_limit():
    rec = _Recorder()
    until = datetime(2027, 2, 1, 12, 0, tzinfo=timezone.utc)
    with patch.object(dbc, "engine", rec):
        dbc.create_db_credential("tenant_claudius", "read", until)
    sql, params = rec.statements[0]
    assert sql.startswith('CREATE ROLE "tld_tenant_claudius_') and "LOGIN PASSWORD :pw" in sql
    assert f"CONNECTION LIMIT {dbc.CONNECTION_LIMIT}" in sql and "VALID UNTIL :until" in sql
    assert params["until"] == "2027-02-01T12:00:00+00:00" and params["pw"] not in sql


def test_db_role_without_expiry_has_no_valid_until():
    rec = _Recorder()
    with patch.object(dbc, "engine", rec):
        dbc.create_db_credential("tenant_claudius", "read", None)
    sql, params = rec.statements[0]
    assert "VALID UNTIL" not in sql and "until" not in params


def test_issue_route_passes_the_expiry_to_postgres(client, db_session):
    calls = []

    def fake_create(schema, level, expires_at):
        calls.append(expires_at)
        return {"username": "tld_public_abcd1234", "password": "pw", "host": "h", "port": 5432,
                "database": "d", "schema": schema, "connection_string": "postgresql://..."}

    with patch.object(dbc, "create_db_credential", fake_create):
        res = client.post("/api/v1/db-credentials/", json={"name": "psql", "expires_in_days": 30})
    assert res.status_code == 201, res.text
    assert calls[0] is not None and timedelta(days=29) < calls[0] - datetime.now(timezone.utc) <= timedelta(days=30)
    assert res.json()["expires_at"].endswith("+00:00")
    row = db_session.get(DbCredential, res.json()["id"])
    assert row.expires_at.tzinfo is None  # naive column holds UTC


def test_listing_revokes_expired_credentials_stored_as_naive_utc(client, db_session):
    """Postgres returns `timestamp without time zone` as naive; comparing it with an aware now() used to raise."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None)
    db_session.add_all([
        DbCredential(user_id=1, tenant_id=1, pg_username="tld_old", name="old", access_level="read", expires_at=past),
        DbCredential(user_id=1, tenant_id=1, pg_username="tld_new", name="new", access_level="read", expires_at=future),
    ])
    db_session.commit()
    dropped = []
    with patch.object(dbc, "revoke_db_credential", dropped.append):
        res = client.get("/api/v1/db-credentials/")
    assert res.status_code == 200, res.text
    active = {c["pg_username"]: c["is_active"] for c in res.json()}
    assert active == {"tld_old": False, "tld_new": True} and dropped == ["tld_old"]


# ── CSRF: Origin check on unsafe methods ─────────────────────────────────────

HOOK = {"url": "https://8.8.8.8/hook", "events": ["import.completed"]}


@pytest.mark.parametrize("headers", [
    {"Origin": "https://money-demo.markcheli.com"},
    {"Origin": "https://evil.example"},
    {"Origin": "null"},
    {"Referer": "https://evil.example/page"},
])
def test_cross_origin_writes_are_refused(client, headers):
    res = client.post("/api/v1/webhooks/", json=HOOK, headers=headers)
    assert res.status_code == 403 and res.json()["detail"] == "Cross-origin request refused"


@pytest.mark.parametrize("headers", [
    {},  # non-browser clients send neither header
    {"Origin": "http://testserver"},  # same host as the request
    {"Origin": "http://localhost:5173"},  # FINANCE_CORS_ORIGINS
    {"Referer": "http://testserver/settings"},
    {"Origin": "https://evil.example", "X-API-Key": "k"},  # no cookie involved; CORS guards the header
])
def test_same_origin_and_non_browser_writes_pass(client, headers):
    res = client.post("/api/v1/webhooks/", json=HOOK, headers=headers)
    assert res.status_code == 201, res.text


def test_cross_origin_reads_are_not_affected(client):
    assert client.get("/api/v1/webhooks/", headers={"Origin": "https://evil.example"}).status_code == 200


# ── Invalid API keys are throttled per address ───────────────────────────────

def test_invalid_api_keys_are_throttled_but_valid_ones_are_not(db_session):
    from app.middleware.rate_limit import invalid_api_key_limiter
    from tests.test_api.test_security import _make_key, _request
    from app.models.tenant import Tenant, TenantMembership
    from app.models.user import User

    user = User(email="k2@test.dev", password_hash="", display_name="K", auth_provider="local",
                is_admin=False, is_active=True, status="active")
    tenant = Tenant(slug="t_k2", display_name="K", schema_name="tenant_k2abcd", is_active=True)
    db_session.add_all([user, tenant])
    db_session.flush()
    db_session.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner", is_default=True))
    db_session.commit()
    raw = _make_key(db_session, user, tenant, "read")

    invalid_api_key_limiter._requests.clear()
    codes = []
    with patch.object(dependencies, "SessionLocal", sessionmaker(bind=db_session.get_bind())), \
         patch.object(invalid_api_key_limiter, "requests_per_hour", 3):
        for _ in range(4):
            try:
                dependencies.get_tenant_context(_request("GET", {"X-API-Key": "tld_wrong"}))
            except HTTPException as e:
                codes.append(e.status_code)
        ctx = dependencies.get_tenant_context(_request("GET", {"X-API-Key": raw}))
    invalid_api_key_limiter._requests.clear()
    assert codes == [401, 401, 401, 429]
    assert ctx.user_id == user.id
