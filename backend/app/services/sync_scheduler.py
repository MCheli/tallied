"""
Background scheduler for automatic Monarch Money syncs.

Runs as an asyncio task started during app lifespan. Syncs balances
(with history backfill) and transactions for all tenants that have
a Monarch connection configured.
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
from app.models.monarch_sync_job import MonarchSyncJob
from app.models.transaction import Transaction
from app.parsers.monarch import ACCOUNT_TYPE_MAP, DISPLAY_GROUP_MAP

logger = logging.getLogger("tallied.sync")

# Sync interval: 12 hours (twice per day)
SYNC_INTERVAL_SECONDS = 12 * 60 * 60

# Watchdog: jobs stuck in 'running' longer than this are marked failed at boot.
WATCHDOG_STUCK_MINUTES = 15


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


async def _sync_tenant(schema: str) -> dict:
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
                exists = db.query(BalanceSnapshot).filter(
                    BalanceSnapshot.account_id == local_id,
                    BalanceSnapshot.snapshot_date == snap_date,
                    BalanceSnapshot.source == "monarch",
                ).first()
                if not exists:
                    db.add(BalanceSnapshot(
                        account_id=local_id, snapshot_date=snap_date,
                        balance=Decimal(str(snap_balance)), source="monarch",
                    ))

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

                existing_txn = db.query(Transaction).filter(Transaction.id == local_txn_id).first()
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


async def run_sync_with_job(schema: str, job_id: int) -> None:
    """Execute a sync against `schema` and update the existing job row.

    Used by the route handler (which inserts the job row before returning 202)
    and by the scheduler (which inserts a row per cycle). Always lands in a
    terminal state — never leaves a row in 'running'.
    """
    try:
        result = await _sync_tenant(schema)
        _finalize_job(schema, job_id, result)
    except Exception as e:
        logger.exception("Monarch sync crashed for %s job=%d", schema, job_id)
        _finalize_job(schema, job_id, {"error": str(e)})


def _finalize_job(schema: str, job_id: int, result: dict) -> None:
    db = _get_tenant_session(schema)
    try:
        job = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
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


def create_job_row(schema: str, trigger: str) -> int:
    """Insert a new monarch_sync_jobs row with status='running'. Returns the id.

    Captures the autoincrement id via flush() before commit — the engine's
    pool-checkout handler resets search_path to public on the next checkout,
    so a post-commit refresh would query the wrong schema.
    """
    db = _get_tenant_session(schema)
    try:
        job = MonarchSyncJob(status="running", trigger=trigger)
        db.add(job)
        db.flush()
        job_id = job.id
        db.commit()
        return job_id
    finally:
        db.close()


def find_running_job(schema: str) -> int | None:
    """Return the id of the in-flight job for this tenant, if any."""
    db = _get_tenant_session(schema)
    try:
        job = (
            db.query(MonarchSyncJob)
            .filter(MonarchSyncJob.status == "running")
            .order_by(MonarchSyncJob.started_at.desc())
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
                db.query(MonarchSyncJob)
                .filter(
                    MonarchSyncJob.status == "running",
                    MonarchSyncJob.started_at < cutoff,
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
        logger.warning("Watchdog reaped %d stuck Monarch sync job(s)", total)


async def sync_all_tenants():
    """Run Monarch sync across all tenant schemas, recording a job row each."""
    schemas = _get_tenant_schemas()
    results = []
    for schema in schemas:
        # Skip tenants with no Monarch connection — don't pollute job table.
        db = _get_tenant_session(schema)
        try:
            link = db.query(MonarchLink).first()
        finally:
            db.close()
        if not link:
            continue
        job_id = create_job_row(schema, trigger="scheduled")
        await run_sync_with_job(schema, job_id)
        results.append({"schema": schema, "job_id": job_id})
    return results


async def _scheduler_loop():
    """Background loop that runs Monarch sync on a fixed interval.

    Runs an immediate sync on startup, then sleeps the full interval between
    runs. Without the immediate sync, every container restart (e.g. Watchtower
    auto-update) would defer the next sync by 12 hours.
    """
    logger.info("Monarch sync scheduler started (interval: %ds)", SYNC_INTERVAL_SECONDS)
    while True:
        try:
            logger.info("Starting scheduled Monarch sync...")
            await sync_all_tenants()
        except Exception as e:
            logger.error("Scheduled Monarch sync error: %s", e)
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


_scheduler_task: asyncio.Task | None = None


def start_scheduler():
    """Start the background sync scheduler. Call from app lifespan startup."""
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Monarch sync scheduler task created")


def stop_scheduler():
    """Stop the background sync scheduler. Call from app lifespan shutdown."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Monarch sync scheduler stopped")
    _scheduler_task = None
