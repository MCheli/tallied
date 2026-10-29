"""Outbound webhooks fire on import confirm and after a successful sync (PLAT-API-002)."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.models.import_session import ImportSession
from app.models.sync_job import SyncJob
from app.models.tenant import Tenant


def test_import_confirm_delivers_import_completed(client, db_session):
    session = ImportSession(
        id="sess00000001", status="review", context="income", filename="2025 W2.pdf", file_type="pdf",
        chat_messages="[]",
        proposed_changes=json.dumps([{
            "id": "c1", "table": "w2_records", "action": "upsert", "tax_year": 2025,
            "fields": [{"column": "gross_pay", "old_value": None, "new_value": 210000, "is_new": True, "source": "ai_parsed"}],
        }]),
        accepted_change_ids=json.dumps(["c1"]),
    )
    db_session.add(session)
    db_session.commit()

    delivered = []
    factory = sessionmaker(bind=db_session.get_bind())
    with patch("app.database.SessionLocal", factory), \
         patch("app.services.webhook_service.deliver_webhook", lambda event, tenant_id, payload, db: delivered.append((event, tenant_id, payload)) or 1):
        res = client.post("/api/v1/import/sess00000001/confirm")
    assert res.status_code == 200, res.text
    assert delivered and delivered[0][0] == "import.completed" and delivered[0][1] == 1
    assert delivered[0][2]["changes_applied"] == 1


def test_sync_finalize_delivers_balance_and_transaction_events(db_session):
    from contextlib import contextmanager

    from app.services import sync_scheduler

    db_session.add(Tenant(id=7, slug="t7", display_name="T", schema_name="tenant_abcdefgh", is_active=True))
    job = SyncJob(provider="simplefin", status="running", trigger="manual")
    db_session.add(job)
    db_session.commit()

    @contextmanager
    def fake_tenant_session(schema):
        yield db_session

    delivered = []
    factory = sessionmaker(bind=db_session.get_bind())
    with patch.object(sync_scheduler, "tenant_session", fake_tenant_session), \
         patch("app.database.SessionLocal", factory), \
         patch("app.services.webhook_service.deliver_webhook", lambda event, tenant_id, payload, db: delivered.append((event, tenant_id)) or 1):
        sync_scheduler._finalize_job("tenant_abcdefgh", job.id, {"balances_synced": 2, "txn_added": 3, "txn_updated": 0})
    db_session.refresh(job)
    assert job.status == "succeeded" and job.balances_synced == 2
    assert delivered == [("balance.updated", 7), ("transaction.created", 7)]
