"""The browser session lasts 30 days from the last visit: /auth/me renews it from the refresh cookie.

Before 2026-11 the refresh cookie only reached /auth/refresh, and the frontend only called that when a
localStorage flag said a session existed, which Google sign-in never set. So a Google session ended with
the 4h access token, and the iPhone Home Screen app went back to Google sign-in several times a day.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.api.auth import ACCESS_TOKEN_EXPIRE_HOURS, REFRESH_TOKEN_EXPIRE_DAYS
from app.config import settings
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User


@pytest.fixture
def member(db_session):
    user = User(email="session@test.dev", password_hash="", display_name="Session", auth_provider="google",
                is_admin=False, is_active=True, status="active")
    tenant = Tenant(slug="tenant_session", display_name="Session", schema_name="tenant_session1", is_active=True)
    db_session.add_all([user, tenant])
    db_session.flush()
    db_session.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner", is_default=True))
    db_session.commit()
    return user


def _refresh_for(user, days=1, token_type="refresh"):
    return jwt.encode(
        {"sub": str(user.id), "type": token_type, "exp": datetime.now(timezone.utc) + timedelta(days=days)},
        settings.secret_key, algorithm="HS256",
    )


def _set_cookies(res) -> dict[str, list[str]]:
    """Set-Cookie headers by cookie name, lower-cased."""
    out: dict[str, list[str]] = {}
    for header in res.headers.get_list("set-cookie"):
        out.setdefault(header.split("=", 1)[0], []).append(header.lower())
    return out


def test_me_renews_a_lapsed_session_from_the_refresh_cookie(client, member):
    client.cookies.set("tallied_refresh", _refresh_for(member), path="/api/v1/auth")
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "session@test.dev"
    cookies = _set_cookies(res)
    assert "tallied_token" in cookies and "tallied_refresh" in cookies


def test_renewed_cookies_are_server_set_http_only_and_last_30_days(client, member):
    client.cookies.set("tallied_refresh", _refresh_for(member), path="/api/v1/auth")
    cookies = _set_cookies(client.get("/api/v1/auth/me"))
    access = cookies["tallied_token"][0]
    assert f"max-age={ACCESS_TOKEN_EXPIRE_HOURS * 3600}" in access
    assert "httponly" in access and "samesite=lax" in access
    refresh = next(c for c in cookies["tallied_refresh"] if "path=/api/v1/auth;" in c or c.endswith("path=/api/v1/auth"))
    assert f"max-age={REFRESH_TOKEN_EXPIRE_DAYS * 86400}" in refresh
    assert REFRESH_TOKEN_EXPIRE_DAYS == 30
    assert "httponly" in refresh and "samesite=lax" in refresh


def test_renewal_retires_the_cookie_at_the_old_refresh_path(client, member):
    client.cookies.set("tallied_refresh", _refresh_for(member), path="/api/v1/auth/refresh")
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    refresh = _set_cookies(res)["tallied_refresh"]
    assert any("path=/api/v1/auth/refresh" in c and "max-age=0" in c for c in refresh)
    assert any("path=/api/v1/auth;" in c or c.endswith("path=/api/v1/auth") for c in refresh)


def test_me_with_no_cookies_is_signed_out(client):
    res = client.get("/api/v1/auth/me")
    assert res.json() == {"user": None, "authenticated": False}
    assert "tallied_token" not in _set_cookies(res)


@pytest.mark.parametrize("is_active,status", [(False, "active"), (True, "suspended"), (True, "pending_approval")])
def test_me_does_not_renew_for_users_who_may_not_sign_in(client, db_session, member, is_active, status):
    member.is_active = is_active
    member.status = status
    db_session.commit()
    client.cookies.set("tallied_refresh", _refresh_for(member), path="/api/v1/auth")
    res = client.get("/api/v1/auth/me")
    assert res.json()["authenticated"] is False
    assert "tallied_token" not in _set_cookies(res)


def test_me_does_not_renew_from_an_access_token_or_an_expired_refresh(client, member):
    client.cookies.set("tallied_refresh", _refresh_for(member, token_type="access"), path="/api/v1/auth")
    assert client.get("/api/v1/auth/me").json()["authenticated"] is False
    client.cookies.clear()
    client.cookies.set("tallied_refresh", _refresh_for(member, days=-1), path="/api/v1/auth")
    assert client.get("/api/v1/auth/me").json()["authenticated"] is False


def test_logout_clears_the_refresh_cookie_at_both_paths(client):
    cookies = _set_cookies(client.post("/api/v1/auth/logout"))
    refresh = cookies["tallied_refresh"]
    assert any("path=/api/v1/auth/refresh" in c for c in refresh)
    assert any("path=/api/v1/auth;" in c or c.endswith("path=/api/v1/auth") for c in refresh)
    assert all("max-age=0" in c for c in refresh)
