"""Provider normalization, credential encryption and the generic sync loop (mocked provider)."""
import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.services import crypto
from app.services.providers.base import ProviderAccount, ProviderSnapshot, ProviderTransaction, type_and_group_for
from app.services.providers.simplefin import classify_kind, normalize


SAMPLE = {
    "errors": ["Connection to Example Bank may need attention"],
    "accounts": [
        {
            "org": {"name": "Example Bank"},
            "id": "ACT-1",
            "name": "Everyday Checking",
            "balance": "1234.56",
            "balance-date": 1761696000,
            "transactions": [
                {"id": "T1", "posted": 1761609600, "amount": "-45.10", "payee": "Whole Foods", "pending": 0},
                {"id": "T1", "posted": 1761609600, "amount": "-45.10", "payee": "Whole Foods"},
                {"id": "T2", "posted": 1761523200, "amount": "2500.00", "description": "PAYROLL"},
                {"id": "", "posted": 1761523200, "amount": "1"},
                {"id": "T3", "posted": None, "amount": "9"},
            ],
        },
        {"org": {"name": "Example Bank"}, "id": "ACT-2", "name": "Platinum Visa Card", "balance": "-300", "transactions": []},
        {"id": "ACT-3", "name": "Brokerage", "balance": "9000", "holdings": [{"symbol": "VTI"}]},
    ],
}


def test_normalize_simplefin_payload():
    snap = normalize(SAMPLE)
    assert snap.warnings == ["Connection to Example Bank may need attention"]
    assert [a.id for a in snap.accounts] == ["ACT-1", "ACT-2", "ACT-3"]
    checking = snap.accounts[0]
    assert checking.kind == "checking"
    assert checking.institution == "Example Bank"
    assert checking.balance == Decimal("1234.56")
    assert checking.balance_date == date(2025, 10, 29)
    assert [t.id for t in checking.transactions] == ["T1", "T2"]  # duplicate and invalid rows dropped
    assert checking.transactions[0].merchant == "Whole Foods"
    assert checking.transactions[1].merchant == "PAYROLL"
    assert snap.accounts[1].kind == "credit_card"
    assert snap.accounts[2].kind == "investment"


@pytest.mark.parametrize("name,holdings,kind", [
    ("Everyday Checking", False, "checking"),
    ("High Yield Savings", False, "savings"),
    ("Platinum Visa", False, "credit_card"),
    ("Home Mortgage", False, "mortgage"),
    ("Student Loan", False, "loan"),
    ("Company 401(k)", False, "retirement"),
    ("Anything", True, "investment"),
])
def test_classify_kind(name, holdings, kind):
    assert classify_kind(name, holdings) == kind


def test_type_and_group_prefers_stored_type():
    assert type_and_group_for("checking") == ("cash", "Cash")
    assert type_and_group_for("checking", "credit_card") == ("credit_card", "Credit Cards")
    assert type_and_group_for("mortgage") == ("loan_mortgage", "Home Equity")


def test_credential_round_trip_and_passthrough():
    crypto.reset_key_cache()
    stored = crypto.encrypt_secret("https://user:pass@bridge.simplefin.org/simplefin")
    assert stored.startswith("enc:") and "pass" not in stored
    assert crypto.decrypt_secret(stored) == "https://user:pass@bridge.simplefin.org/simplefin"
    assert crypto.decrypt_secret("https://legacy") == "https://legacy"  # pre-encryption rows


def test_generic_sync_upserts_accounts_balances_and_transactions(db_session):
    """sync_tenant drives a mocked provider through the real upsert path on SQLite."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from app.models.account import Account
    from app.models.balance import BalanceSnapshot
    from app.models.transaction import Transaction
    from app.services import sync_scheduler
    from app.services.providers.base import AccountSyncConfig, ProviderConnection

    cfg_row = SimpleNamespace(local_account_id=None)
    link_row = SimpleNamespace(last_synced_at=None)
    connection = ProviderConnection(
        credential="secret",
        configs={"ACT-1": AccountSyncConfig(
            external_id="ACT-1", account_name="Everyday Checking", institution="Example Bank",
            account_type=None, sync_balances=True, sync_transactions=True, local_account_id=None, row=cfg_row,
        )},
        row=link_row,
    )
    snapshot = ProviderSnapshot(accounts=[
        ProviderAccount(id="ACT-1", name="Everyday Checking", institution="Example Bank", kind="checking",
                        balance=Decimal("1234.56"), balance_date=date(2026, 10, 29), transactions=[
                            ProviderTransaction(id="T1", date=date(2026, 10, 28), amount=Decimal("-45.10"), merchant="Whole Foods"),
                            ProviderTransaction(id="T2", date=date(2026, 10, 27), amount=Decimal("2500"), merchant="PAYROLL"),
                        ]),
        ProviderAccount(id="ACT-9", name="Unconfigured", kind="checking", balance=Decimal("1")),
    ])

    class FakeProvider:
        name = "fake"
        display_name = "Fake"

        def get_connection(self, db):
            return connection

        async def fetch(self, credential):
            assert credential == "secret"
            return snapshot

    @contextmanager
    def fake_tenant_session(schema):
        yield db_session

    from app.models.category_rule import CategoryRule
    db_session.add(CategoryRule(pattern="whole foods", match="contains", category="Groceries",
                                category_group="Food & Dining", source="research"))
    db_session.commit()

    with patch.object(sync_scheduler, "get_provider", lambda name: FakeProvider()), \
         patch.object(sync_scheduler, "tenant_session", fake_tenant_session):
        result = asyncio.run(sync_scheduler.sync_tenant("tenant_test0001", "fake"))
        assert result == {"schema": "tenant_test0001", "balances_synced": 1, "txn_added": 2, "txn_updated": 0}
        # second run updates instead of duplicating
        snapshot.accounts[0].transactions[0].amount = Decimal("-50")
        result2 = asyncio.run(sync_scheduler.sync_tenant("tenant_test0001", "fake"))
        assert result2["txn_added"] == 0 and result2["txn_updated"] == 2

    acct = db_session.get(Account, "fake-ACT-1")
    assert acct is not None and acct.account_type == "cash" and acct.display_group == "Cash"
    assert cfg_row.local_account_id == "fake-ACT-1"
    assert db_session.get(Account, "fake-ACT-9") is None
    assert db_session.query(BalanceSnapshot).filter_by(account_id="fake-ACT-1").count() == 1
    txns = {t.id: t for t in db_session.query(Transaction).filter(Transaction.account_id == "fake-ACT-1").all()}
    assert txns["fake-T1"].amount == Decimal("-50") and txns["fake-T1"].source == "fake"
    # New synced transactions are categorized by rule on arrival; unmatched ones stay uncategorized.
    assert (txns["fake-T1"].category, txns["fake-T1"].category_source) == ("Groceries", "rule:research")
    assert txns["fake-T2"].category is None
    assert link_row.last_synced_at is not None


def test_sync_all_tenants_creates_one_job_per_connected_provider():
    from app.services import sync_scheduler

    calls = []

    async def fake_run(schema, job_id, provider):
        calls.append((schema, job_id, provider))

    with patch.object(sync_scheduler, "_get_tenant_schemas", lambda: ["tenant_a", "tenant_b"]), \
         patch.object(sync_scheduler, "_tenant_has_provider_connection", lambda s, p: s == "tenant_a"), \
         patch.object(sync_scheduler, "create_job_row", lambda s, provider, trigger: (42, True)), \
         patch.object(sync_scheduler, "run_sync_with_job", fake_run):
        results = asyncio.run(sync_scheduler.sync_all_tenants())
    assert results == [{"schema": "tenant_a", "provider": "simplefin", "job_id": 42}]
    assert calls == [("tenant_a", 42, "simplefin")]


def test_removed_providers_are_gone(client):
    assert client.get("/api/v1/monarch/status").status_code == 404
    assert client.get("/api/v1/plaid/links").status_code == 404
    assert client.post("/api/v1/rsu/reload").status_code == 404
    assert client.post("/api/v1/retirement/upload-statement").status_code == 404
    assert client.post("/api/v1/ingest/confirm").status_code == 404
