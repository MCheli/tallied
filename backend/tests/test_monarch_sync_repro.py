"""Tests for the fire-and-forget Monarch sync route + status endpoint.

The actual Monarch API integration logic in sync_scheduler._sync_tenant is
exercised by scripts/repro_monarch_500.py against real Postgres (which the
CI SQLite setup can't simulate due to FK/constraint differences). These
tests focus on the route boundary: 202 contract, idempotency, and status.
"""
from unittest.mock import patch

import pytest

from app.models.monarch_link import MonarchLink
from app.models.monarch_sync_job import MonarchSyncJob


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
    with patch("app.services.sync_scheduler.create_job_row", return_value=42) as cj, \
         patch("app.services.sync_scheduler.find_running_job", return_value=None), \
         patch("app.services.sync_scheduler.run_sync_with_job") as rs, \
         patch("app.api.monarch_routes.asyncio.create_task") as ct:
        r = client.post("/api/v1/monarch/sync")
    assert r.status_code == 202
    body = r.json()
    assert body == {"job_id": 42, "status": "running", "queued": True}
    cj.assert_called_once()
    ct.assert_called_once()


def test_sync_returns_existing_running_job(db_session, client):
    _seed_link(db_session)
    with patch("app.services.sync_scheduler.create_job_row") as cj, \
         patch("app.services.sync_scheduler.find_running_job", return_value=99), \
         patch("app.api.monarch_routes.asyncio.create_task") as ct:
        r = client.post("/api/v1/monarch/sync")
    assert r.status_code == 202
    assert r.json() == {"job_id": 99, "status": "running", "queued": False}
    cj.assert_not_called()
    ct.assert_not_called()


def test_status_with_no_jobs_returns_none(db_session, client):
    r = client.get("/api/v1/monarch/sync/status")
    assert r.status_code == 200
    assert r.json() == {"job_id": None, "status": "none"}


def test_status_returns_latest_job(db_session, client):
    from datetime import datetime, timedelta
    older = MonarchSyncJob(
        status="succeeded", trigger="scheduled",
        started_at=datetime.utcnow() - timedelta(hours=1),
        finished_at=datetime.utcnow() - timedelta(hours=1),
        balances_synced=2, txn_added=5, txn_updated=1,
    )
    newer = MonarchSyncJob(
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
