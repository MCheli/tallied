"""SimpleFIN Bridge integration — connect, sync balances + transactions.

SimpleFIN is dramatically simpler than Monarch:
- One-time setup token (base64 string with embedded claim URL) → POST → permanent
  access URL with basic-auth credentials
- One endpoint: GET {access_url}/accounts returns balances + recent transactions
- No MFA, no session refresh — the access URL is the credential
"""
import asyncio
import base64
import logging
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db, get_tenant_context, TenantContext
from app.models.simplefin_link import SimpleFinAccountConfig, SimpleFinLink
from app.models.sync_job import SyncJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simplefin", tags=["simplefin"])


# ── Request schemas ──────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    setup_token: str


class AccountConfigUpdate(BaseModel):
    sync_balances: Optional[bool] = None
    sync_transactions: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _claim_setup_token(setup_token: str) -> str:
    """Exchange a SimpleFIN setup token for a permanent access URL.

    The token is a base64-encoded claim URL. POST to that URL (single-use)
    returns the access URL as plain text — basic-auth creds embedded.
    """
    raw = setup_token.strip()
    try:
        claim_url = base64.b64decode(raw).decode().strip()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Setup token is not valid base64. Paste the entire token from SimpleFIN.",
        )
    if not claim_url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Decoded setup token doesn't look like a claim URL.",
        )

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(claim_url, headers={"Content-Length": "0"}) as r:
            body = (await r.text()).strip()
            if r.status != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"SimpleFIN rejected the setup token ({r.status}): {body[:200]}",
                )
            if not body.startswith("https://"):
                raise HTTPException(
                    status_code=400,
                    detail="SimpleFIN response wasn't an access URL — token may already be used.",
                )
            return body


async def _fetch_accounts(access_url: str) -> dict:
    p = urlparse(access_url)
    if not p.username or not p.password:
        raise HTTPException(
            status_code=401,
            detail="Stored access URL is missing credentials. Reconnect SimpleFIN.",
        )
    end = int(datetime.utcnow().timestamp())
    start = end - 45 * 24 * 3600  # default 45-day window
    clean = f"{p.scheme}://{p.hostname}{p.path}/accounts?start-date={start}&end-date={end}&pending=1"
    auth = aiohttp.BasicAuth(p.username, p.password)
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(clean, auth=auth, headers={"User-Agent": "Tallied/1.0"}) as r:
            if r.status in (401, 403):
                raise HTTPException(
                    status_code=401,
                    detail="SimpleFIN access URL was revoked. Re-claim a fresh setup token.",
                )
            r.raise_for_status()
            return await r.json()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/connect")
async def connect_simplefin(
    body: ConnectRequest,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Claim a SimpleFIN setup token, store the access URL, register accounts."""
    access_url = await _claim_setup_token(body.setup_token)

    # Validate by actually pulling accounts.
    try:
        data = await _fetch_accounts(access_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch accounts: {e}")

    # Upsert SimpleFinLink — only one per tenant.
    existing = db.query(SimpleFinLink).first()
    if existing:
        existing.access_url = access_url
        existing.updated_at = datetime.utcnow()
        link = existing
    else:
        link = SimpleFinLink(access_url=access_url)
        db.add(link)
    db.flush()

    sf_accounts = data.get("accounts", []) or []
    existing_cfgs = {
        c.simplefin_account_id: c
        for c in db.query(SimpleFinAccountConfig).filter(
            SimpleFinAccountConfig.simplefin_link_id == link.id
        ).all()
    }

    result_accounts = []
    for acct in sf_accounts:
        acct_id = str(acct.get("id", ""))
        acct_name = acct.get("name", "Unknown")
        org = acct.get("org") or {}
        institution = org.get("name", "") if isinstance(org, dict) else ""

        if acct_id in existing_cfgs:
            cfg = existing_cfgs[acct_id]
            cfg.account_name = acct_name
            cfg.institution = institution
        else:
            cfg = SimpleFinAccountConfig(
                simplefin_link_id=link.id,
                simplefin_account_id=acct_id,
                account_name=acct_name,
                institution=institution,
                sync_balances=True,
                sync_transactions=False,
            )
            db.add(cfg)

        result_accounts.append({
            "simplefin_account_id": acct_id,
            "account_name": acct_name,
            "institution": institution,
        })

    db.commit()

    return {
        "connected": True,
        "accounts_found": len(result_accounts),
        "accounts": result_accounts,
        "warnings": data.get("errors") or [],
    }


@router.post("/refresh-credentials")
async def refresh_simplefin_credentials(
    body: ConnectRequest,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Replace the stored access URL with a fresh one without disconnecting accounts."""
    link = db.query(SimpleFinLink).first()
    if not link:
        raise HTTPException(
            status_code=404,
            detail="No SimpleFIN connection to refresh — use Connect instead.",
        )
    new_access_url = await _claim_setup_token(body.setup_token)
    try:
        await _fetch_accounts(new_access_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"New access URL failed validation: {e}")

    link.access_url = new_access_url
    link.updated_at = datetime.utcnow()
    db.commit()
    return {"refreshed": True}


@router.get("/status")
def simplefin_status(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    link = db.query(SimpleFinLink).first()
    if not link:
        return {"connected": False}
    return {
        "connected": True,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/accounts")
def list_simplefin_accounts(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    link = db.query(SimpleFinLink).first()
    if not link:
        return []
    configs = db.query(SimpleFinAccountConfig).filter(
        SimpleFinAccountConfig.simplefin_link_id == link.id
    ).all()
    return [
        {
            "id": c.id,
            "simplefin_account_id": c.simplefin_account_id,
            "account_name": c.account_name,
            "account_type": c.account_type,
            "institution": c.institution,
            "sync_balances": c.sync_balances,
            "sync_transactions": c.sync_transactions,
            "local_account_id": c.local_account_id,
        }
        for c in configs
    ]


@router.put("/accounts/{config_id}")
def update_simplefin_account(
    config_id: int,
    body: AccountConfigUpdate,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    cfg = db.query(SimpleFinAccountConfig).filter(SimpleFinAccountConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Account config not found")
    if body.sync_balances is not None:
        cfg.sync_balances = body.sync_balances
    if body.sync_transactions is not None:
        cfg.sync_transactions = body.sync_transactions
    db.commit()
    return {"updated": True}


@router.post("/sync", status_code=202)
async def sync_simplefin(
    response: Response,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Enqueue a SimpleFIN sync. Returns 202 with a job_id (same pattern as Monarch)."""
    from app.services.sync_scheduler import (
        create_job_row, notify_sync_request, run_sync_with_job,
    )

    link = db.query(SimpleFinLink).first()
    if not link:
        response.status_code = 200
        return {"status": "skipped", "detail": "No SimpleFIN connection"}

    job_id, created = create_job_row(
        ctx.tenant_schema, provider="simplefin", trigger="manual",
    )
    if created:
        role = os.environ.get("APP_ROLE", "").lower()
        if role == "web":
            try:
                notify_sync_request(ctx.tenant_schema, "simplefin")
            except Exception:
                logger.exception("Failed to NOTIFY scheduler — claim_orphan_jobs will pick it up")
        else:
            asyncio.create_task(
                run_sync_with_job(ctx.tenant_schema, job_id, "simplefin")
            )
    return {"job_id": job_id, "status": "running", "queued": created}


@router.get("/sync/status")
def simplefin_sync_status(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Most recent SimpleFIN sync job for this tenant."""
    job = (
        db.query(SyncJob)
        .filter(SyncJob.provider == "simplefin")
        .order_by(SyncJob.started_at.desc())
        .first()
    )
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
def disconnect_simplefin(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    link = db.query(SimpleFinLink).first()
    if not link:
        raise HTTPException(status_code=404, detail="No SimpleFIN connection found")
    db.delete(link)
    db.commit()
    return {"disconnected": True}
