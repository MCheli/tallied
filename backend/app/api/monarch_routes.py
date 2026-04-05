"""
Monarch Money integration — connect, sync balances, sync transactions.

Mirrors the Plaid integration pattern but uses Monarch's API via the
monarchmoney Python package.
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db, get_tenant_context, TenantContext
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.monarch_link import MonarchAccountConfig, MonarchLink
from app.models.transaction import Transaction
from app.parsers.monarch import ACCOUNT_TYPE_MAP, DISPLAY_GROUP_MAP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monarch", tags=["monarch"])


# ── Request / response schemas ────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    email: str
    password: str = ""
    mfa_code: Optional[str] = None
    token: Optional[str] = None


class AccountConfigUpdate(BaseModel):
    sync_balances: Optional[bool] = None
    sync_transactions: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_monarch_client():
    """Create a MonarchMoney client instance with a browser-like User-Agent.

    Monarch's API sits behind Cloudflare, which blocks the default
    'MonarchMoneyAPI' User-Agent string as a bot.

    Also patches the GraphQL URL: Monarch rebranded from monarchmoney.com
    to monarch.com, and the old URL 301-redirects — stripping the
    Authorization header on redirect.
    """
    from monarchmoney import MonarchMoney, MonarchMoneyEndpoints

    # Patch the endpoint to the new domain so we skip the 301 redirect
    MonarchMoneyEndpoints.getGraphQL = staticmethod(lambda: "https://api.monarch.com/graphql")
    MonarchMoneyEndpoints.getLoginEndpoint = staticmethod(lambda: "https://api.monarch.com/auth/login/")

    mm = MonarchMoney()
    mm._headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    return mm


def _classify_account_type(monarch_type: str) -> tuple[str, str]:
    """Map Monarch account type to (account_type, display_group)."""
    key = monarch_type.lower().replace(" ", "_")
    acct_type = ACCOUNT_TYPE_MAP.get(key, "cash")
    display_group = DISPLAY_GROUP_MAP.get(acct_type, "Cash")
    return acct_type, display_group


def _extract_category(txn: dict) -> tuple[str, str]:
    """Extract category and category_group from a Monarch transaction."""
    cat = txn.get("category") or {}
    category = cat.get("name", "") if isinstance(cat, dict) else str(cat)
    group = ""
    if isinstance(cat, dict):
        grp = cat.get("group") or {}
        group = grp.get("name", "") if isinstance(grp, dict) else str(grp)
    return category, group


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/connect")
async def connect_monarch(
    body: ConnectRequest,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Authenticate with Monarch Money and store the session token.

    Supports three flows:
    1. email + password → normal login (may trigger MFA)
    2. email + password + mfa_code → MFA login
    3. email + token → direct token auth (bypasses login endpoint entirely)
    """
    from monarchmoney import RequireMFAException

    mm = _get_monarch_client()

    if body.token:
        # Direct token — skip login entirely
        # Strip "Token " prefix if user copied the full header value
        raw_token = body.token.strip()
        if raw_token.lower().startswith("token "):
            raw_token = raw_token[6:].strip()
        mm.set_token(raw_token)
        mm._headers["Authorization"] = f"Token {raw_token}"
    else:
        if not body.password:
            raise HTTPException(status_code=400, detail="Password or token is required")
        try:
            if body.mfa_code:
                await mm.multi_factor_authenticate(body.email, body.password, body.mfa_code)
            else:
                await mm.login(
                    body.email, body.password,
                    use_saved_session=False, save_session=False,
                )
        except RequireMFAException:
            return {"mfa_required": True, "detail": "Enter your MFA code to continue."}
        except Exception as e:
            msg = str(e)
            if "429" in msg:
                raise HTTPException(
                    status_code=429,
                    detail="Monarch rate-limited this IP. Wait 15-30 minutes before trying again.",
                )
            raise HTTPException(status_code=401, detail=f"Monarch login failed: {e}")

    token = mm.token
    if not token:
        raise HTTPException(status_code=401, detail="No session token received")

    # Fetch accounts immediately
    try:
        accounts_data = await mm.get_accounts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch accounts: {e}")

    # Upsert MonarchLink
    existing_link = db.query(MonarchLink).filter(MonarchLink.email == body.email).first()
    if existing_link:
        existing_link.token = token
        existing_link.updated_at = datetime.utcnow()
        link = existing_link
    else:
        link = MonarchLink(email=body.email, token=token)
        db.add(link)
    db.flush()

    # Sync account configs
    monarch_accounts = accounts_data.get("accounts", [])
    existing_configs = {
        c.monarch_account_id: c
        for c in db.query(MonarchAccountConfig).filter(
            MonarchAccountConfig.monarch_link_id == link.id
        ).all()
    }

    result_accounts = []
    for acct in monarch_accounts:
        acct_id = str(acct.get("id", ""))
        acct_name = acct.get("displayName") or acct.get("name", "Unknown")
        institution = ""
        inst = acct.get("institution") or {}
        if isinstance(inst, dict):
            institution = inst.get("name", "")

        raw_type = ""
        type_obj = acct.get("type") or {}
        if isinstance(type_obj, dict):
            raw_type = type_obj.get("name", "")
        elif isinstance(type_obj, str):
            raw_type = type_obj

        if acct_id in existing_configs:
            cfg = existing_configs[acct_id]
            cfg.account_name = acct_name
            cfg.account_type = raw_type
            cfg.institution = institution
        else:
            cfg = MonarchAccountConfig(
                monarch_link_id=link.id,
                monarch_account_id=acct_id,
                account_name=acct_name,
                account_type=raw_type,
                institution=institution,
                sync_balances=True,
                sync_transactions=False,
            )
            db.add(cfg)

        result_accounts.append({
            "monarch_account_id": acct_id,
            "account_name": acct_name,
            "account_type": raw_type,
            "institution": institution,
        })

    db.commit()

    return {
        "connected": True,
        "email": body.email,
        "accounts_found": len(result_accounts),
        "accounts": result_accounts,
    }


@router.get("/status")
def monarch_status(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Check if Monarch is connected."""
    link = db.query(MonarchLink).first()
    if not link:
        return {"connected": False}
    return {
        "connected": True,
        "email": link.email,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/accounts")
def list_monarch_accounts(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List Monarch account configs with sync settings."""
    link = db.query(MonarchLink).first()
    if not link:
        return []

    configs = db.query(MonarchAccountConfig).filter(
        MonarchAccountConfig.monarch_link_id == link.id
    ).all()

    return [
        {
            "id": c.id,
            "monarch_account_id": c.monarch_account_id,
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
def update_monarch_account(
    config_id: int,
    body: AccountConfigUpdate,
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update sync settings for a Monarch account."""
    cfg = db.query(MonarchAccountConfig).filter(MonarchAccountConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Account config not found")

    if body.sync_balances is not None:
        cfg.sync_balances = body.sync_balances
    if body.sync_transactions is not None:
        cfg.sync_transactions = body.sync_transactions

    db.commit()
    return {"updated": True}


@router.post("/sync-balances")
async def sync_monarch_balances(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Fetch current balances from Monarch for configured accounts."""
    link = db.query(MonarchLink).first()
    if not link:
        return {"synced": 0, "detail": "No Monarch connection"}

    mm = _get_monarch_client()
    mm.set_token(link.token)
    mm._headers["Authorization"] = f"Token {link.token}"

    try:
        accounts_data = await mm.get_accounts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monarch API error: {e}")

    configs = {
        c.monarch_account_id: c
        for c in db.query(MonarchAccountConfig).filter(
            MonarchAccountConfig.monarch_link_id == link.id,
            MonarchAccountConfig.sync_balances == True,  # noqa: E712
        ).all()
    }

    today = date.today()
    synced = 0

    for acct in accounts_data.get("accounts", []):
        acct_id = str(acct.get("id", ""))
        cfg = configs.get(acct_id)
        if not cfg:
            continue

        balance = acct.get("currentBalance")
        if balance is None:
            continue

        acct_name = acct.get("displayName") or acct.get("name", "Unknown")
        institution = ""
        inst = acct.get("institution") or {}
        if isinstance(inst, dict):
            institution = inst.get("name", "")

        raw_type = cfg.account_type or ""
        acct_type, display_group = _classify_account_type(raw_type)

        # Find or create local account
        local_id = cfg.local_account_id or f"monarch-{acct_id}"
        local_acct = db.query(Account).filter(Account.id == local_id).first()
        if not local_acct:
            local_acct = Account(
                id=local_id,
                name=acct_name,
                institution=institution,
                account_type=acct_type,
                display_group=display_group,
                include_in_nw=True,
            )
            db.add(local_acct)
            db.flush()

        if not cfg.local_account_id:
            cfg.local_account_id = local_id

        # Upsert balance snapshot
        bal_value = Decimal(str(balance))
        existing = db.query(BalanceSnapshot).filter(
            BalanceSnapshot.account_id == local_id,
            BalanceSnapshot.snapshot_date == today,
            BalanceSnapshot.source == "monarch",
        ).first()

        if existing:
            existing.balance = bal_value
        else:
            db.add(BalanceSnapshot(
                account_id=local_id,
                snapshot_date=today,
                balance=bal_value,
                source="monarch",
            ))
        synced += 1

        # Fetch full balance history for this account
        try:
            history = await mm.get_account_history(acct_id)
        except Exception:
            history = []

        history_cutoff = None  # Import all available history
        history_added = 0
        for snap in history:
            snap_date_str = snap.get("date", "")
            try:
                snap_date = datetime.strptime(snap_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            if history_cutoff and snap_date < history_cutoff:
                continue

            snap_balance = snap.get("signedBalance")
            if snap_balance is None:
                continue

            existing_snap = db.query(BalanceSnapshot).filter(
                BalanceSnapshot.account_id == local_id,
                BalanceSnapshot.snapshot_date == snap_date,
                BalanceSnapshot.source == "monarch",
            ).first()

            if not existing_snap:
                db.add(BalanceSnapshot(
                    account_id=local_id,
                    snapshot_date=snap_date,
                    balance=Decimal(str(snap_balance)),
                    source="monarch",
                ))
                history_added += 1

        if history_added > 0:
            logger.info("Backfilled %d balance snapshots for %s", history_added, acct_name)

    link.last_synced_at = datetime.utcnow()
    db.commit()

    return {"synced": synced}


@router.post("/sync")
async def sync_monarch_transactions(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Sync transactions from Monarch for configured accounts."""
    link = db.query(MonarchLink).first()
    if not link:
        return {"added": 0, "detail": "No Monarch connection"}

    mm = _get_monarch_client()
    mm.set_token(link.token)
    mm._headers["Authorization"] = f"Token {link.token}"

    # Fetch all transactions from Jan 2025 onward, paginating through results
    start_date = date(2000, 1, 1)  # Fetch all available history
    all_transactions: list[dict] = []
    offset = 0
    page_size = 100

    try:
        while True:
            txn_data = await mm.get_transactions(
                limit=page_size,
                offset=offset,
                start_date=start_date.isoformat(),
                end_date=date.today().isoformat(),
            )
            results = txn_data.get("allTransactions", {}).get("results", [])
            all_transactions.extend(results)
            total = txn_data.get("allTransactions", {}).get("totalCount", 0)
            offset += page_size
            if offset >= total or len(results) == 0:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monarch API error: {e}")

    configs = {
        c.monarch_account_id: c
        for c in db.query(MonarchAccountConfig).filter(
            MonarchAccountConfig.monarch_link_id == link.id,
            MonarchAccountConfig.sync_transactions == True,  # noqa: E712
        ).all()
    }

    added = 0
    updated = 0
    transactions = all_transactions

    for txn in transactions:
        txn_account = txn.get("account") or {}
        txn_account_id = str(txn_account.get("id", ""))

        cfg = configs.get(txn_account_id)
        if not cfg:
            continue

        # Ensure local account exists
        if not cfg.local_account_id:
            local_id = f"monarch-{txn_account_id}"
            acct_name = txn_account.get("displayName") or "Unknown"
            raw_type = cfg.account_type or ""
            acct_type, display_group = _classify_account_type(raw_type)

            local_acct = db.query(Account).filter(Account.id == local_id).first()
            if not local_acct:
                local_acct = Account(
                    id=local_id,
                    name=acct_name,
                    institution=cfg.institution or "",
                    account_type=acct_type,
                    display_group=display_group,
                    include_in_nw=True,
                )
                db.add(local_acct)
                db.flush()
            cfg.local_account_id = local_id

        monarch_txn_id = str(txn.get("id", ""))
        local_txn_id = f"monarch-{monarch_txn_id}"

        txn_date_str = txn.get("date", "")
        try:
            txn_date = datetime.strptime(txn_date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        amount = txn.get("amount")
        if amount is None:
            continue

        merchant = txn.get("merchant") or {}
        merchant_name = merchant.get("name", "") if isinstance(merchant, dict) else str(merchant)
        if not merchant_name:
            merchant_name = txn.get("name", txn.get("originalName", ""))

        category, category_group = _extract_category(txn)
        is_recurring = bool(txn.get("isRecurring", False))

        existing = db.query(Transaction).filter(Transaction.id == local_txn_id).first()
        if existing:
            existing.amount = Decimal(str(amount))
            existing.merchant = merchant_name
            existing.category = category
            existing.category_group = category_group
            updated += 1
        else:
            db.add(Transaction(
                id=local_txn_id,
                account_id=cfg.local_account_id,
                date=txn_date,
                amount=Decimal(str(amount)),
                merchant=merchant_name,
                category=category,
                category_group=category_group,
                is_recurring=is_recurring,
                source="monarch",
            ))
            added += 1

    link.last_synced_at = datetime.utcnow()
    db.commit()

    return {"added": added, "updated": updated}


@router.delete("/disconnect")
def disconnect_monarch(
    db: Session = Depends(get_tenant_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Remove Monarch connection and all account configs."""
    link = db.query(MonarchLink).first()
    if not link:
        raise HTTPException(status_code=404, detail="No Monarch connection found")

    db.delete(link)
    db.commit()
    return {"disconnected": True}
