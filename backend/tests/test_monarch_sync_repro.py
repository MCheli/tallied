"""Reproduction test for the 500 on POST /api/v1/monarch/sync.

Mocks the Monarch client to feed the route a variety of realistic payload
shapes, so we can find which one trips the 500 we see in production logs.
"""
import logging
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.models.account import Account
from app.models.monarch_link import MonarchAccountConfig, MonarchLink


def _seed_link(db, *, sync_transactions=True, local_account_id=None):
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
    db.flush()
    return link, cfg


def _mock_client(transactions):
    mm = AsyncMock()
    mm.set_token = lambda *a, **k: None
    mm._headers = {}
    mm.get_transactions = AsyncMock(return_value={
        "allTransactions": {
            "results": transactions,
            "totalCount": len(transactions),
        }
    })
    return mm


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _post_sync(client):
    return client.post("/api/v1/monarch/sync")


# ── Scenario 1: well-formed transaction ───────────────────────────────────────

def test_well_formed_transaction(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txns = [{
        "id": "txn-1",
        "date": "2026-04-15",
        "amount": -42.50,
        "merchant": {"name": "Starbucks"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "isRecurring": False,
        "account": {"id": "999", "displayName": "Test Checking"},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[well-formed] status={r.status_code} body={r.text[:200]}")
    assert r.status_code == 200, f"Unexpected: {r.text}"


# ── Scenario 2: category is a string instead of dict (Monarch API drift) ──────

def test_category_as_string(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txns = [{
        "id": "txn-2",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": "Coffee",  # string instead of dict
        "account": {"id": "999"},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[cat-string] status={r.status_code} body={r.text[:300]}")


# ── Scenario 3: category.group is a string ────────────────────────────────────

def test_category_group_as_string(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txns = [{
        "id": "txn-3",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": "Food"},  # group as str
        "account": {"id": "999"},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[group-string] status={r.status_code} body={r.text[:300]}")


# ── Scenario 4: duplicate txn id within same payload (PK violation) ──────────

def test_duplicate_txn_in_payload(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txn = {
        "id": "dup-1",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "account": {"id": "999"},
    }
    txns = [txn, dict(txn)]  # same id twice

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[duplicate-pk] status={r.status_code} body={r.text[:300]}")


# ── Scenario 5: account FK doesn't exist + cfg has stale local_account_id ────

def test_stale_local_account_id(db_session, client, caplog):
    """cfg.local_account_id points at an Account that doesn't exist.

    The route skips creating the Account because cfg.local_account_id is
    truthy (line 473), so on commit the Transaction FK fails.
    """
    _seed_link(db_session, local_account_id="ghost-account")
    db_session.commit()

    txns = [{
        "id": "stale-1",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "account": {"id": "999"},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[stale-fk] status={r.status_code} body={r.text[:500]}")


# ── Scenario 6: amount is None for one txn (skipped) but rest commit ─────────

def test_none_amount(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txns = [{
        "id": "none-amt",
        "date": "2026-04-15",
        "amount": None,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
        "account": {"id": "999"},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[none-amt] status={r.status_code} body={r.text[:200]}")


# ── Scenario 7: account dict missing entirely ────────────────────────────────

def test_account_missing(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    txns = [{
        "id": "no-acct",
        "date": "2026-04-15",
        "amount": -10.0,
        "merchant": {"name": "X"},
        "category": {"name": "Coffee", "group": {"name": "Food"}},
    }]

    with patch("app.api.monarch_routes._get_monarch_client",
               return_value=_mock_client(txns)):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[no-acct] status={r.status_code} body={r.text[:200]}")


# ── Scenario 8: monarch client raises on get_transactions ────────────────────

def test_get_transactions_raises(db_session, client, caplog):
    _seed_link(db_session)
    db_session.commit()

    mm = AsyncMock()
    mm.set_token = lambda *a, **k: None
    mm._headers = {}
    mm.get_transactions = AsyncMock(side_effect=Exception("boom"))

    with patch("app.api.monarch_routes._get_monarch_client", return_value=mm):
        with caplog.at_level(logging.ERROR):
            r = _post_sync(client)
    print(f"\n[client-raises] status={r.status_code} body={r.text[:200]}")
