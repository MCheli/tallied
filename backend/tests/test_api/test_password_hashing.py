"""Password hashing: argon2id for new hashes, legacy SHA-256 verified once and upgraded on login (CodeQL #13)."""
import hashlib

from app.models.user import User
from app.services.passwords import hash_password, needs_rehash, verify_and_upgrade, verify_password


def _legacy(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _user(db, email: str, password_hash: str, provider: str = "local") -> User:
    user = User(email=email, password_hash=password_hash, display_name="Claudius Banks", auth_provider=provider,
                is_admin=False, is_active=True, status="active")
    db.add(user)
    db.commit()
    return user


def _login(client, email: str, password: str):
    from app.middleware.rate_limit import login_limiter

    login_limiter._requests.clear()
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_new_hash_is_argon2id_and_round_trips():
    stored = hash_password("demo123")
    assert stored.startswith("$argon2id$")
    assert hash_password("demo123") != stored  # salted
    assert verify_password("demo123", stored)
    assert not verify_password("demo124", stored)
    assert not needs_rehash(stored)


def test_legacy_hash_verifies_and_needs_rehash():
    stored = _legacy("demo123")
    assert verify_password("demo123", stored)
    assert not verify_password("wrong", stored)
    assert needs_rehash(stored)


def test_empty_or_unknown_hash_never_verifies():
    assert not verify_password("", "")
    assert not verify_password("anything", "")
    assert not verify_password("demo123", "demo123")  # plaintext is not a format we accept
    assert not verify_password("demo123", "$argon2id$garbage")


def test_verify_and_upgrade_leaves_hash_alone_on_wrong_password():
    user = User(email="x@test.dev", password_hash=_legacy("demo123"))
    assert not verify_and_upgrade(user, "wrong")
    assert user.password_hash == _legacy("demo123")


def test_login_with_legacy_hash_upgrades_to_argon2id(client, db_session):
    user = _user(db_session, "legacy@test.dev", _legacy("demo123"))
    res = _login(client, "legacy@test.dev", "demo123")
    assert res.status_code == 200, res.text
    db_session.refresh(user)
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password("demo123", user.password_hash)
    # The upgraded hash still logs in
    assert _login(client, "legacy@test.dev", "demo123").status_code == 200


def test_login_with_argon2_hash_and_wrong_password(client, db_session):
    _user(db_session, "argon@test.dev", hash_password("demo123"))
    assert _login(client, "argon@test.dev", "demo123").status_code == 200
    assert _login(client, "argon@test.dev", "demo124").status_code == 401


def test_wrong_password_on_legacy_hash_fails_and_keeps_hash(client, db_session):
    user = _user(db_session, "legacy2@test.dev", _legacy("demo123"))
    assert _login(client, "legacy2@test.dev", "nope").status_code == 401
    db_session.refresh(user)
    assert user.password_hash == _legacy("demo123")


def test_google_only_user_cannot_password_login_and_is_untouched(client, db_session):
    user = _user(db_session, "google@test.dev", "", provider="google")
    assert _login(client, "google@test.dev", "").status_code == 401
    assert _login(client, "google@test.dev", "anything").status_code == 401
    db_session.refresh(user)
    assert user.password_hash == ""
