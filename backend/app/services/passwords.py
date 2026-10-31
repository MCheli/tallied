"""
Password hashing — argon2id, with a transparent upgrade from the legacy SHA-256 format.

New hashes are argon2id (`$argon2id$...`, salted, memory-hard; argon2-cffi's RFC 9106
low-memory profile: 64 MiB, t=3, p=4). Before this module, local users were stored as
a bare unsalted SHA-256 hex digest (64 lowercase hex characters). Those still verify, and
`verify_and_upgrade` rewrites them as argon2id on the first successful login, so nobody is
locked out. Google-only users have an empty hash and never verify.

API keys are not passwords: they are high-entropy random tokens hashed with a peppered
HMAC-SHA-256 in app/models/api_key.py, which is the right tool for them.
"""
import hashlib
import hmac
import logging
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.models.user import User

logger = logging.getLogger("tallied")

ARGON2ID_PREFIX = "$argon2id$"
_LEGACY_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ph = PasswordHasher()  # argon2id, RFC 9106 low-memory profile


def hash_password(password: str) -> str:
    return _ph.hash(password)


def _is_legacy(stored: str) -> bool:
    return bool(_LEGACY_SHA256.match(stored))


def _verify_legacy(password: str, stored: str) -> bool:
    # Only reached for hashes written before argon2id; kept so those users can log in once and be upgraded.
    digest = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(digest, stored)


def verify_password(password: str, stored: str) -> bool:
    """True when `password` matches `stored`, in either the argon2id or the legacy SHA-256 format."""
    if not stored:
        return False  # Google-only users have no password
    if stored.startswith(ARGON2ID_PREFIX):
        try:
            return _ph.verify(stored, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as e:
            logger.warning("Unreadable argon2 password hash: %s", e)
            return False
    if _is_legacy(stored):
        return _verify_legacy(password, stored)
    logger.warning("Password hash in an unknown format; refusing login")
    return False


def needs_rehash(stored: str) -> bool:
    if not stored.startswith(ARGON2ID_PREFIX):
        return True
    return _ph.check_needs_rehash(stored)


def verify_and_upgrade(user: User, password: str) -> bool:
    """Verify the user's password; on success, rewrite a legacy or outdated hash as argon2id.

    Changes `user.password_hash` in the session; the caller commits.
    """
    stored = user.password_hash or ""
    if not verify_password(password, stored):
        return False
    if needs_rehash(stored):
        user.password_hash = hash_password(password)
        logger.info("Upgraded password hash to argon2id for user %s", user.id)
    return True
