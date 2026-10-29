"""Encryption at rest for provider credentials (SEC-3).

Values are stored as "enc:<fernet token>". `decrypt_secret` passes through
values without the prefix so rows written before encryption keep working
until the migration re-encrypts them.

The key comes from FINANCE_CREDENTIAL_KEY (a Fernet key: 32 url-safe base64
bytes). Outside dev mode the key is required; in dev mode a key is derived
from FINANCE_SECRET_KEY so local setups need no extra configuration.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

PREFIX = "enc:"


class CredentialKeyMissing(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.credential_key.strip()
    if not key:
        if not settings.dev_mode:
            raise CredentialKeyMissing(
                "FINANCE_CREDENTIAL_KEY must be set outside dev mode. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


def reset_key_cache() -> None:
    """For tests that change settings."""
    _fernet.cache_clear()


def is_encrypted(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(PREFIX)


def encrypt_secret(plain: str) -> str:
    return PREFIX + _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(stored: str) -> str:
    if not is_encrypted(stored):
        return stored
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored credential cannot be decrypted with the current FINANCE_CREDENTIAL_KEY") from exc
