"""End-to-end check of the fire-and-forget Monarch sync flow against PG.

Verifies:
- POST /sync inserts a job row, runs the background task, lands in 'succeeded'
- Concurrent POSTs return the same in-flight job_id (no duplicate task)
- reap_stuck_jobs() flips orphaned 'running' rows to 'failed'
- Sync logic still tolerates the duplicate-id / FK-violation edge cases that
  originally produced the 500
"""
import asyncio
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql://tallied:tallied_dev@localhost/tallied"
SCHEMA = "tenant_claudius"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _session():
    db = SessionLocal()
    db.execute(text(f'SET search_path TO "{SCHEMA}"'))
    return db


def _reset(db):
    db.execute(text("DELETE FROM monarch_sync_jobs"))
    db.execute(text("DELETE FROM monarch_account_configs"))
    db.execute(text("DELETE FROM monarch_links"))
    db.execute(text("DELETE FROM transactions WHERE id LIKE 'monarch-%'"))
    db.execute(text("DELETE FROM accounts WHERE id LIKE 'monarch-%' OR id = 'ghost-account'"))
    db.commit()


def _seed_link(db, *, sync_transactions=True, local_account_id=None):
    from app.models.monarch_link import MonarchLink, MonarchAccountConfig
    link = MonarchLink(email="claudius@tallied.dev", token="fake-token")
    db.add(link)
    db.flush()
    cfg = MonarchAccountConfig(
        monarch_link_id=link.id,
        monarch_account_id="999",
        account_name="Test Checking",
        account_type="Checking",
        institution="Test Bank",
        sync_balances=False,
        sync_transactions=sync_transactions,
        local_account_id=local_account_id,
    )
    db.add(cfg)
    db.commit()


def _mock_client(transactions):
    mm = AsyncMock()
    mm.set_token = lambda *a, **k: None
    mm._headers = {}
    mm.get_accounts = AsyncMock(return_value={"accounts": []})
    mm.get_transactions = AsyncMock(return_value={
        "allTransactions": {
            "results": transactions,
            "totalCount": len(transactions),
        }
    })
    return mm


def _txn(**overrides):
    base = {
        "id": "test-1", "date": "2026-04-15", "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "isRecurring": False,
        "account": {"id": "999", "displayName": "Test"},
    }
    base.update(overrides)
    return base


async def scenario_happy_path():
    """Full /sync flow: enqueue → background runs → status reflects success."""
    from app.services.sync_scheduler import (
        create_job_row, find_running_job, run_sync_with_job,
    )
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    txns = [_txn(id="happy-1"), _txn(id="happy-2", date="2026-04-16")]
    mm = _mock_client(txns)
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        job_id, _created = create_job_row(SCHEMA, trigger="manual")
        await run_sync_with_job(SCHEMA, job_id)

    db = _session()
    try:
        job = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
        ok = job and job.status == "succeeded" and job.txn_added == 2
        print(f"[happy-path] status={job.status if job else 'MISSING'} "
              f"added={job.txn_added if job else '?'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def scenario_dup_ids_no_500():
    """Same id twice in payload — historically caused UniqueViolation 500."""
    from app.services.sync_scheduler import create_job_row, run_sync_with_job
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    dup = _txn(id="d-1")
    mm = _mock_client([dup, dict(dup), _txn(id="", date="2026-04-15"),
                       _txn(id="", date="2026-04-16")])
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        job_id, _created = create_job_row(SCHEMA, trigger="manual")
        await run_sync_with_job(SCHEMA, job_id)

    db = _session()
    try:
        job = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
        ok = job and job.status == "succeeded"
        print(f"[dup-ids] status={job.status} error={job.error or '-'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def scenario_failure_lands_in_failed():
    """Monarch API raises — job row should be 'failed', not stuck 'running'."""
    from app.services.sync_scheduler import create_job_row, run_sync_with_job
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    mm = AsyncMock()
    mm.set_token = lambda *a, **k: None; mm._headers = {}
    mm.get_accounts = AsyncMock(side_effect=Exception("401 Unauthorized"))

    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        job_id, _created = create_job_row(SCHEMA, trigger="manual")
        await run_sync_with_job(SCHEMA, job_id)

    db = _session()
    try:
        job = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
        ok = job and job.status == "failed" and "401" in (job.error or "")
        print(f"[failure-tracked] status={job.status} err='{(job.error or '')[:60]}' "
              f"→ {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


def scenario_watchdog_reaps_stuck():
    """A job stuck in 'running' from a dead worker should self-heal at boot.

    The unique partial index allows only one running row at a time, so we
    test the stuck and fresh cases sequentially rather than simultaneously.
    """
    from app.services.sync_scheduler import reap_stuck_jobs
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
        stuck = MonarchSyncJob(
            status="running", trigger="manual",
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )
        db.add(stuck); db.commit()
        stuck_id = stuck.id
    finally:
        db.close()

    reap_stuck_jobs()

    db = _session()
    try:
        s = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == stuck_id).first()
        # After reaping, slot is free — insert a fresh running row and
        # confirm a second reap doesn't touch it.
        fresh = MonarchSyncJob(
            status="running", trigger="manual",
            started_at=datetime.utcnow(),
        )
        db.add(fresh); db.commit()
        fresh_id = fresh.id
    finally:
        db.close()

    reap_stuck_jobs()

    db = _session()
    try:
        s = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == stuck_id).first()
        f = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == fresh_id).first()
        ok = s.status == "failed" and f.status == "running"
        print(f"[watchdog] stuck={s.status} fresh={f.status} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


def scenario_unique_running_index():
    """A second create_job_row while one is running returns the same id."""
    from app.services.sync_scheduler import create_job_row, mark_running_jobs_failed

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    a, a_created = create_job_row(SCHEMA, trigger="manual")
    b, b_created = create_job_row(SCHEMA, trigger="manual")
    ok = a_created is True and b_created is False and a == b
    print(f"[unique-running] first=({a},{a_created}) second=({b},{b_created}) → "
          f"{'OK' if ok else 'FAIL'}")

    # Cleanup so subsequent runs of this script start fresh.
    n = mark_running_jobs_failed("test cleanup")
    print(f"[shutdown-mark-failed] flipped {n} running → failed → "
          f"{'OK' if n >= 1 else 'FAIL'}")


async def scenario_sync_all_tenants_path():
    """Regression for the tuple-vs-int bug at sync_scheduler.py:460.

    sync_all_tenants is what the 12-hour scheduler loop calls. If the
    create_job_row tuple isn't destructured, run_sync_with_job receives
    a tuple as job_id, the WHERE id = (n, bool) query errors out, and
    the row stays stuck in 'running' forever. This test asserts the row
    reaches a terminal state.
    """
    from app.services.sync_scheduler import sync_all_tenants
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    txns = [_txn(id="sched-1"), _txn(id="sched-2", date="2026-04-16")]
    mm = _mock_client(txns)
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        results = await sync_all_tenants()

    db = _session()
    try:
        # Pick out the run we just kicked off (latest 'scheduled' job for
        # this tenant). It must NOT still be 'running'.
        job = (
            db.query(MonarchSyncJob)
            .filter(MonarchSyncJob.trigger == "scheduled")
            .order_by(MonarchSyncJob.id.desc())
            .first()
        )
        ok = job and job.status == "succeeded" and job.txn_added == 2
        print(f"[scheduled-path] status={job.status if job else 'MISSING'} "
              f"added={job.txn_added if job else '?'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def scenario_notify_listener_e2e():
    """Web-tier NOTIFY → scheduler listener wakes → job processed.

    Spins up notify_listener_loop as a background task, then simulates the
    web tier by inserting a 'running' job row and calling notify_sync_request.
    Asserts the listener picks it up and finalizes the job within a few
    seconds (no polling cadence — purely event-driven via LISTEN).
    """
    from app.services.sync_scheduler import (
        create_job_row, notify_listener_loop, notify_sync_request,
    )
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    txns = [_txn(id="notify-1")]
    mm = _mock_client(txns)

    listener_task = asyncio.create_task(notify_listener_loop())
    try:
        await asyncio.sleep(0.5)  # let listener attach LISTEN
        with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
            job_id, created = create_job_row(SCHEMA, trigger="manual")
            assert created, "expected new job to be created"
            notify_sync_request(SCHEMA)
            # Poll the row until terminal — listener is event-driven so this
            # should resolve in well under a second.
            for _ in range(30):  # 30 * 0.2s = 6s ceiling
                await asyncio.sleep(0.2)
                d = _session()
                try:
                    j = d.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
                    if j and j.status != "running":
                        break
                finally:
                    d.close()
    finally:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

    db = _session()
    try:
        j = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
        ok = j and j.status == "succeeded" and j.txn_added == 1
        print(f"[notify-e2e] status={j.status if j else 'MISSING'} "
              f"added={j.txn_added if j else '?'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def scenario_claim_on_boot():
    """Web inserts a job while scheduler is down. Scheduler boots, claims it.

    Mimics the deploy-time race: web tier creates a 'running' row but the
    scheduler container isn't up to receive the NOTIFY. claim_orphan_jobs
    on scheduler boot must pick it up.
    """
    from app.services.sync_scheduler import claim_orphan_jobs, create_job_row
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    # Web tier inserts the job row (no NOTIFY listener attached).
    job_id, _created = create_job_row(SCHEMA, trigger="manual")

    # Scheduler boots — should claim and run the job.
    txns = [_txn(id="claim-1"), _txn(id="claim-2", date="2026-04-16")]
    mm = _mock_client(txns)
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        claimed = await claim_orphan_jobs()

    db = _session()
    try:
        j = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == job_id).first()
        ok = claimed >= 1 and j and j.status == "succeeded" and j.txn_added == 2
        print(f"[claim-on-boot] claimed={claimed} status={j.status if j else 'MISSING'} "
              f"added={j.txn_added if j else '?'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def scenario_bulk_existence_check():
    """Verify the new bulk SELECT IN matches the per-row results.

    Pre-load some monarch transactions, then run a second sync with a
    payload that has both new and existing ids. Expect 'updated' for the
    pre-existing ids and 'added' for the new ones.
    """
    from app.services.sync_scheduler import create_job_row, run_sync_with_job
    from app.models.monarch_sync_job import MonarchSyncJob

    db = _session()
    try:
        _reset(db); _seed_link(db)
    finally:
        db.close()

    # First sync: 3 new transactions.
    initial = [_txn(id=f"bulk-{i}", date=f"2026-04-{10+i}") for i in range(3)]
    mm = _mock_client(initial)
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        j1, _ = create_job_row(SCHEMA, trigger="manual")
        await run_sync_with_job(SCHEMA, j1)

    # Second sync: 2 existing (bulk-0, bulk-1) + 2 new (bulk-3, bulk-4).
    payload = [
        _txn(id="bulk-0", date="2026-04-10", amount=-99.99),  # update
        _txn(id="bulk-1", date="2026-04-11", amount=-88.88),  # update
        _txn(id="bulk-3", date="2026-04-13"),                 # new
        _txn(id="bulk-4", date="2026-04-14"),                 # new
    ]
    mm = _mock_client(payload)
    with patch("app.services.sync_scheduler._get_monarch_client", return_value=mm):
        j2, _ = create_job_row(SCHEMA, trigger="manual")
        await run_sync_with_job(SCHEMA, j2)

    db = _session()
    try:
        j = db.query(MonarchSyncJob).filter(MonarchSyncJob.id == j2).first()
        ok = j and j.status == "succeeded" and j.txn_added == 2 and j.txn_updated == 2
        print(f"[bulk-exists] added={j.txn_added if j else '?'} "
              f"updated={j.txn_updated if j else '?'} → {'OK' if ok else 'FAIL'}")
    finally:
        db.close()


async def main():
    try:
        await scenario_happy_path()
        await scenario_dup_ids_no_500()
        await scenario_failure_lands_in_failed()
        scenario_watchdog_reaps_stuck()
        scenario_unique_running_index()
        await scenario_sync_all_tenants_path()
        await scenario_bulk_existence_check()
        await scenario_claim_on_boot()
        await scenario_notify_listener_e2e()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
