"""
Background scheduler for automatic provider syncs (Monarch, SimpleFIN).

Runs as an asyncio task started during app lifespan. Syncs balances and
transactions for all tenants that have a connection configured for each
provider. Job lifecycle is tracked in sync_jobs (per tenant schema) with
provider-aware uniqueness.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.monarch_link import MonarchAccountConfig, MonarchLink
from app.models.simplefin_link import SimpleFinAccountConfig, SimpleFinLink
from app.models.sync_job import SyncJob
from app.models.transaction import Transaction
from app.parsers.monarch import ACCOUNT_TYPE_MAP, DISPLAY_GROUP_MAP

logger = logging.getLogger("tallied.sync")

# Provider identifiers — keep in sync with the SyncJob.provider column.
PROVIDER_MONARCH = "monarch"
PROVIDER_SIMPLEFIN = "simplefin"
# Monarch is hidden from the UI and excluded from the 12h scheduler loop —
# its API integration has been unreliable. Direct route access
# (/api/v1/monarch/sync) and the dispatch table still work, so re-enabling
# is a one-line change here when Monarch ships a real API.
ALL_PROVIDERS = (PROVIDER_SIMPLEFIN,)

# Sync interval: 12 hours (twice per day)
SYNC_INTERVAL_SECONDS = 12 * 60 * 60

# Watchdog: jobs stuck in 'running' longer than this are marked failed at boot.
WATCHDOG_STUCK_MINUTES = 15

# Postgres advisory lock key for the scheduler. Hashed to a stable bigint so
# only one process across the cluster runs the scheduler loop. Released
# automatically when the holding connection closes (process exit).
SCHEDULER_LOCK_KEY = 0x6D6F6E6172636873  # "monarchs" as ASCII bytes, fits in bigint

# LISTEN/NOTIFY channel. Payload is "{schema}|{provider}" so the listener
# knows which provider's sync to run. Decouples the long-running sync from
# gunicorn's request lifecycle.
NOTIFY_CHANNEL = "tallied_sync"


def _classify_account_type(monarch_type: str) -> tuple[str, str]:
    key = monarch_type.lower().replace(" ", "_")
    acct_type = ACCOUNT_TYPE_MAP.get(key, "cash")
    display_group = DISPLAY_GROUP_MAP.get(acct_type, "Cash")
    return acct_type, display_group


def _extract_category(txn: dict) -> tuple[str, str]:
    cat = txn.get("category") or {}
    category = cat.get("name", "") if isinstance(cat, dict) else str(cat)
    group = ""
    if isinstance(cat, dict):
        grp = cat.get("group") or {}
        group = grp.get("name", "") if isinstance(grp, dict) else str(grp)
    return category, group


def _get_tenant_schemas() -> list[str]:
    """Return all tenant schema names."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'")
        ).fetchall()
    return [r[0] for r in rows]


def _get_tenant_session(schema: str):
    """Create a DB session scoped to a specific tenant schema."""
    db = SessionLocal()
    db.execute(text(f'SET search_path TO "{schema}"'))
    return db


def _get_monarch_client():
    from monarchmoney import MonarchMoney, MonarchMoneyEndpoints
    MonarchMoneyEndpoints.getGraphQL = staticmethod(lambda: "https://api.monarch.com/graphql")
    MonarchMoneyEndpoints.getLoginEndpoint = staticmethod(lambda: "https://api.monarch.com/auth/login/")
    mm = MonarchMoney()
    mm._headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    return mm


async def _sync_tenant_monarch(schema: str) -> dict:
    """Run a full Monarch sync for a single tenant."""
    db = _get_tenant_session(schema)
    try:
        link = db.query(MonarchLink).first()
        if not link:
            return {"schema": schema, "skipped": True}

        mm = _get_monarch_client()
        mm.set_token(link.token)
        mm._headers["Authorization"] = f"Token {link.token}"

        configs = {
            c.monarch_account_id: c
            for c in db.query(MonarchAccountConfig).filter(
                MonarchAccountConfig.monarch_link_id == link.id
            ).all()
        }

        # ── Sync balances + history ───────────────────────────────────────
        balance_configs = {k: v for k, v in configs.items() if v.sync_balances}
        balances_synced = 0

        try:
            accounts_data = await mm.get_accounts()
        except Exception as e:
            logger.error("Failed to fetch Monarch accounts for %s: %s", schema, e)
            return {"schema": schema, "error": str(e)}

        today = date.today()
        history_cutoff = None  # Import all available history

        for acct in accounts_data.get("accounts", []):
            acct_id = str(acct.get("id", ""))
            cfg = balance_configs.get(acct_id)
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

            local_id = cfg.local_account_id or f"monarch-{acct_id}"
            local_acct = db.query(Account).filter(Account.id == local_id).first()
            if not local_acct:
                local_acct = Account(
                    id=local_id, name=acct_name, institution=institution,
                    account_type=acct_type, display_group=display_group, include_in_nw=True,
                )
                db.add(local_acct)
                db.flush()

            if not cfg.local_account_id:
                cfg.local_account_id = local_id

            # Current balance
            existing = db.query(BalanceSnapshot).filter(
                BalanceSnapshot.account_id == local_id,
                BalanceSnapshot.snapshot_date == today,
                BalanceSnapshot.source == "monarch",
            ).first()
            if existing:
                existing.balance = Decimal(str(balance))
            else:
                db.add(BalanceSnapshot(
                    account_id=local_id, snapshot_date=today,
                    balance=Decimal(str(balance)), source="monarch",
                ))
            balances_synced += 1

            # History backfill
            try:
                history = await mm.get_account_history(acct_id)
            except Exception:
                history = []

            # Bulk-load existing snapshot dates for this account so the
            # per-row uniqueness check is an in-memory set lookup instead
            # of N separate SELECTs (the same N+1 anti-pattern the txn
            # loop had).
            existing_snap_dates = {
                r[0] for r in db.execute(
                    text("SELECT snapshot_date FROM balance_snapshots "
                         "WHERE account_id = :aid AND source = 'monarch'"),
                    {"aid": local_id},
                ).fetchall()
            }

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
                if snap_date in existing_snap_dates:
                    continue
                db.add(BalanceSnapshot(
                    account_id=local_id, snapshot_date=snap_date,
                    balance=Decimal(str(snap_balance)), source="monarch",
                ))
                existing_snap_dates.add(snap_date)

        # ── Sync transactions ─────────────────────────────────────────────
        txn_configs = {k: v for k, v in configs.items() if v.sync_transactions}
        txn_added = 0
        txn_updated = 0

        if txn_configs:
            start_date = date(2000, 1, 1)  # Fetch all available history
            all_transactions: list[dict] = []
            offset = 0
            page_size = 100

            try:
                while True:
                    txn_data = await mm.get_transactions(
                        limit=page_size, offset=offset,
                        start_date=start_date.isoformat(),
                        end_date=today.isoformat(),
                    )
                    results = txn_data.get("allTransactions", {}).get("results", [])
                    all_transactions.extend(results)
                    total = txn_data.get("allTransactions", {}).get("totalCount", 0)
                    offset += page_size
                    if offset >= total or len(results) == 0:
                        break
            except Exception as e:
                logger.error("Failed to fetch Monarch transactions for %s: %s", schema, e)

            # Dedupe — Monarch pagination can return the same txn twice when
            # rows shift mid-iteration; collapse to one entry per id (last
            # write wins) to avoid PK violations on commit.
            deduped: dict[str, dict] = {}
            for txn in all_transactions:
                deduped[str(txn.get("id", ""))] = txn
            all_transactions = list(deduped.values())

            # Bulk existence check — for a tenant with thousands of
            # transactions, the per-row db.query().first() pattern below
            # used to fire N synchronous queries (the dominant cost in the
            # sync loop and the reason gunicorn workers timed out). One
            # SELECT IN replaces them all and the subsequent loop is a
            # pure in-memory dict lookup.
            candidate_ids = [
                f"monarch-{str(t.get('id', ''))}" for t in all_transactions
            ]
            existing_txns: dict[str, Transaction] = {}
            if candidate_ids:
                for t in (
                    db.query(Transaction)
                    .filter(Transaction.id.in_(candidate_ids))
                    .all()
                ):
                    existing_txns[t.id] = t

            for txn in all_transactions:
                txn_account = txn.get("account") or {}
                txn_account_id = str(txn_account.get("id", ""))
                cfg = txn_configs.get(txn_account_id)
                if not cfg:
                    continue

                if not cfg.local_account_id:
                    local_id = f"monarch-{txn_account_id}"
                    # Ensure the Account row exists — txn-only syncs (where
                    # sync_balances=False) never went through the balance
                    # branch above that creates Accounts.
                    local_acct = db.query(Account).filter(Account.id == local_id).first()
                    if not local_acct:
                        acct_name = (txn_account.get("displayName")
                                     or cfg.account_name or "Unknown")
                        raw_type = cfg.account_type or ""
                        acct_type, display_group = _classify_account_type(raw_type)
                        local_acct = Account(
                            id=local_id, name=acct_name,
                            institution=cfg.institution or "",
                            account_type=acct_type, display_group=display_group,
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

                existing_txn = existing_txns.get(local_txn_id)
                if existing_txn:
                    existing_txn.amount = Decimal(str(amount))
                    existing_txn.merchant = merchant_name
                    existing_txn.category = category
                    existing_txn.category_group = category_group
                    txn_updated += 1
                else:
                    db.add(Transaction(
                        id=local_txn_id, account_id=cfg.local_account_id,
                        date=txn_date, amount=Decimal(str(amount)),
                        merchant=merchant_name, category=category,
                        category_group=category_group, is_recurring=is_recurring,
                        source="monarch",
                    ))
                    txn_added += 1

        link.last_synced_at = datetime.utcnow()
        db.commit()

        return {
            "schema": schema,
            "balances_synced": balances_synced,
            "txn_added": txn_added,
            "txn_updated": txn_updated,
        }
    except Exception as e:
        db.rollback()
        logger.error("Monarch sync failed for %s: %s", schema, e)
        return {"schema": schema, "error": str(e)}
    finally:
        db.close()


# ── SimpleFIN sync ────────────────────────────────────────────────────────────
# SimpleFIN exposes one endpoint: GET {access_url}/accounts. The response
# contains balances + recent transactions for every account in one shot.
# Default time range cap from the spec is 45 days; we request that.

SIMPLEFIN_HISTORY_DAYS = 45


def _classify_simplefin_account(name: str, has_holdings: bool) -> tuple[str, str]:
    """Infer (account_type, display_group) from a SimpleFIN account name.

    SimpleFIN doesn't carry a structured type field — only display name +
    institution. Map common keywords to our internal types.
    """
    if has_holdings:
        return "investment", "Investment"
    n = name.lower()
    if "mortgage" in n or "loan" in n:
        return "loan", "Liability"
    if "credit" in n or "visa" in n or "mastercard" in n or "amex" in n or "card" in n:
        return "cash", "Cash"
    if "savings" in n:
        return "cash", "Cash"
    return "cash", "Cash"


async def _simplefin_get_accounts(access_url: str) -> dict:
    """Fetch /accounts using the basic-auth credentials embedded in the URL."""
    import aiohttp
    from urllib.parse import urlparse

    p = urlparse(access_url)
    if not p.username or not p.password:
        raise RuntimeError("SimpleFIN access URL missing basic-auth credentials")

    end = int(datetime.utcnow().timestamp())
    start = end - SIMPLEFIN_HISTORY_DAYS * 24 * 3600
    clean = f"{p.scheme}://{p.hostname}{p.path}/accounts?start-date={start}&end-date={end}&pending=1"

    auth = aiohttp.BasicAuth(p.username, p.password)
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(clean, auth=auth, headers={"User-Agent": "Tallied/1.0"}) as resp:
            if resp.status == 401 or resp.status == 403:
                raise RuntimeError(
                    f"SimpleFIN access URL rejected ({resp.status}). "
                    "Re-claim a fresh setup token in Settings → SimpleFIN."
                )
            resp.raise_for_status()
            return await resp.json()


async def _sync_tenant_simplefin(schema: str) -> dict:
    """Run a full SimpleFIN sync for a single tenant.

    Single API call returns balances + ~45 days of transactions for every
    account. We respect per-account sync_balances / sync_transactions toggles
    and reuse the same Account / BalanceSnapshot / Transaction models as
    Monarch, with source='simplefin'.
    """
    db = _get_tenant_session(schema)
    try:
        link = db.query(SimpleFinLink).first()
        if not link:
            return {"schema": schema, "skipped": True}

        try:
            data = await _simplefin_get_accounts(link.access_url)
        except Exception as e:
            logger.error("Failed to fetch SimpleFIN accounts for %s: %s", schema, e)
            return {"schema": schema, "error": str(e)}

        for err in data.get("errors", []) or []:
            logger.warning("SimpleFIN warning for %s: %s", schema, err)

        configs = {
            c.simplefin_account_id: c
            for c in db.query(SimpleFinAccountConfig).filter(
                SimpleFinAccountConfig.simplefin_link_id == link.id
            ).all()
        }

        today = date.today()
        balances_synced = 0
        txn_added = 0
        txn_updated = 0

        for acct in data.get("accounts", []):
            sf_acct_id = str(acct.get("id", ""))
            cfg = configs.get(sf_acct_id)
            if not cfg:
                # Account exists upstream but not configured — skip silently;
                # /connect (and refresh) is what creates configs.
                continue

            local_id = cfg.local_account_id or f"simplefin-{sf_acct_id}"
            acct_name = acct.get("name", "Unknown")
            org = acct.get("org") or {}
            institution = org.get("name", "") if isinstance(org, dict) else ""
            has_holdings = bool(acct.get("holdings"))
            acct_type, display_group = _classify_simplefin_account(acct_name, has_holdings)

            local_acct = db.query(Account).filter(Account.id == local_id).first()
            if not local_acct:
                local_acct = Account(
                    id=local_id, name=acct_name, institution=institution,
                    account_type=acct_type, display_group=display_group, include_in_nw=True,
                )
                db.add(local_acct)
                db.flush()
            if not cfg.local_account_id:
                cfg.local_account_id = local_id

            # ── Balance ────────────────────────────────────────────────────
            if cfg.sync_balances:
                balance_str = acct.get("balance")
                if balance_str is not None:
                    try:
                        balance_val = Decimal(str(balance_str))
                    except Exception:
                        balance_val = None
                    if balance_val is not None:
                        existing_snap = db.query(BalanceSnapshot).filter(
                            BalanceSnapshot.account_id == local_id,
                            BalanceSnapshot.snapshot_date == today,
                            BalanceSnapshot.source == "simplefin",
                        ).first()
                        if existing_snap:
                            existing_snap.balance = balance_val
                        else:
                            db.add(BalanceSnapshot(
                                account_id=local_id, snapshot_date=today,
                                balance=balance_val, source="simplefin",
                            ))
                        balances_synced += 1

            # ── Transactions ───────────────────────────────────────────────
            if cfg.sync_transactions:
                raw_txns = acct.get("transactions", []) or []

                # Dedupe by id (defensive — SimpleFIN doesn't paginate but
                # multiple accounts could theoretically expose the same id).
                deduped: dict[str, dict] = {}
                for t in raw_txns:
                    deduped[str(t.get("id", ""))] = t
                raw_txns = list(deduped.values())

                # Bulk existence check — single SELECT IN, then in-memory.
                candidate_ids = [f"simplefin-{str(t.get('id', ''))}" for t in raw_txns]
                existing_txns: dict[str, Transaction] = {}
                if candidate_ids:
                    for t in (
                        db.query(Transaction)
                        .filter(Transaction.id.in_(candidate_ids))
                        .all()
                    ):
                        existing_txns[t.id] = t

                for t in raw_txns:
                    sf_txn_id = str(t.get("id", ""))
                    if not sf_txn_id:
                        continue
                    local_txn_id = f"simplefin-{sf_txn_id}"

                    posted = t.get("posted") or t.get("transacted_at")
                    if not posted:
                        continue
                    try:
                        txn_date = datetime.utcfromtimestamp(int(posted)).date()
                    except (ValueError, TypeError):
                        continue

                    amount_str = t.get("amount")
                    if amount_str is None:
                        continue
                    try:
                        amount = Decimal(str(amount_str))
                    except Exception:
                        continue

                    merchant = t.get("payee") or t.get("description") or ""
                    # SimpleFIN doesn't categorize — leave category empty so
                    # our existing category-rules / manual labelling pipeline
                    # owns it.
                    existing = existing_txns.get(local_txn_id)
                    if existing:
                        existing.amount = amount
                        existing.merchant = merchant
                        txn_updated += 1
                    else:
                        db.add(Transaction(
                            id=local_txn_id, account_id=cfg.local_account_id,
                            date=txn_date, amount=amount,
                            merchant=merchant, category="", category_group="",
                            is_recurring=False,
                            source="simplefin",
                        ))
                        txn_added += 1

        link.last_synced_at = datetime.utcnow()
        db.commit()

        return {
            "schema": schema,
            "balances_synced": balances_synced,
            "txn_added": txn_added,
            "txn_updated": txn_updated,
        }
    except Exception as e:
        db.rollback()
        logger.error("SimpleFIN sync failed for %s: %s", schema, e)
        return {"schema": schema, "error": str(e)}
    finally:
        db.close()


# Provider → sync function dispatch table.
_PROVIDER_SYNC_FN: dict[str, "callable"] = {}


def _register_provider(name: str, fn) -> None:
    _PROVIDER_SYNC_FN[name] = fn


_register_provider(PROVIDER_MONARCH, _sync_tenant_monarch)
_register_provider(PROVIDER_SIMPLEFIN, _sync_tenant_simplefin)


async def run_sync_with_job(schema: str, job_id: int, provider: str) -> None:
    """Execute a provider sync against `schema` and update the job row.

    Used by the route handlers (insert job row → return 202 → enqueue) and
    by the scheduler (one row per cycle). Always lands the row in a
    terminal state — never leaves a row in 'running'.
    """
    sync_fn = _PROVIDER_SYNC_FN.get(provider)
    if sync_fn is None:
        logger.error("Unknown provider %r for job %d", provider, job_id)
        _finalize_job(schema, job_id, {"error": f"unknown provider: {provider}"})
        return
    try:
        result = await sync_fn(schema)
        _finalize_job(schema, job_id, result)
    except Exception as e:
        logger.exception("%s sync crashed for %s job=%d", provider, schema, job_id)
        _finalize_job(schema, job_id, {"error": str(e)})


def _finalize_job(schema: str, job_id: int, result: dict) -> None:
    db = _get_tenant_session(schema)
    try:
        job = db.query(SyncJob).filter(SyncJob.id == job_id).first()
        if not job:
            logger.warning("Job %d not found in %s when finalizing", job_id, schema)
            return
        job.finished_at = datetime.utcnow()
        if "error" in result:
            job.status = "failed"
            job.error = (result.get("error") or "")[:4000]
        elif result.get("skipped"):
            job.status = "succeeded"
        else:
            job.status = "succeeded"
            job.balances_synced = int(result.get("balances_synced", 0))
            job.txn_added = int(result.get("txn_added", 0))
            job.txn_updated = int(result.get("txn_updated", 0))
        db.commit()
    finally:
        db.close()


def create_job_row(schema: str, provider: str, trigger: str) -> tuple[int, bool]:
    """Insert a new sync_jobs row with status='running' for `provider`.

    Returns (job_id, created): created=True if we inserted a new row,
    False if a 'running' row for the same provider already existed and
    we returned its id instead. The unique partial index
    uq_sync_jobs_one_running_per_provider enforces at most one running
    row per (schema, provider), so a TOCTOU race between a
    find_running_job check and the insert lands here as an IntegrityError
    that we catch and recover from.

    Captures the autoincrement id via flush() before commit — the engine's
    pool-checkout handler resets search_path to public on the next checkout,
    so a post-commit refresh would query the wrong schema.
    """
    from sqlalchemy.exc import IntegrityError

    db = _get_tenant_session(schema)
    try:
        job = SyncJob(provider=provider, status="running", trigger=trigger)
        db.add(job)
        try:
            db.flush()
            job_id = job.id
            db.commit()
            return job_id, True
        except IntegrityError:
            db.rollback()
            # Rollback returns the connection to the pool, which fires the
            # checkout handler and resets search_path to public. Re-set it
            # before the recovery query.
            db.execute(text(f'SET search_path TO "{schema}"'))
            existing = (
                db.query(SyncJob)
                .filter(SyncJob.status == "running", SyncJob.provider == provider)
                .order_by(SyncJob.started_at.desc())
                .first()
            )
            if existing:
                return existing.id, False
            raise
    finally:
        db.close()


def find_running_job(schema: str, provider: str) -> int | None:
    """Return the id of the in-flight job for this (tenant, provider), if any."""
    db = _get_tenant_session(schema)
    try:
        job = (
            db.query(SyncJob)
            .filter(SyncJob.status == "running", SyncJob.provider == provider)
            .order_by(SyncJob.started_at.desc())
            .first()
        )
        return job.id if job else None
    finally:
        db.close()


def reap_stuck_jobs() -> None:
    """Mark any 'running' job older than WATCHDOG_STUCK_MINUTES as failed.

    Runs once at boot before the scheduler starts. A worker SIGTERM mid-sync
    leaves the job row stuck in 'running' forever; this is the safety net.
    """
    from sqlalchemy.exc import ProgrammingError

    cutoff = datetime.utcnow() - timedelta(minutes=WATCHDOG_STUCK_MINUTES)
    schemas = _get_tenant_schemas()
    total = 0
    for schema in schemas:
        db = _get_tenant_session(schema)
        try:
            stuck = (
                db.query(SyncJob)
                .filter(
                    SyncJob.status == "running",
                    SyncJob.started_at < cutoff,
                )
                .all()
            )
            for j in stuck:
                j.status = "failed"
                j.error = "worker died (watchdog reaped at startup)"
                j.finished_at = datetime.utcnow()
                total += 1
            if stuck:
                db.commit()
        except ProgrammingError:
            # Table doesn't exist in this schema yet (migration not applied).
            # Skip silently — the migration will add it on the next deploy.
            db.rollback()
        except Exception:
            logger.exception("Watchdog reap failed for %s", schema)
            db.rollback()
        finally:
            db.close()
    if total:
        logger.warning("Watchdog reaped %d stuck sync job(s)", total)


def _tenant_has_provider_connection(schema: str, provider: str) -> bool:
    """Check whether a tenant has a configured connection for `provider`.

    Tolerates schemas where the provider's link table doesn't exist yet
    (tenant created before the migration ran) by treating it as "no
    connection" — the next migration will add the table.
    """
    from sqlalchemy.exc import ProgrammingError

    db = _get_tenant_session(schema)
    try:
        if provider == PROVIDER_MONARCH:
            return db.query(MonarchLink).first() is not None
        if provider == PROVIDER_SIMPLEFIN:
            return db.query(SimpleFinLink).first() is not None
        return False
    except ProgrammingError:
        db.rollback()
        return False
    finally:
        db.close()


async def sync_all_tenants():
    """Run all configured provider syncs across every tenant schema.

    For each tenant, iterates each provider; only creates a job row when the
    tenant actually has a connection for that provider so we don't pollute
    the job table. Tolerates schemas where sync_jobs hasn't been created yet.
    """
    from sqlalchemy.exc import ProgrammingError

    schemas = _get_tenant_schemas()
    results = []
    for schema in schemas:
        for provider in ALL_PROVIDERS:
            if not _tenant_has_provider_connection(schema, provider):
                continue
            try:
                job_id, _created = create_job_row(
                    schema, provider=provider, trigger="scheduled"
                )
            except ProgrammingError:
                logger.warning(
                    "Skipping %s/%s: sync_jobs missing (migration pending?)",
                    schema, provider,
                )
                continue
            await run_sync_with_job(schema, job_id, provider)
            results.append({"schema": schema, "provider": provider, "job_id": job_id})
    return results


def mark_running_jobs_failed(reason: str) -> int:
    """Flip every 'running' job in every tenant schema to 'failed'.

    Called from the lifespan shutdown path so a graceful stop (deploy,
    docker compose down) marks in-flight jobs failed immediately, instead
    of waiting up to 15 minutes for the next-boot watchdog to catch them.
    SIGKILL still skips this — the watchdog is the backstop for that case.
    """
    from sqlalchemy.exc import ProgrammingError

    schemas = _get_tenant_schemas()
    total = 0
    for schema in schemas:
        db = _get_tenant_session(schema)
        try:
            running = (
                db.query(SyncJob)
                .filter(SyncJob.status == "running")
                .all()
            )
            for j in running:
                j.status = "failed"
                j.error = reason
                j.finished_at = datetime.utcnow()
                total += 1
            if running:
                db.commit()
        except ProgrammingError:
            db.rollback()
        except Exception:
            logger.exception("Shutdown mark-failed query failed for %s", schema)
            db.rollback()
        finally:
            db.close()
    return total


async def _scheduler_loop():
    """Background loop that runs Monarch sync on a fixed interval.

    Guards against multi-worker duplication via a Postgres advisory lock —
    gunicorn -w N spawns N processes that each run lifespan(), so without the
    lock every tenant gets N concurrent syncs. The lock-loser exits cleanly
    and the route handler / watchdog still work in that worker.

    Runs an immediate sync on startup, then sleeps the full interval between
    runs. Without the immediate sync, every container restart would defer
    the next sync by 12 hours.
    """
    # Hold a dedicated connection open for the lifetime of the loop — the
    # advisory lock is released when this connection closes (i.e. process
    # exit), so we can't release it back to the pool.
    conn = engine.connect()
    try:
        got_lock = conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY}
        ).scalar()
        if not got_lock:
            logger.info(
                "Monarch sync scheduler: another worker holds the lock; this worker is idle"
            )
            return

        logger.info("Monarch sync scheduler started (interval: %ds)", SYNC_INTERVAL_SECONDS)
        while True:
            try:
                logger.info("Starting scheduled Monarch sync...")
                await sync_all_tenants()
            except Exception as e:
                logger.error("Scheduled Monarch sync error: %s", e)
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)
    finally:
        conn.close()


async def claim_orphan_jobs() -> int:
    """Resume any 'running' jobs that exist at scheduler startup.

    These come from two sources:
    - The web tier inserted a row + NOTIFY'd while the scheduler was down.
    - A previous scheduler process died mid-sync (graceful shutdown should
      have failed them; this catches SIGKILL gaps before the watchdog).

    Only claim jobs younger than the watchdog cutoff — older ones get
    reaped to 'failed' by reap_stuck_jobs before we get here. Iterates all
    providers since multiple may have a running row per tenant.
    """
    from sqlalchemy.exc import ProgrammingError

    cutoff = datetime.utcnow() - timedelta(minutes=WATCHDOG_STUCK_MINUTES)
    schemas = _get_tenant_schemas()
    claimed = 0
    for schema in schemas:
        db = _get_tenant_session(schema)
        try:
            jobs = (
                db.query(SyncJob)
                .filter(
                    SyncJob.status == "running",
                    SyncJob.started_at >= cutoff,
                )
                .order_by(SyncJob.started_at.desc())
                .all()
            )
            pairs = [(j.id, j.provider) for j in jobs]
        except ProgrammingError:
            db.rollback()
            pairs = []
        finally:
            db.close()
        for job_id, provider in pairs:
            logger.info("Claiming orphan running job %d (%s) in %s", job_id, provider, schema)
            await run_sync_with_job(schema, job_id, provider)
            claimed += 1
    return claimed


def notify_sync_request(schema: str, provider: str) -> None:
    """Wake the scheduler container's notify_listener_loop for (schema, provider).

    Called by the web tier's POST /sync routes after creating a 'running' job
    row. Fire-and-forget: if no listener is connected (scheduler down,
    mid-deploy) the NOTIFY is harmless — claim_orphan_jobs picks the row up
    at the next scheduler boot.
    """
    with engine.connect() as conn:
        # NOTIFY's payload can't be a bind parameter — it's a string literal
        # in the SQL. Schema names come from server-controlled tenant rows
        # (alphanumeric + underscore) and provider is one of ALL_PROVIDERS,
        # but quote anyway as a defense.
        safe_schema = schema.replace("'", "''")
        safe_provider = provider.replace("'", "''")
        payload = f"{safe_schema}|{safe_provider}"
        conn.execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{payload}'"))
        conn.commit()


async def notify_listener_loop():
    """Wake on Postgres NOTIFY monarch_sync, run pending manual jobs.

    Holds a long-lived psycopg2 connection in autocommit mode (so NOTIFY
    payloads arrive immediately rather than being held until the next
    transaction boundary). Uses asyncio's add_reader to avoid blocking the
    event loop on select().
    """
    import select
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    raw = engine.raw_connection()
    try:
        # Capture the underlying psycopg2 connection BEFORE detach — after
        # detach the proxy stops exposing driver_connection. Detach removes
        # it from the pool so SQLAlchemy can't recycle it underneath us.
        pg_conn = raw.driver_connection
        raw.detach()
        pg_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = pg_conn.cursor()
        cur.execute(f"LISTEN {NOTIFY_CHANNEL}")
        cur.close()
        logger.info("Monarch sync NOTIFY listener attached on channel '%s'", NOTIFY_CHANNEL)

        loop = asyncio.get_running_loop()
        wakeup = asyncio.Event()

        def _on_socket_readable():
            wakeup.set()

        loop.add_reader(pg_conn.fileno(), _on_socket_readable)
        try:
            while True:
                await wakeup.wait()
                wakeup.clear()
                pg_conn.poll()
                # Drain all pending notifies — collapse duplicates per
                # schema (the loop processes manual jobs idempotently).
                pending: set[tuple[str, str]] = set()
                while pg_conn.notifies:
                    n = pg_conn.notifies.pop(0)
                    if not n.payload:
                        continue
                    if "|" in n.payload:
                        schema, provider = n.payload.split("|", 1)
                    else:
                        # Back-compat for the old single-channel payload.
                        schema, provider = n.payload, PROVIDER_MONARCH
                    pending.add((schema, provider))
                for schema, provider in pending:
                    await _process_notify(schema, provider)
        finally:
            loop.remove_reader(pg_conn.fileno())
    finally:
        try:
            raw.close()
        except Exception:
            pass


async def _process_notify(schema: str, provider: str) -> None:
    """Look up the in-flight 'running' job for (schema, provider) and run it."""
    from sqlalchemy.exc import ProgrammingError

    db = _get_tenant_session(schema)
    try:
        job = (
            db.query(SyncJob)
            .filter(SyncJob.status == "running", SyncJob.provider == provider)
            .order_by(SyncJob.started_at.desc())
            .first()
        )
        job_id = job.id if job else None
    except ProgrammingError:
        db.rollback()
        job_id = None
    finally:
        db.close()
    if job_id is None:
        logger.info("NOTIFY for %s/%s but no running job (already processed?)",
                    schema, provider)
        return
    logger.info("NOTIFY: running %s sync for %s (job %d)", provider, schema, job_id)
    await run_sync_with_job(schema, job_id, provider)


_scheduler_task: asyncio.Task | None = None
_listener_task: asyncio.Task | None = None


def start_scheduler():
    """Start the background sync scheduler and NOTIFY listener.

    Call from the dedicated scheduler container's entrypoint. The web tier
    no longer runs these — its event loop must stay free for HTTP traffic.
    """
    global _scheduler_task, _listener_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    _listener_task = asyncio.create_task(notify_listener_loop())
    logger.info("Monarch sync scheduler + NOTIFY listener tasks created")


def stop_scheduler():
    """Stop background tasks. Call from shutdown."""
    global _scheduler_task, _listener_task
    for t in (_scheduler_task, _listener_task):
        if t and not t.done():
            t.cancel()
    _scheduler_task = None
    _listener_task = None
    logger.info("Monarch sync scheduler stopped")
