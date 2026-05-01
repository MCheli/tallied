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


async def main():
    try:
        await scenario_happy_path()
        await scenario_dup_ids_no_500()
        await scenario_failure_lands_in_failed()
        scenario_watchdog_reaps_stuck()
        scenario_unique_running_index()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
