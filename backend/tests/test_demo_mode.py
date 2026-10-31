"""DEMO-001: the public demo is read-only, signs visitors in as the persona, and refuses real data."""
import re

import pytest
from fastapi.routing import APIRoute

from app.config import settings
from app.demo import ALLOWED_WRITES, check_demo_database, check_demo_settings, write_allowed
from app.main import v1
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_user_email", "claudius@tallied.dev")


def _api_routes(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):  # an included router
            yield from _api_routes(r.original_router.routes)


def _write_routes():
    for r in _api_routes(v1.routes):
        for m in r.methods - {"GET", "HEAD", "OPTIONS"}:
            yield m, re.sub(r"\{[^}]+\}", "1", r.path)


def test_only_sign_in_and_calculations_may_write():
    assert write_allowed("GET", "/api/v1/accounts/")
    assert write_allowed("POST", "/api/v1/auth/demo")
    assert write_allowed("POST", "/api/v1/plans/3/what-if")
    assert write_allowed("POST", "/api/v1/plans/3/sprint")
    assert write_allowed("POST", "/api/v1/admin/query")
    assert not write_allowed("POST", "/api/v1/auth/login")
    assert not write_allowed("POST", "/api/v1/api-keys/")
    assert not write_allowed("PUT", "/api/v1/plans/3")
    assert not write_allowed("POST", "/api/v1/plans/3/what-if/extra")
    assert not write_allowed("DELETE", "/api/v1/transactions/x")


def test_every_write_route_is_refused_in_demo_mode(client, demo):
    allowed = [(m, p) for m, p in _write_routes() if any(a.match(p) for a in ALLOWED_WRITES)]
    assert {p for _, p in allowed} == {"/auth/demo", "/auth/logout", "/auth/refresh", "/plans/1/what-if",
                                       "/plans/1/sprint", "/admin/query"}
    refused = [(m, p) for m, p in _write_routes() if (m, p) not in allowed]
    assert len(refused) > 60
    for method, path in refused:
        res = client.request(method, f"/api/v1{path}", json={})
        assert res.status_code == 403 and res.json().get("demo") is True, (method, path, res.status_code)


def test_reads_work_and_pages_are_not_indexed(client, demo):
    res = client.get("/api/v1/accounts/")
    assert res.status_code == 200
    assert res.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert client.get("/api/v1/auth/config").json()["demo_mode"] is True


def test_outside_demo_mode_nothing_changes(client):
    assert client.post("/api/v1/accounts/", json={"id": "x", "name": "X", "institution": "Bank", "account_type": "cash", "display_group": "Cash"}).status_code == 201
    assert "X-Robots-Tag" not in client.get("/api/v1/accounts/").headers
    assert client.post("/api/v1/auth/demo").status_code == 404
    cfg = client.get("/api/v1/auth/config").json()
    assert cfg["demo_mode"] is False and cfg["demo_url"] is None


def test_the_real_deployment_links_to_the_demo(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_url", "https://money-demo.example.com")
    assert client.get("/api/v1/auth/config").json()["demo_url"] == "https://money-demo.example.com"


def test_demo_sign_in_issues_a_session_for_the_persona(client, db_session, demo):
    assert client.post("/api/v1/auth/demo").status_code == 503  # no persona yet: the rebuild is running
    user = User(email="claudius@tallied.dev", display_name="Claudius Banks", auth_provider="local")
    tenant = Tenant(slug="tenant_claudius", display_name="Claudius's Finances", schema_name="tenant_claudius")
    db_session.add_all([user, tenant])
    db_session.flush()
    db_session.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner", is_default=True))
    db_session.commit()

    res = client.post("/api/v1/auth/demo")
    assert res.status_code == 200, res.text
    assert res.json()["user"]["display_name"] == "Claudius Banks"
    assert "tallied_token" in res.cookies


def test_demo_refuses_a_database_with_real_users(db_session):
    db_session.add(User(email="claudius@tallied.dev", display_name="Claudius Banks", auth_provider="local"))
    db_session.commit()
    check_demo_database(db_session)  # personas only: fine
    db_session.add(User(email="someone@example.com", display_name="Someone", auth_provider="google"))
    db_session.commit()
    with pytest.raises(RuntimeError, match="real users"):
        check_demo_database(db_session)


def test_demo_refuses_ai_and_sso_secrets(monkeypatch):
    check_demo_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-x")
    with pytest.raises(RuntimeError, match="ANTHROPIC"):
        check_demo_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "google_client_id", "abc")
    with pytest.raises(RuntimeError, match="SSO"):
        check_demo_settings()


def test_demo_uses_the_seeded_price_and_never_fetches(db_session, demo, monkeypatch):
    from datetime import date, timedelta
    from decimal import Decimal

    from app.models.investment import StockPrice
    from app.services import stock_price

    db_session.add(StockPrice(symbol="MSFT", price_date=date.today() - timedelta(days=1), close_price=Decimal("410"),
                              source="seed"))
    db_session.commit()
    monkeypatch.setattr(stock_price, "fetch_price", lambda symbol: pytest.fail("the demo fetched a live price"))
    assert stock_price.get_or_fetch_price(db_session, "MSFT") == 410
    assert db_session.query(StockPrice).count() == 1
