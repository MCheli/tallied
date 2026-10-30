"""AI block: one client, structured outputs, labelled estimates, deterministic projections (NFR-AI-001)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.ai import client as ai_client
from app.ai.schemas import IncomeExtraction, ReceiptExtraction, VehicleValuation
from app.services import valuation


class FakeMessages:
    """Stands in for client.messages: records calls, returns canned responses."""

    def __init__(self, parsed=None, content=None, stop_reason="end_turn", raise_exc=None):
        self.parsed = parsed
        self.content = content or []
        self.stop_reason = stop_reason
        self.raise_exc = raise_exc
        self.calls = []

    def _response(self):
        return SimpleNamespace(
            parsed_output=self.parsed, content=self.content, stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    def parse(self, **kwargs):
        self.calls.append(("parse", kwargs))
        if self.raise_exc:
            raise self.raise_exc
        return self._response()

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        if self.raise_exc:
            raise self.raise_exc
        return self._response()


@pytest.fixture
def fake_ai(monkeypatch):
    """Patch the Anthropic client; yields the FakeMessages so tests can set responses and inspect calls."""
    fake = FakeMessages()
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(ai_client, "get_client", lambda: SimpleNamespace(messages=fake))
    yield fake


def test_extract_uses_configured_model_and_schema(fake_ai):
    fake_ai.parsed = IncomeExtraction(findings=[])
    result = ai_client.extract(IncomeExtraction, content="doc", instructions="read it", tier="import", purpose="t")
    assert isinstance(result, IncomeExtraction)
    kind, kwargs = fake_ai.calls[0]
    assert kind == "parse"
    assert kwargs["model"] == ai_client.settings.ai_model_import == "claude-opus-5-5"
    assert kwargs["output_format"] is IncomeExtraction
    assert kwargs["system"] == "read it"


def test_extract_without_key_raises_503(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "")
    with pytest.raises(ai_client.AIUnavailable) as exc:
        ai_client.extract(IncomeExtraction, content="x", instructions="y")
    assert exc.value.status_code == 503


def test_extract_translates_refusal_and_truncation(fake_ai):
    fake_ai.parsed = IncomeExtraction(findings=[])
    fake_ai.stop_reason = "refusal"
    with pytest.raises(ai_client.AIError, match="declined"):
        ai_client.extract(IncomeExtraction, content="x", instructions="y")
    fake_ai.stop_reason = "max_tokens"
    with pytest.raises(ai_client.AIError, match="cut off"):
        ai_client.extract(IncomeExtraction, content="x", instructions="y")


def test_vehicle_curve_interpolates_history_and_projects_deterministically():
    history, projections = valuation.vehicle_value_curve(
        purchase_price=28500, purchase_year=2019, current_value=22000, current_year=2026,
        annual_depreciation_pct=10,
    )
    assert [y for y, _ in history] == [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    values = [float(v) for _, v in history]
    assert values[-1] == 22000 and all(a > b for a, b in zip(values, values[1:]))
    assert [y for y, _ in projections] == [2027, 2028, 2029, 2030, 2031]
    assert float(projections[0][1]) == 19800 and float(projections[4][1]) == round(22000 * 0.9 ** 5)
    # the rate is clamped, never trusted blindly
    _, wild = valuation.vehicle_value_curve(purchase_price=None, purchase_year=None, current_value=1000,
                                            current_year=2026, annual_depreciation_pct=400)
    assert float(wild[0][1]) == 400


def test_property_projection_clamps_rate():
    pts = valuation.property_projection(current_value=520000, current_year=2026, annual_appreciation_pct=3)
    assert len(pts) == 8 and float(pts[0][1]) == 535600
    pts = valuation.property_projection(current_value=100, current_year=2026, annual_appreciation_pct=90)
    assert float(pts[0][1]) == 115


def test_refresh_value_stores_labelled_estimate(client, fake_ai, db_session):
    from app.models.asset import Vehicle
    from app.models.asset_value_history import AssetValueHistory

    v = Vehicle(year=2019, make="Toyota", model="RAV4", purchase_price=Decimal("28500"), purchase_date=date(2019, 8, 15))
    db_session.add(v)
    db_session.commit()
    fake_ai.parsed = VehicleValuation(current_value=22000, confidence="medium", annual_depreciation_pct=12,
                                      reasoning="Typical RAV4 depreciation.")
    res = client.post(f"/api/v1/assets/vehicles/{v.id}/refresh-value")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] is True and body["confidence"] == "medium" and body["model"] == "claude-sonnet-5-5"
    db_session.refresh(v)
    assert v.valuation_source == "ai" and v.valuation_model == "claude-sonnet-5-5" and v.valuation_confidence == "medium"
    rows = db_session.query(AssetValueHistory).filter_by(vehicle_id=v.id).all()
    assert sum(1 for r in rows if r.source == "purchase") == 1
    assert sum(1 for r in rows if r.is_projected) == 5
    assert all(r.source in ("purchase", "ai_estimate") for r in rows)


def test_refresh_value_failure_is_an_error_not_a_silent_200(client, fake_ai, db_session):
    from app.models.asset import Vehicle

    v = Vehicle(year=2015, make="Honda", model="Civic")
    db_session.add(v)
    db_session.commit()
    import anthropic
    fake_ai.raise_exc = anthropic.APIConnectionError(request=None)
    res = client.post(f"/api/v1/assets/vehicles/{v.id}/refresh-value")
    assert res.status_code == 502
    assert "Valuation unavailable" in res.json()["detail"]


def test_create_vehicle_never_calls_ai(client, fake_ai):
    res = client.post("/api/v1/assets/vehicles", json={"year": 2020, "make": "Ford", "model": "Bronco"})
    assert res.status_code == 200, res.text
    assert res.json()["estimated_value"] is None
    assert fake_ai.calls == []


def test_receipt_parse_returns_error_for_non_receipts(fake_ai):
    from app.services.email_receipt_service import parse_receipt_with_ai

    fake_ai.parsed = ReceiptExtraction(parse_error="newsletter, not a receipt", merchant=None, amount=None, date=None,
                                       category=None, items=[], tax=None, shipping=None, order_id=None, is_refund=False)
    assert parse_receipt_with_ai("Hi", "body", "x@y.z") == {"error": "newsletter, not a receipt"}
    _, kwargs = fake_ai.calls[0]
    assert "<email>" in kwargs["messages"][0]["content"]


def test_receipt_to_transaction(db_session):
    from app.models.email_receipt import EmailReceipt
    from app.services.email_receipt_service import create_transaction_from_receipt

    receipt = EmailReceipt(from_email="orders@shop.test", forwarded_by="me@home.test", subject="Order", status="received")
    db_session.add(receipt)
    db_session.flush()
    txn = create_transaction_from_receipt(db_session, {
        "merchant": "Shop", "amount": 40.0, "tax": 2.5, "shipping": 0, "date": "2026-10-20",
        "category": "Shopping", "items": [{"name": "Lamp", "qty": 1, "price": 40}], "order_id": "A1", "is_refund": False,
    }, receipt)
    assert txn.amount == Decimal("-42.5") and txn.date == date(2026, 10, 20) and txn.source == "email_receipt"
    assert "Order: A1" in txn.notes and "Lamp" in txn.notes
    with pytest.raises(ValueError):
        create_transaction_from_receipt(db_session, {"merchant": "x"}, receipt)


def test_import_upload_uses_schema_and_builds_w2_changes(client, fake_ai, db_session):
    from app.ai.schemas import Finding

    fake_ai.parsed = IncomeExtraction(findings=[
        Finding(field="Box 1 Wages", value="$197,700.00", value_numeric=197700, category="income", confidence="high", db_field="w2_gross_pay"),
        Finding(field="Box 2 Federal", value="$38,500.00", value_numeric=38500, category="income", confidence="high", db_field="w2_federal_tax"),
        Finding(field="Employer", value="Microsoft", value_numeric=None, category="other", confidence="high", db_field=None),
    ])
    res = client.post("/api/v1/import/upload", files={"file": ("2025 W2.pdf", b"%PDF-1.4 fake", "application/pdf")},
                      data={"context": "income"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "review" and body["findings_count"] == 3
    kind, kwargs = fake_ai.calls[0]
    assert kind == "parse" and kwargs["output_format"] is IncomeExtraction and kwargs["model"] == "claude-opus-5-5"
    assert kwargs["messages"][0]["content"][0]["type"] == "document"
    change = next(c for c in body["proposed_changes"] if c["table"] == "w2_records")
    assert change["tax_year"] == 2025
    assert {f["column"] for f in change["fields"]} == {"gross_pay", "federal_tax"}
    assert any(m["field"] == "w2_state_tax" for m in body["missing_fields"])


def test_import_upload_without_key_is_503(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "")
    res = client.post("/api/v1/import/upload", files={"file": ("x.pdf", b"x", "application/pdf")}, data={"context": "income"})
    assert res.status_code == 503
    assert "FINANCE_ANTHROPIC_API_KEY" in res.json()["detail"]


def test_chat_action_comes_from_the_tool_and_is_whitelisted():
    from app.api.import_unified import _text_and_action

    good = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="Done, I added it."),
        SimpleNamespace(type="tool_use", name="propose_field_change",
                        input={"action": "add_field", "table": "w2_records", "column": "base_salary", "value": "155,000", "tax_year": 2025}),
    ])
    text, action = _text_and_action(good, "income")
    assert text == "Done, I added it."
    assert action == {"action": "add_field", "table": "w2_records", "column": "base_salary", "value": 155000, "tax_year": 2025}

    bad = SimpleNamespace(content=[
        SimpleNamespace(type="tool_use", name="propose_field_change",
                        input={"action": "add_field", "table": "w2_records", "column": "password_hash", "value": "x", "tax_year": None}),
    ])
    assert _text_and_action(bad, "income") == ("", None)


def test_property_refresh_keeps_manual_entries_and_labels_projections(client, fake_ai, db_session):
    from app.ai.schemas import PropertyOutlook
    from app.models.account import Account
    from app.models.property import Mortgage
    from app.models.property_value_history import PropertyValueHistory

    acct = Account(id="prop-1", name="456 Oak Street", account_type="real_estate", display_group="Home Equity", include_in_nw=True)
    db_session.add(acct)
    db_session.add(Mortgage(account_id="prop-1", original_amount=Decimal("380000"), current_balance=Decimal("362450"),
                            rate=Decimal("0.0425"), monthly_payment=Decimal("2450"), property_address="456 Oak Street, Springfield, MA 01101"))
    db_session.commit()
    res = client.post("/api/v1/property/valuation", json={"value": 515000, "source": "Tax Assessment", "valuation_date": "2026-01-01"})
    assert res.status_code == 200, res.text

    fake_ai.parsed = PropertyOutlook(annual_appreciation_pct=3.0, confidence="medium", commentary="Steady market.")
    realtor = {"estimate": 520000, "details": {"beds": 3}, "tax_history": [{"year": 2025, "assessed_value": 500000}], "sources": []}
    with patch("app.api.property.get_property_estimate", lambda address: realtor):
        res = client.post("/api/v1/property/refresh-history")
    assert res.status_code == 200, res.text
    rows = db_session.query(PropertyValueHistory).filter_by(account_id="prop-1").all()
    assert any(r.source == "manual" and float(r.value) == 515000 for r in rows), "the owner's tax assessment survived"
    projected = [r for r in rows if r.is_projected]
    assert len(projected) == 8 and all(r.source == "ai_projection" for r in projected)
    import json
    label = json.loads(projected[0].details)
    assert label["source"] == "ai" and label["model"] == "claude-sonnet-5-5" and label["confidence"] == "medium"
    assert float(projected[0].value) == 535600


def test_no_direct_anthropic_client_outside_app_ai():
    """Every Claude call goes through app/ai (NFR-AI-001)."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.parts[-2] == "ai":
            continue
        text = path.read_text()
        if "anthropic.Anthropic(" in text or "messages.create(" in text or "claude-sonnet-4-20250514" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_import_logs_endpoint_lists_confirmed_imports(client, db_session):
    from app.models.import_log import ImportLog

    db_session.add(ImportLog(source="unified_import", capture_mode="pdf", status="confirmed", records_created=3))
    db_session.commit()
    res = client.get("/api/v1/import/logs")
    assert res.status_code == 200
    assert res.json()[0]["records_created"] == 3 and res.json()[0]["source"] == "unified_import"



def test_vehicle_bought_this_year_keeps_todays_value_point(db_session):
    from datetime import date
    from decimal import Decimal

    from app.models.asset import Vehicle
    from app.models.asset_value_history import AssetValueHistory
    from app.services.valuation import store_vehicle_valuation

    v = Vehicle(year=1991, make="Honda", model="Acty", purchase_price=Decimal("6200"), purchase_date=date(2026, 6, 2))
    db_session.add(v)
    db_session.flush()
    store_vehicle_valuation(db_session, v, value=6500, annual_depreciation_pct=2, reasoning="comps", source="research",
                            model="claude-opus-5-5", confidence="medium", today=date(2026, 10, 30))
    rows = [(r.date, int(r.value), r.is_projected) for r in
            db_session.query(AssetValueHistory).filter_by(vehicle_id=v.id).order_by(AssetValueHistory.date)]
    assert rows[:3] == [(date(2026, 6, 2), 6200, False), (date(2026, 10, 30), 6500, False), (date(2027, 1, 1), 6370, True)]
    assert v.valuation_source == "research" and float(v.estimated_value) == 6500
