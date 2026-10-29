"""SimpleFIN Bridge connection routes: connect, configure accounts, sync, disconnect.

The provider logic lives in app/services/providers/simplefin.py; this module
only stores the (encrypted) access URL and the per-account sync configuration.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import TenantContext, get_tenant_context, get_tenant_db, require_permission
from app.models.simplefin_link import SimpleFinAccountConfig, SimpleFinLink
from app.models.sync_job import SyncJob
from app.services.crypto import encrypt_secret
from app.services.providers import get_provider
from app.services.providers.base import KIND_TO_TYPE_AND_GROUP, TYPE_TO_GROUP, ProviderError
from app.services.providers.simplefin import SimpleFinProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simplefin", tags=["simplefin"])

# Keep references to in-process sync tasks so the event loop cannot drop them mid-run.
_background_syncs: set[asyncio.Task] = set()

ACCOUNT_TYPES = sorted(TYPE_TO_GROUP)


def _provider() -> SimpleFinProvider:
    return get_provider("simplefin")  # type: ignore[return-value]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConnectRequest(BaseModel):
    setup_token: str


class AccountConfigUpdate(BaseModel):
    sync_balances: bool | None = None
    sync_transactions: bool | None = None
    account_type: str | None = None


def _serialize_config(c: SimpleFinAccountConfig) -> dict:
    return {
        "id": c.id,
        "simplefin_account_id": c.simplefin_account_id,
        "account_name": c.account_name,
        "account_type": c.account_type,
        "display_group": TYPE_TO_GROUP.get(c.account_type or "", None),
        "institution": c.institution,
        "sync_balances": c.sync_balances,
        "sync_transactions": c.sync_transactions,
        "local_account_id": c.local_account_id,
    }


async def _claim_and_validate(setup_token: str):
    provider = _provider()
    try:
        access_url = await provider.claim_setup_token(setup_token)
        snapshot = await provider.fetch(access_url)
    except ProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach SimpleFIN: {e}")
    return access_url, snapshot


@router.post("/connect")
async def connect_simplefin(
    body: ConnectRequest,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(require_permission("write")),
):
    """Claim a SimpleFIN setup token, store the access URL encrypted, register accounts with a type."""
    access_url, snapshot = await _claim_and_validate(body.setup_token)

    link = db.query(SimpleFinLink).first()
    if link:
        link.access_url = encrypt_secret(access_url)
        link.updated_at = _utcnow()
    else:
        link = SimpleFinLink(access_url=encrypt_secret(access_url))
        db.add(link)
    db.flush()

    existing = {
        c.simplefin_account_id: c
        for c in db.query(SimpleFinAccountConfig).filter(SimpleFinAccountConfig.simplefin_link_id == link.id).all()
    }
    result_accounts = []
    for acct in snapshot.accounts:
        cfg = existing.get(acct.id)
        if cfg:
            cfg.account_name = acct.name
            cfg.institution = acct.institution
            if not cfg.account_type:
                cfg.account_type = KIND_TO_TYPE_AND_GROUP[acct.kind][0]
        else:
            cfg = SimpleFinAccountConfig(
                simplefin_link_id=link.id,
                simplefin_account_id=acct.id,
                account_name=acct.name,
                institution=acct.institution,
                account_type=KIND_TO_TYPE_AND_GROUP[acct.kind][0],
                sync_balances=True,
                sync_transactions=False,
            )
            db.add(cfg)
        result_accounts.append({
            "simplefin_account_id": acct.id,
            "account_name": acct.name,
            "institution": acct.institution,
            "account_type": cfg.account_type,
        })

    db.commit()
    return {
        "connected": True,
        "accounts_found": len(result_accounts),
        "accounts": result_accounts,
        "warnings": snapshot.warnings,
    }


@router.post("/refresh-credentials")
async def refresh_simplefin_credentials(
    body: ConnectRequest,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(require_permission("write")),
):
    """Replace the stored access URL with a fresh one without disconnecting accounts."""
    link = db.query(SimpleFinLink).first()
    if not link:
        raise HTTPException(status_code=404, detail="No SimpleFIN connection to refresh; use Connect instead.")
    access_url, _snapshot = await _claim_and_validate(body.setup_token)
    link.access_url = encrypt_secret(access_url)
    link.updated_at = _utcnow()
    db.commit()
    return {"refreshed": True}


@router.get("/status")
def simplefin_status(db: Session = Depends(get_tenant_db), ctx: TenantContext = Depends(get_tenant_context)):
    link = db.query(SimpleFinLink).first()
    if not link:
        return {"connected": False}
    return {
        "connected": True,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/accounts")
def list_simplefin_accounts(db: Session = Depends(get_tenant_db), ctx: TenantContext = Depends(get_tenant_context)):
    link = db.query(SimpleFinLink).first()
    if not link:
        return []
    configs = db.query(SimpleFinAccountConfig).filter(SimpleFinAccountConfig.simplefin_link_id == link.id).all()
    return [_serialize_config(c) for c in configs]


@router.get("/account-types")
def simplefin_account_types():
    """Account types a synced account may be assigned, with the display group each implies."""
    return [{"account_type": t, "display_group": g} for t, g in sorted(TYPE_TO_GROUP.items())]


@router.put("/accounts/{config_id}")
def update_simplefin_account(
    config_id: int,
    body: AccountConfigUpdate,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(require_permission("write")),
):
    cfg = db.query(SimpleFinAccountConfig).filter(SimpleFinAccountConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Account config not found")
    if body.sync_balances is not None:
        cfg.sync_balances = body.sync_balances
    if body.sync_transactions is not None:
        cfg.sync_transactions = body.sync_transactions
    if body.account_type is not None:
        if body.account_type not in TYPE_TO_GROUP:
            raise HTTPException(status_code=400, detail=f"account_type must be one of {ACCOUNT_TYPES}")
        cfg.account_type = body.account_type
    db.commit()
    return _serialize_config(cfg)


@router.post("/sync", status_code=202)
async def sync_simplefin(
    response: Response,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(require_permission("write")),
):
    """Enqueue a SimpleFIN sync. Returns 202 with a job_id; poll /sync/status."""
    from app.services.sync_scheduler import create_job_row, notify_sync_request, run_sync_with_job

    link = db.query(SimpleFinLink).first()
    if not link:
        response.status_code = 200
        return {"status": "skipped", "detail": "No SimpleFIN connection"}

    job_id, created = create_job_row(ctx.tenant_schema, provider="simplefin", trigger="manual")
    if created:
        role = os.environ.get("APP_ROLE", "").lower()
        if role == "web":
            try:
                notify_sync_request(ctx.tenant_schema, "simplefin")
            except Exception:
                logger.exception("Failed to NOTIFY scheduler; claim_orphan_jobs will pick it up")
        else:
            task = asyncio.create_task(run_sync_with_job(ctx.tenant_schema, job_id, "simplefin"))
            _background_syncs.add(task)
            task.add_done_callback(_background_syncs.discard)
    return {"job_id": job_id, "status": "running", "queued": created}


@router.get("/sync/status")
def simplefin_sync_status(db: Session = Depends(get_tenant_db), ctx: TenantContext = Depends(get_tenant_context)):
    """Most recent SimpleFIN sync job for this tenant."""
    job = db.query(SyncJob).filter(SyncJob.provider == "simplefin").order_by(SyncJob.started_at.desc()).first()
    if not job:
        return {"job_id": None, "status": "none"}
    return {
        "job_id": job.id,
        "status": job.status,
        "trigger": job.trigger,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "balances_synced": job.balances_synced or 0,
        "txn_added": job.txn_added or 0,
        "txn_updated": job.txn_updated or 0,
        "error": job.error,
    }


@router.delete("/disconnect")
def disconnect_simplefin(db: Session = Depends(get_tenant_db), ctx: TenantContext = Depends(require_permission("write"))):
    link = db.query(SimpleFinLink).first()
    if not link:
        raise HTTPException(status_code=404, detail="No SimpleFIN connection found")
    db.delete(link)
    db.commit()
    return {"disconnected": True}
