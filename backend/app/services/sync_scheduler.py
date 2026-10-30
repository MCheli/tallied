"""
Background scheduler for provider syncs.

One generic loop for every provider in `app.services.providers`:
fetch → normalize (the provider's job) → upsert accounts, balance snapshots
and transactions → finalize the job row (this module's job). Job lifecycle is
tracked in sync_jobs (per tenant schema) with provider-aware uniqueness.

Runs as asyncio tasks started during the app lifespan (or in the dedicated
scheduler process, see app/scheduler/__main__.py): a 12-hour loop guarded by a
Postgres advisory lock, plus a LISTEN loop that wakes on NOTIFY for manual
syncs enqueued by the web tier.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from app.database import engine
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.sync_job import SyncJob
from app.models.transaction import Transaction
from app.services.categorize import apply_rules
from app.services.providers import ALL_PROVIDERS, get_provider
from app.services.providers.base import ProviderError, type_and_group_for
from app.services.tenant_service import tenant_session

logger = logging.getLogger("tallied.sync")

PROVIDER_SIMPLEFIN = "simplefin"

# Sync interval: 12 hours (twice per day)
SYNC_INTERVAL_SECONDS = 12 * 60 * 60

# Watchdog: jobs stuck in 'running' longer than this are marked failed at boot.
WATCHDOG_STUCK_MINUTES = 15

# Postgres advisory lock key for the scheduler. Only one process across the
# cluster runs the scheduler loop; released when the holding connection closes.
SCHEDULER_LOCK_KEY = 0x6D6F6E6172636873

# LISTEN/NOTIFY channel. Payload is "{schema}|{provider}".
NOTIFY_CHANNEL = "tallied_sync"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_tenant_schemas() -> list[str]:
    """Return all tenant schema names."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'")
        ).fetchall()
    return [r[0] for r in rows]


# ── The generic sync ──────────────────────────────────────────────────────────

async def sync_tenant(schema: str, provider_name: str) -> dict:
    """Run one provider's sync for one tenant. Returns a result dict for _finalize_job."""
    provider = get_provider(provider_name)
    with tenant_session(schema) as db:
        connection = provider.get_connection(db)
        if connection is None:
            return {"schema": schema, "skipped": True}

        try:
            snapshot = await provider.fetch(connection.credential)
        except ProviderError as e:
            logger.error("%s fetch failed for %s: %s", provider.display_name, schema, e)
            return {"schema": schema, "error": str(e)}
        except Exception as e:
            logger.exception("%s fetch crashed for %s", provider.display_name, schema)
            return {"schema": schema, "error": f"{type(e).__name__}: {e}"}

        warnings = list(snapshot.warnings)
        for warning in warnings:
            logger.warning("%s warning for %s: %s", provider.display_name, schema, warning)

        today = date.today()
        balances_synced = txn_added = txn_updated = 0
        new_txn_ids: list[str] = []
        try:
            for name in adopt_reconnected_accounts(provider, connection, snapshot.accounts):
                logger.warning("%s: %s came back under a new id after a reconnect; kept its history", provider.display_name, name)
                warnings.append(f"{name} was reconnected; its history was kept.")
            for acct in snapshot.accounts:
                cfg = connection.configs.get(acct.id)
                if cfg is None:
                    # Upstream account the user has not configured; /connect creates configs.
                    continue

                local_id = cfg.local_account_id or f"{provider.name}-{acct.id}"
                local_acct = db.get(Account, local_id)
                if local_acct is None:
                    acct_type, display_group = type_and_group_for(acct.kind, cfg.account_type)
                    local_acct = Account(
                        id=local_id, name=acct.name, institution=acct.institution,
                        account_type=acct_type, display_group=display_group, include_in_nw=True,
                    )
                    db.add(local_acct)
                    db.flush()
                if not cfg.local_account_id:
                    cfg.row.local_account_id = local_id

                if cfg.sync_balances and acct.balance is not None:
                    snap_date = acct.balance_date or today
                    existing = db.query(BalanceSnapshot).filter(
                        BalanceSnapshot.account_id == local_id,
                        BalanceSnapshot.snapshot_date == snap_date,
                        BalanceSnapshot.source == provider.name,
                    ).first()
                    if existing:
                        existing.balance = acct.balance
                    else:
                        db.add(BalanceSnapshot(
                            account_id=local_id, snapshot_date=snap_date,
                            balance=acct.balance, source=provider.name,
                        ))
                    balances_synced += 1

                if cfg.sync_transactions and acct.transactions:
                    ids = [f"{provider.name}-{t.id}" for t in acct.transactions]
                    existing_txns = {
                        t.id: t for t in db.query(Transaction).filter(Transaction.id.in_(ids)).all()
                    }
                    for t in acct.transactions:
                        local_txn_id = f"{provider.name}-{t.id}"
                        existing_txn = existing_txns.get(local_txn_id)
                        if existing_txn:
                            existing_txn.amount = t.amount
                            existing_txn.merchant = t.merchant
                            existing_txn.date = t.date
                            txn_updated += 1
                        elif rekeyed := _rekey_reconnected_duplicate(db, local_id, t, local_txn_id, ids):
                            rekeyed.amount = t.amount
                            txn_updated += 1
                        else:
                            db.add(Transaction(
                                id=local_txn_id, account_id=local_id,
                                date=t.date, amount=t.amount,
                                merchant=t.merchant, category=t.category or None, category_group=t.category_group or None,
                                category_source=provider.name if t.category else None,
                                is_recurring=False, source=provider.name,
                            ))
                            txn_added += 1
                            new_txn_ids.append(local_txn_id)

            db.flush()
            categorized = apply_rules(db, new_txn_ids)
            if categorized:
                logger.info("Categorized %d new transactions by rule for %s", categorized, schema)
            connection.row.last_synced_at = _utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception("%s upsert failed for %s", provider.display_name, schema)
            return {"schema": schema, "error": f"{type(e).__name__}: {e}"}

    return {
        "schema": schema,
        "balances_synced": balances_synced,
        "txn_added": txn_added,
        "txn_updated": txn_updated,
        "warnings": warnings,
    }


def adopt_reconnected_accounts(provider, connection, accounts) -> list[str]:
    """A bank reconnected upstream comes back with new account ids. An unconfigured upstream account takes
    over the config of a configured one with the same name and institution that no longer appears, so its
    history continues instead of the account silently going stale. Returns the adopted names."""
    upstream = {a.id for a in accounts}
    orphans = [c for external_id, c in connection.configs.items() if external_id not in upstream]
    adopted = []
    for a in accounts:
        if a.id in connection.configs:
            continue
        matches = [c for c in orphans if c.account_name == a.name and (c.institution or "") == (a.institution or "")]
        if len(matches) != 1:
            continue
        cfg = matches[0]
        orphans.remove(cfg)
        del connection.configs[cfg.external_id]
        provider.rebind(cfg, a.id)
        connection.configs[a.id] = cfg
        adopted.append(a.name)
    return adopted


def _rekey_reconnected_duplicate(db, account_id: str, t, new_id: str, fetched_ids: list[str]):
    """After a reconnect the provider resends recent transactions under new ids. A stored row on the same
    account with the same date, amount and merchant whose id the provider no longer sends is the same
    transaction: give it the new id (keeping its category) instead of adding a duplicate."""
    prefix = new_id.split("-", 1)[0] + "-"
    old = db.query(Transaction).filter(
        Transaction.account_id == account_id, Transaction.date == t.date, Transaction.amount == t.amount,
        Transaction.merchant == t.merchant, Transaction.id.like(prefix + "%"), Transaction.id.notin_(fetched_ids),
    ).first()
    if old is None:
        return None
    old.id = new_id
    db.flush()
    return old


# ── Job rows ──────────────────────────────────────────────────────────────────

async def run_sync_with_job(schema: str, job_id: int, provider: str) -> None:
    """Execute a provider sync against `schema` and update the job row.

    Always lands the row in a terminal state; never leaves a row in 'running'.
    """
    try:
        get_provider(provider)
    except KeyError:
        logger.error("Unknown provider %r for job %d", provider, job_id)
        _finalize_job(schema, job_id, {"error": f"unknown provider: {provider}"})
        return
    try:
        result = await sync_tenant(schema, provider)
        _finalize_job(schema, job_id, result)
    except Exception as e:
        logger.exception("%s sync crashed for %s job=%d", provider, schema, job_id)
        _finalize_job(schema, job_id, {"error": str(e)})


def _finalize_job(schema: str, job_id: int, result: dict) -> None:
    with tenant_session(schema) as db:
        job = db.get(SyncJob, job_id)
        if not job:
            logger.warning("Job %d not found in %s when finalizing", job_id, schema)
            return
        job.finished_at = _utcnow()
        job.warnings = result.get("warnings") or None
        if "error" in result:
            job.status = "failed"
            job.error = (result.get("error") or "")[:4000]
        else:
            job.status = "succeeded"
            job.balances_synced = int(result.get("balances_synced", 0))
            job.txn_added = int(result.get("txn_added", 0))
            job.txn_updated = int(result.get("txn_updated", 0))
        db.commit()
        _emit_sync_webhook(schema, job)


def _emit_sync_webhook(schema: str, job: SyncJob) -> None:
    """Deliver balance.updated / transaction.created after a successful sync. Never raises."""
    if job.status != "succeeded" or not (job.balances_synced or job.txn_added):
        return
    try:
        from app.database import SessionLocal
        from app.models.tenant import Tenant
        from app.services.webhook_service import deliver_webhook

        with SessionLocal() as public_db:
            tenant = public_db.query(Tenant).filter(Tenant.schema_name == schema).first()
            if not tenant:
                return
            payload = {
                "provider": job.provider,
                "job_id": job.id,
                "balances_synced": job.balances_synced,
                "transactions_added": job.txn_added,
                "transactions_updated": job.txn_updated,
            }
            if job.balances_synced:
                deliver_webhook("balance.updated", tenant.id, payload, public_db)
            if job.txn_added:
                deliver_webhook("transaction.created", tenant.id, payload, public_db)
    except Exception:
        logger.exception("Webhook delivery after sync failed for %s", schema)


def create_job_row(schema: str, provider: str, trigger: str) -> tuple[int, bool]:
    """Insert a sync_jobs row with status='running' for `provider`.

    Returns (job_id, created): created=False when a 'running' row for the same
    provider already existed (the unique partial index turns the race into an
    IntegrityError, which is caught here) and its id is returned instead.
    """
    from sqlalchemy.exc import IntegrityError

    with tenant_session(schema) as db:
        job = SyncJob(provider=provider, status="running", trigger=trigger)
        db.add(job)
        try:
            db.flush()
            job_id = job.id
            db.commit()
            return job_id, True
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(SyncJob)
                .filter(SyncJob.status == "running", SyncJob.provider == provider)
                .order_by(SyncJob.started_at.desc())
                .first()
            )
            if existing:
                return existing.id, False
            raise


def find_running_job(schema: str, provider: str) -> int | None:
    """Return the id of the in-flight job for this (tenant, provider), if any."""
    with tenant_session(schema) as db:
        job = (
            db.query(SyncJob)
            .filter(SyncJob.status == "running", SyncJob.provider == provider)
            .order_by(SyncJob.started_at.desc())
            .first()
        )
        return job.id if job else None


def _for_each_tenant_jobs(fn, *, label: str) -> int:
    """Run fn(db) -> int for every tenant schema, tolerating schemas without sync_jobs."""
    from sqlalchemy.exc import ProgrammingError

    total = 0
    for schema in _get_tenant_schemas():
        try:
            with tenant_session(schema) as db:
                total += fn(db)
        except ProgrammingError:
            # sync_jobs missing in this schema (migration pending); nothing to do.
            pass
        except Exception:
            logger.exception("%s failed for %s", label, schema)
    return total


def reap_stuck_jobs() -> None:
    """Mark any 'running' job older than WATCHDOG_STUCK_MINUTES as failed (runs at boot)."""
    cutoff = _utcnow() - timedelta(minutes=WATCHDOG_STUCK_MINUTES)

    def _reap(db) -> int:
        stuck = db.query(SyncJob).filter(SyncJob.status == "running", SyncJob.started_at < cutoff).all()
        for j in stuck:
            j.status = "failed"
            j.error = "worker died (watchdog reaped at startup)"
            j.finished_at = _utcnow()
        if stuck:
            db.commit()
        return len(stuck)

    total = _for_each_tenant_jobs(_reap, label="Watchdog reap")
    if total:
        logger.warning("Watchdog reaped %d stuck sync job(s)", total)


def mark_running_jobs_failed(reason: str) -> int:
    """Flip every 'running' job in every tenant schema to 'failed' (graceful shutdown)."""

    def _fail(db) -> int:
        running = db.query(SyncJob).filter(SyncJob.status == "running").all()
        for j in running:
            j.status = "failed"
            j.error = reason
            j.finished_at = _utcnow()
        if running:
            db.commit()
        return len(running)

    return _for_each_tenant_jobs(_fail, label="Shutdown mark-failed")


def _tenant_has_provider_connection(schema: str, provider_name: str) -> bool:
    """Whether a tenant has a stored connection for `provider_name` (tolerates missing tables)."""
    from sqlalchemy.exc import ProgrammingError

    try:
        with tenant_session(schema) as db:
            return get_provider(provider_name).get_connection(db) is not None
    except ProgrammingError:
        return False
    except Exception:
        logger.exception("Connection check failed for %s/%s", schema, provider_name)
        return False


async def sync_all_tenants():
    """Run every configured provider sync across every tenant schema (one job row each)."""
    from sqlalchemy.exc import ProgrammingError

    results = []
    for schema in _get_tenant_schemas():
        for provider in ALL_PROVIDERS:
            if not _tenant_has_provider_connection(schema, provider):
                continue
            try:
                job_id, _created = create_job_row(schema, provider=provider, trigger="scheduled")
            except ProgrammingError:
                logger.warning("Skipping %s/%s: sync_jobs missing (migration pending?)", schema, provider)
                continue
            await run_sync_with_job(schema, job_id, provider)
            results.append({"schema": schema, "provider": provider, "job_id": job_id})
    return results


# ── Loops ─────────────────────────────────────────────────────────────────────

async def _scheduler_loop():
    """Run sync_all_tenants at boot and then every SYNC_INTERVAL_SECONDS, under an advisory lock."""
    conn = engine.connect()
    try:
        got_lock = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY}).scalar()
        if not got_lock:
            logger.info("Sync scheduler: another worker holds the lock; this worker is idle")
            return

        logger.info("Sync scheduler started (providers: %s, interval: %ds)", ", ".join(ALL_PROVIDERS), SYNC_INTERVAL_SECONDS)
        while True:
            try:
                logger.info("Starting scheduled sync...")
                await sync_all_tenants()
            except Exception:
                logger.exception("Scheduled sync error")
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)
    finally:
        conn.close()


async def claim_orphan_jobs() -> int:
    """Resume 'running' jobs younger than the watchdog cutoff at scheduler startup."""
    from sqlalchemy.exc import ProgrammingError

    cutoff = _utcnow() - timedelta(minutes=WATCHDOG_STUCK_MINUTES)
    claimed = 0
    for schema in _get_tenant_schemas():
        try:
            with tenant_session(schema) as db:
                jobs = (
                    db.query(SyncJob)
                    .filter(SyncJob.status == "running", SyncJob.started_at >= cutoff)
                    .order_by(SyncJob.started_at.desc())
                    .all()
                )
                pairs = [(j.id, j.provider) for j in jobs]
        except ProgrammingError:
            pairs = []
        for job_id, provider in pairs:
            logger.info("Claiming orphan running job %d (%s) in %s", job_id, provider, schema)
            await run_sync_with_job(schema, job_id, provider)
            claimed += 1
    return claimed


def notify_sync_request(schema: str, provider: str) -> None:
    """Wake the scheduler process for (schema, provider). Fire-and-forget."""
    with engine.connect() as conn:
        safe_schema = schema.replace("'", "''")
        safe_provider = provider.replace("'", "''")
        conn.execute(text(f"NOTIFY {NOTIFY_CHANNEL}, '{safe_schema}|{safe_provider}'"))
        conn.commit()


async def notify_listener_loop():
    """Wake on Postgres NOTIFY and run the pending manual job for (schema, provider)."""
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    raw = engine.raw_connection()
    try:
        pg_conn = raw.driver_connection
        raw.detach()
        pg_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = pg_conn.cursor()
        cur.execute(f"LISTEN {NOTIFY_CHANNEL}")
        cur.close()
        logger.info("Sync NOTIFY listener attached on channel '%s'", NOTIFY_CHANNEL)

        loop = asyncio.get_running_loop()
        wakeup = asyncio.Event()
        loop.add_reader(pg_conn.fileno(), wakeup.set)
        try:
            while True:
                await wakeup.wait()
                wakeup.clear()
                pg_conn.poll()
                pending: set[tuple[str, str]] = set()
                while pg_conn.notifies:
                    n = pg_conn.notifies.pop(0)
                    if not n.payload or "|" not in n.payload:
                        continue
                    schema, provider = n.payload.split("|", 1)
                    pending.add((schema, provider))
                for schema, provider in pending:
                    await _process_notify(schema, provider)
        finally:
            loop.remove_reader(pg_conn.fileno())
    finally:
        try:
            raw.close()
        except Exception:
            logger.debug("Closing the NOTIFY listener connection failed", exc_info=True)


async def _process_notify(schema: str, provider: str) -> None:
    """Look up the in-flight 'running' job for (schema, provider) and run it."""
    from sqlalchemy.exc import ProgrammingError

    try:
        job_id = find_running_job(schema, provider)
    except ProgrammingError:
        job_id = None
    if job_id is None:
        logger.info("NOTIFY for %s/%s but no running job (already processed?)", schema, provider)
        return
    logger.info("NOTIFY: running %s sync for %s (job %d)", provider, schema, job_id)
    await run_sync_with_job(schema, job_id, provider)


_scheduler_task: asyncio.Task | None = None
_listener_task: asyncio.Task | None = None


def start_scheduler():
    """Start the background sync scheduler and NOTIFY listener tasks."""
    global _scheduler_task, _listener_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    _listener_task = asyncio.create_task(notify_listener_loop())
    logger.info("Sync scheduler + NOTIFY listener tasks created")


def stop_scheduler():
    """Stop background tasks. Call from shutdown."""
    global _scheduler_task, _listener_task
    for t in (_scheduler_task, _listener_task):
        if t and not t.done():
            t.cancel()
    _scheduler_task = None
    _listener_task = None
    logger.info("Sync scheduler stopped")
