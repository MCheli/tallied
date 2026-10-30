"""Older 401(k) statements never overwrite newer data (UND-401K-001); forecast-year RSU rule (PLAN-002);
receipts are queued and processed after the webhook response (FEED-003)."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.models.account import Account
from app.models.import_session import ImportSession
from app.models.retirement import RetirementAccount, RetirementSnapshot


def _confirm_statement(client, db, statement_end: str, total: float, session_id: str):
    db.add(ImportSession(
        id=session_id, status="review", context="retirement", filename="stmt.pdf", file_type="pdf", chat_messages="[]",
        proposed_changes=json.dumps([{
            "id": "r1", "table": "retirement_accounts", "action": "upsert",
            "fields": [
                {"column": "statement_end", "old_value": None, "new_value": statement_end, "is_new": False, "source": "ai_parsed"},
                {"column": "total_balance", "old_value": None, "new_value": total, "is_new": False, "source": "ai_parsed"},
                {"column": "total_employee_contributions_lifetime", "old_value": None, "new_value": 42000, "is_new": False, "source": "ai_parsed"},
            ],
            "data": {"holdings": []},
        }]),
        accepted_change_ids=json.dumps(["r1"]),
    ))
    db.commit()
    factory = sessionmaker(bind=db.get_bind())
    with patch("app.database.SessionLocal", factory), patch("app.services.webhook_service.deliver_webhook", lambda *a, **k: 0):
        res = client.post(f"/api/v1/import/{session_id}/confirm")
    assert res.status_code == 200, res.text


def test_older_statement_adds_history_but_keeps_current_balance(client, db_session):
    db_session.add(Account(id="k401", name="401(k)", account_type="investment_401k", display_group="Retirement", include_in_nw=True))
    db_session.add(RetirementAccount(plan_name="PLAN", provider="Fidelity", total_balance=Decimal("185432.50"),
                                     statement_end=date(2025, 12, 31), total_employee_contributions=Decimal("50000")))
    db_session.commit()

    _confirm_statement(client, db_session, "2025-06-30", 150000, "older0000001")
    acct = db_session.query(RetirementAccount).one()
    assert float(acct.total_balance) == 185432.50, "an older statement must not overwrite the current balance"
    assert acct.statement_end == date(2025, 12, 31)
    assert float(acct.total_employee_contributions) == 50000, "lifetime totals never decrease"
    snaps = {s.snapshot_date: float(s.balance) for s in db_session.query(RetirementSnapshot).all()}
    assert snaps.get(date(2025, 6, 30)) == 150000, "the older statement is kept as history"

    _confirm_statement(client, db_session, "2026-03-31", 190000, "newer0000001")
    db_session.expire_all()
    acct = db_session.query(RetirementAccount).one()
    assert float(acct.total_balance) == 190000 and acct.statement_end == date(2026, 3, 31)
    summary = client.get("/api/v1/retirement/summary").json()
    assert summary["account"]["total_balance"] == 190000


def test_forecast_year_rsu_income_is_actual_vests_plus_scheduled_at_todays_price(client, db_session, born_30):
    from app.models.income import W2Record
    from app.models.investment import RSUGrant, StockPrice, VestEvent

    year = date.today().year
    db_session.add(W2Record(tax_year=year - 1, gross_pay=Decimal("210000"), base_salary=Decimal("145000"), rsu_income=Decimal("65000")))
    db_session.add(RSUGrant(id="G1", company="MSFT", symbol="MSFT", grant_date=date(year - 2, 5, 15), total_shares=300, vested_shares=100, unvested_shares=200, sellable_shares=100))
    db_session.add(StockPrice(symbol="MSFT", price_date=date.today(), close_price=Decimal("100"), source="seed"))
    db_session.add_all([
        VestEvent(grant_id="G1", vest_date=date(year, 1, 15), shares=100, is_actual=True, fmv_at_vest=Decimal("80"), vest_period=1),
        VestEvent(grant_id="G1", vest_date=date(year, 12, 15), shares=100, is_actual=False, vest_period=2),
        VestEvent(grant_id="G1", vest_date=date(year + 1, 12, 15), shares=100, is_actual=False, vest_period=3),
    ])
    db_session.commit()
    plan = client.post("/api/v1/plans/", json={"name": "T", "scenario_type": "base", "assumptions": []}).json()
    table = client.get(f"/api/v1/plans/{plan['id']}/table").json()
    forecast = table["rows"][str(year)]
    assert forecast["status"] == "forecast"
    # actual vest at its FMV (100 x 80) + the remaining scheduled vest at today's price (100 x 100)
    assert forecast["rsu_income"]["value"] == 18000.0
    next_year = table["rows"][str(year + 1)]
    assert next_year["rsu_income"]["value"] == 10000.0, "plan years with a known vest schedule use it at today's price"


def test_inbound_receipt_is_queued_then_processed(client, db_session, monkeypatch):
    from contextlib import contextmanager

    from app.ai import client as ai_client
    from app.ai.schemas import ReceiptExtraction
    from app.api import email_import
    from app.models.email_forwarding_address import EmailForwardingAddress
    from app.models.email_receipt import EmailReceipt
    from app.models.tenant import Tenant
    from app.models.transaction import Transaction

    db_session.add(Tenant(id=3, slug="t3", display_name="T", schema_name="tenant_claudius", is_active=True))
    db_session.add(EmailForwardingAddress(user_id=1, tenant_id=3, email="me@home.test", is_active=True))
    db_session.commit()

    @contextmanager
    def fake_tenant_session(schema):
        assert schema == "tenant_claudius"
        yield db_session

    parsed = ReceiptExtraction(parse_error=None, merchant="Shop", amount=40.0, date=date.today().isoformat(), category="Shopping",
                               items=[], tax=2.5, shipping=None, order_id="A1", is_refund=False)
    monkeypatch.setattr(email_import.settings, "email_webhook_secret", "s3cret")
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "sk-ant-test")
    factory = sessionmaker(bind=db_session.get_bind())
    with patch.object(email_import, "SessionLocal", factory), patch.object(email_import, "tenant_session", fake_tenant_session), \
         patch("app.services.email_receipt_service.extract", lambda *a, **k: parsed):
        res = client.post("/api/v1/email-import/inbound", headers={"X-Email-Webhook-Secret": "s3cret"},
                          json={"from_email": "orders@shop.test", "forwarded_by": "me@home.test", "to": "receipts@x", "subject": "Order", "text": "body"})
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "queued"
    receipt = db_session.query(EmailReceipt).one()  # the background task ran after the response
    assert receipt.status == "parsed" and receipt.transaction_id
    txn = db_session.get(Transaction, receipt.transaction_id)
    assert float(txn.amount) == -42.5

    wrong = client.post("/api/v1/email-import/inbound", headers={"X-Email-Webhook-Secret": "nope"},
                        json={"from_email": "x@y", "forwarded_by": "me@home.test", "to": "r", "subject": "s"})
    assert wrong.status_code == 401
