"""API key writes: create and revoke, with the caller's own permission level as the ceiling."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import PERMISSION_ORDER, TenantContext
from app.models.api_key import ApiKey


class ApiKeyError(ValueError):
    """A request the caller may not make; `status` is the HTTP status the route should answer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def create_api_key(db: Session, ctx: TenantContext, name: str, permissions: str) -> tuple[ApiKey, str]:
    """Create a key for the caller's user and tenant. Returns the row and the raw key (shown once).

    A key never gets more than the credential that created it: a write key cannot mint an admin key.
    """
    if permissions not in PERMISSION_ORDER:
        raise ApiKeyError("Permissions must be read, write, or admin")
    if PERMISSION_ORDER[permissions] > PERMISSION_ORDER.get(ctx.permissions, 0):
        raise ApiKeyError(f"An API key with {ctx.permissions} permission cannot create a {permissions} key", 403)

    raw_key = ApiKey.generate_key()
    api_key = ApiKey(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        name=name,
        key_prefix=raw_key[:12],
        key_hash=ApiKey.hash_key(raw_key),
        permissions=permissions,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key, raw_key


def revoke_api_key(db: Session, ctx: TenantContext, key_id: int) -> bool:
    """Deactivate one of the caller's keys. False when there is no such key."""
    api_key = db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == ctx.user_id)
    ).scalar_one_or_none()
    if not api_key:
        return False
    api_key.is_active = False
    db.commit()
    return True
