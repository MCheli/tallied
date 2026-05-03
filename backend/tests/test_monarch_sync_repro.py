"""Tests for the fire-and-forget Monarch sync route + status endpoint.

The actual Monarch API integration logic in sync_scheduler._sync_tenant is
exercised by scripts/repro_monarch_500.py against real Postgres (which the
CI SQLite setup can't simulate due to FK/constraint differences). These
tests focus on the route boundary: 202 contract, idempotency, and status.
"""
from unittest.mock import patch

import pytest

from app.models.monarch_link import MonarchLink
from app.models.sync_job import SyncJob as MonarchSyncJob


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _seed_link(db):
    db.add(MonarchLink(email="claudius@tallied.dev", token="fake"))
    db.commit()


def test_sync_no_connection_returns_skipped(db_session, client):
    r = client.post("/api/v1/monarch/sync")
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"


def test_sync_enqueues_job_and_returns_202(db_session, client):
    _seed_link(db_session)
    with patch("app.services.sync_scheduler.create_job_row", return_value=(42, True)) as cj, \
         patch("app.api.monarch_routes.asyncio.create_task") as ct:
        r = client.post("/api/v1/monarch/sync")
    assert r.status_code == 202
    body = r.json()
    assert body == {"job_id": 42, "status": "running", "queued": True}
    cj.assert_called_once()
    ct.assert_called_once()


def test_sync_returns_existing_running_job_on_race(db_session, client):
    """create_job_row hits the unique partial index, returns (existing_id, False)."""
    _seed_link(db_session)
    with patch("app.services.sync_scheduler.create_job_row", return_value=(99, False)) as cj, \
         patch("app.api.monarch_routes.asyncio.create_task") as ct:
        r = client.post("/api/v1/monarch/sync")
    assert r.status_code == 202
    assert r.json() == {"job_id": 99, "status": "running", "queued": False}
    cj.assert_called_once()
    ct.assert_not_called()


def test_status_with_no_jobs_returns_none(db_session, client):
    r = client.get("/api/v1/monarch/sync/status")
    assert r.status_code == 200
    assert r.json() == {"job_id": None, "status": "none"}


@pytest.mark.asyncio
async def test_sync_all_tenants_passes_int_not_tuple_to_run_sync():
    """Regression: create_job_row returns (id, bool); sync_all_tenants must
    destructure it. If the tuple leaks through, run_sync_with_job receives
    `(8, False)` as the job_id and Postgres rejects the WHERE clause with
    'operator does not exist: integer = record', leaving the row stuck."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services import sync_scheduler

    # Monarch is no longer in ALL_PROVIDERS — pin the test to whichever
    # provider is active so it stays a real regression check.
    active = sync_scheduler.ALL_PROVIDERS[0]
    with patch.object(sync_scheduler, "_get_tenant_schemas", return_value=["tenant_x"]), \
         patch.object(sync_scheduler, "_tenant_has_provider_connection",
                      side_effect=lambda schema, provider: provider == active), \
         patch.object(sync_scheduler, "create_job_row", return_value=(7, True)) as cj, \
         patch.object(sync_scheduler, "run_sync_with_job",
                      new_callable=AsyncMock) as rs:
        await sync_scheduler.sync_all_tenants()

    cj.assert_called_once_with("tenant_x", provider=active, trigger="scheduled")
    rs.assert_awaited_once_with("tenant_x", 7, active)
    # Specifically the second arg must be a plain int, not a tuple.
    args = rs.await_args.args
    assert isinstance(args[1], int), f"expected int, got {type(args[1])}: {args[1]!r}"


def test_status_returns_latest_job(db_session, client):
    from datetime import datetime, timedelta
    older = MonarchSyncJob(
        provider="monarch",
        status="succeeded", trigger="scheduled",
        started_at=datetime.utcnow() - timedelta(hours=1),
        finished_at=datetime.utcnow() - timedelta(hours=1),
        balances_synced=2, txn_added=5, txn_updated=1,
    )
    newer = MonarchSyncJob(
        provider="monarch",
        status="failed", trigger="manual",
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        error="boom",
    )
    db_session.add_all([older, newer])
    db_session.commit()

    r = client.get("/api/v1/monarch/sync/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["trigger"] == "manual"
    assert body["error"] == "boom"
