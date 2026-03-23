"""Audit logging service — records security-relevant events."""
import json
from typing import Optional

from app.database import SessionLocal
from app.models.audit_log import AuditLog


def log_event(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[int] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Record an audit event.

    Actions: login, login_failed, logout, user_approved, tenant_created,
             data_import, admin_action
    Resource types: user, tenant, w2_record, retirement_account, import_session, etc.
    """
    db = SessionLocal()
    try:
        db.add(AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
        ))
        db.commit()
    finally:
        db.close()
