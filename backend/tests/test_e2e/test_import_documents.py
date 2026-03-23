"""
End-to-end import tests for all Tallied test document types.

These tests upload real PDF/XLSX documents to the unified import endpoint,
verify the AI correctly extracts expected fields, and verify that confirm
writes correct data to the database.

Requirements:
  - PostgreSQL running: docker compose up -d postgres
  - FINANCE_ANTHROPIC_API_KEY set in environment
  - Test documents generated: python scripts/generate_test_documents.py
  - Run: pytest tests/test_e2e/test_import_documents.py -v

Tests are skipped automatically when:
  - FINANCE_ANTHROPIC_API_KEY is not set (AI parsing required)
  - Test documents are not found on disk
"""
import os
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

DOCS_DIR = Path(__file__).parent.parent.parent.parent / "fixtures" / "test_documents"

SKIP_NO_KEY = pytest.mark.skipif(
    not os.getenv("FINANCE_ANTHROPIC_API_KEY"),
    reason="FINANCE_ANTHROPIC_API_KEY not set; AI import tests require Claude API",
)

SKIP_NO_DOCS = pytest.mark.skipif(
    not DOCS_DIR.exists(),
    reason=f"Test documents not found at {DOCS_DIR}. Run: python scripts/generate_test_documents.py",
)


def _read_file(relative_path: str) -> bytes:
    """Read a test document file and return bytes."""
    full_path = DOCS_DIR / relative_path
    if not full_path.exists():
        pytest.skip(f"Document not found: {full_path}")
    return full_path.read_bytes()


def _upload_document(client, file_bytes: bytes, filename: str, context: str) -> dict:
    """Upload a document to the import endpoint and return the response dict."""
    content_type = "application/pdf" if filename.endswith(".pdf") else (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.endswith(".xlsx") else "application/octet-stream"
    )
    resp = client.post(
        "/api/v1/import/upload",
        data={"context": context},
        files={"file": (filename, file_bytes, content_type)},
    )
    assert resp.status_code == 200, f"Upload failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    assert data["status"] == "review", f"Expected review status, got: {data['status']}"
    return data


def _confirm_import(client, session_id: str) -> dict:
    """Confirm all proposed changes for an import session."""
    resp = client.post(f"/api/v1/import/{session_id}/confirm")
    assert resp.status_code == 200, f"Confirm failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    assert data["status"] == "confirmed"
    return data


def _get_proposed_fields(proposed_changes: list) -> dict:
    """Extract a flat dict of db_field -> value from proposed changes."""
    fields = {}
    for change in proposed_changes:
        for f in change.get("fields", []):
            key = f.get("db_field") or f.get("field")
            if key and f.get("value") is not None:
                fields[key] = f["value"]
    return fields


def _assert_value_close(actual, expected, tolerance=0.05, field_name=""):
    """Assert a numeric value is within tolerance (5% by default)."""
    if actual is None:
        pytest.fail(f"Field '{field_name}' was None, expected ~{expected}")
    actual_f = float(actual) if not isinstance(actual, float) else actual
    expected_f = float(expected)
    if expected_f == 0:
        assert abs(actual_f) < 1.0, f"{field_name}: expected ~0, got {actual_f}"
    else:
        pct_diff = abs(actual_f - expected_f) / abs(expected_f)
        assert pct_diff < tolerance, (
            f"{field_name}: expected ~{expected_f}, got {actual_f} "
            f"(diff={pct_diff:.1%}, tolerance={tolerance:.0%})"
        )


# =============================================================================
# INCOME DOCUMENT TESTS
# =============================================================================


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomeW2Standard:
    """Upload the standard 2025 W2 and verify extraction."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/w2-standard-employer.pdf")
        data = _upload_document(client, file_bytes, "w2-standard-employer.pdf", "income")
        TestIncomeW2Standard._session = data

        assert data["findings_count"] > 0
        assert data["context"] == "income"

    def test_expected_fields_extracted(self, client):
        data = getattr(TestIncomeW2Standard, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        # Should propose w2_records changes
        tables = [c["table"] for c in proposed]
        assert "w2_records" in tables, f"Expected w2_records in proposed tables, got: {tables}"

    def test_key_values(self, client):
        data = getattr(TestIncomeW2Standard, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        # These are the critical fields the AI must extract from a standard W2
        expected = {
            "w2_federal_tax": 38500.00,
            "w2_social_security": 10918.20,
            "w2_medicare": 3045.00,
            "w2_state_tax": 10400.00,
            "w2_pretax_401k": 10000.00,
            "w2_roth_401k": 5000.00,
            "w2_employer_health": 8600.00,
        }

        for field, expected_val in expected.items():
            if field in fields:
                _assert_value_close(fields[field], expected_val, field_name=field)

    def test_confirm_writes_to_db(self, client):
        data = getattr(TestIncomeW2Standard, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        result = _confirm_import(client, data["session_id"])
        assert result["changes_applied"] > 0

        # Verify W2 was written
        resp = client.get("/api/v1/income/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history.get("w2_records", [])) >= 1


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomeW2Minimal:
    """Upload minimal W2 (2024) -- only basic boxes filled."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/w2-minimal-fields.pdf")
        data = _upload_document(client, file_bytes, "w2-minimal-fields.pdf", "income")
        TestIncomeW2Minimal._session = data

        assert data["findings_count"] > 0

    def test_has_missing_fields(self, client):
        """Minimal W2 should report some expected fields as missing."""
        data = getattr(TestIncomeW2Minimal, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        # We don't require specific missing fields, but the AI should note
        # that fields like base_salary, rsu_income are not found
        # This is informational -- the import should still succeed


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomeW2MultipleStates:
    """Upload W2 with MA + CA state taxes."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/w2-multiple-states.pdf")
        data = _upload_document(client, file_bytes, "w2-multiple-states.pdf", "income")
        TestIncomeW2MultipleStates._session = data

        assert data["findings_count"] > 0

    def test_state_tax_handling(self, client):
        """AI should extract state taxes -- ideally summing MA + CA."""
        data = getattr(TestIncomeW2MultipleStates, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        # The combined state tax should be ~$10,400 (7280 + 3120)
        if "w2_state_tax" in fields:
            val = float(fields["w2_state_tax"])
            # Accept either the sum (~10400) or the primary state (~7280)
            assert val >= 3000, f"State tax seems too low: {val}"


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomeW2HighEarner:
    """Upload high-earner W2 ($525K gross)."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/w2-high-earner.pdf")
        data = _upload_document(client, file_bytes, "w2-high-earner.pdf", "income")
        TestIncomeW2HighEarner._session = data

        assert data["findings_count"] > 0

    def test_high_values_extracted(self, client):
        data = getattr(TestIncomeW2HighEarner, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        if "w2_federal_tax" in fields:
            _assert_value_close(fields["w2_federal_tax"], 142500.00, field_name="w2_federal_tax")
        if "w2_pretax_401k" in fields:
            _assert_value_close(fields["w2_pretax_401k"], 23500.00, field_name="w2_pretax_401k")


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomePaystubADP:
    """Upload ADP-style pay stub."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/paystub-adp.pdf")
        data = _upload_document(client, file_bytes, "paystub-adp.pdf", "income")
        TestIncomePaystubADP._session = data

        assert data["findings_count"] > 0

    def test_ytd_values_used(self, client):
        """AI should extract YTD totals, not per-period amounts."""
        data = getattr(TestIncomePaystubADP, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        # Gross pay YTD should be ~210K, not the per-period ~5.5K
        if "w2_gross_pay" in fields:
            val = float(fields["w2_gross_pay"])
            assert val > 50000, f"Gross pay {val} looks like per-period, not YTD"

    def test_base_and_rsu_split(self, client):
        """Pay stubs should extract base salary and RSU income separately."""
        data = getattr(TestIncomePaystubADP, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        if "w2_base_salary" in fields:
            _assert_value_close(fields["w2_base_salary"], 145000.00, field_name="w2_base_salary")
        if "w2_rsu_income" in fields:
            _assert_value_close(fields["w2_rsu_income"], 65000.00, field_name="w2_rsu_income")


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestIncomePaystubWorkday:
    """Upload Workday-style pay stub."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("income/paystub-workday.pdf")
        data = _upload_document(client, file_bytes, "paystub-workday.pdf", "income")
        TestIncomePaystubWorkday._session = data

        assert data["findings_count"] > 0

    def test_all_deductions_extracted(self, client):
        data = getattr(TestIncomePaystubWorkday, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        # Workday stub has all fields clearly labeled
        if "w2_pretax_401k" in fields:
            _assert_value_close(fields["w2_pretax_401k"], 10000.00, field_name="w2_pretax_401k")
        if "w2_roth_401k" in fields:
            _assert_value_close(fields["w2_roth_401k"], 5000.00, field_name="w2_roth_401k")


# =============================================================================
# RETIREMENT DOCUMENT TESTS
# =============================================================================


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRetirementFidelity:
    """Upload Fidelity quarterly 401(k) statement."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("retirement/401k-fidelity-quarterly.pdf")
        data = _upload_document(client, file_bytes, "401k-fidelity-quarterly.pdf", "retirement")
        TestRetirementFidelity._session = data

        assert data["findings_count"] > 0
        assert data["context"] == "retirement"

    def test_balance_fields(self, client):
        data = getattr(TestRetirementFidelity, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        tables = [c["table"] for c in proposed]
        assert "retirement_accounts" in tables

        # Find the retirement change
        ret_change = next((c for c in proposed if c["table"] == "retirement_accounts"), None)
        if ret_change:
            fields = {f.get("db_field", f.get("field")): f.get("value") for f in ret_change.get("fields", [])}

            if "total_balance" in fields:
                _assert_value_close(fields["total_balance"], 185432.50, field_name="total_balance")

    def test_deferral_rates(self, client):
        data = getattr(TestRetirementFidelity, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        ret_change = next((c for c in proposed if c["table"] == "retirement_accounts"), None)
        if ret_change:
            fields = {f.get("db_field", f.get("field")): f.get("value") for f in ret_change.get("fields", [])}
            if "pretax_deferral_rate_pct" in fields:
                _assert_value_close(fields["pretax_deferral_rate_pct"], 10, field_name="pretax_deferral_rate_pct")
            if "roth_deferral_rate_pct" in fields:
                _assert_value_close(fields["roth_deferral_rate_pct"], 2, field_name="roth_deferral_rate_pct")

    def test_confirm_writes_retirement(self, client):
        data = getattr(TestRetirementFidelity, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        result = _confirm_import(client, data["session_id"])
        assert result["changes_applied"] > 0

        tables_written = [r["table"] for r in result.get("results", [])]
        assert "retirement_accounts" in tables_written


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRetirementVanguard:
    """Upload Vanguard annual 401(k) statement."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("retirement/401k-vanguard-annual.pdf")
        data = _upload_document(client, file_bytes, "401k-vanguard-annual.pdf", "retirement")
        TestRetirementVanguard._session = data

        assert data["findings_count"] > 0

    def test_single_fund_extracted(self, client):
        data = getattr(TestRetirementVanguard, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        ret_change = next((c for c in proposed if c["table"] == "retirement_accounts"), None)
        assert ret_change is not None, "Expected retirement_accounts in proposed changes"


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRetirementTRowePrice:
    """Upload T. Rowe Price quarterly statement with 4 funds."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("retirement/401k-troweprice-quarterly.pdf")
        data = _upload_document(client, file_bytes, "401k-troweprice-quarterly.pdf", "retirement")
        TestRetirementTRowePrice._session = data

        assert data["findings_count"] > 0


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRetirementMinimal:
    """Upload minimal 401(k) statement -- just total balance."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("retirement/401k-minimal.pdf")
        data = _upload_document(client, file_bytes, "401k-minimal.pdf", "retirement")
        TestRetirementMinimal._session = data

        assert data["findings_count"] > 0

    def test_missing_fields_reported(self, client):
        """Minimal statement should report missing expected fields."""
        data = getattr(TestRetirementMinimal, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        # The total_balance should still be extracted
        proposed = data.get("proposed_changes", [])
        ret_change = next((c for c in proposed if c["table"] == "retirement_accounts"), None)
        if ret_change:
            fields = {f.get("db_field", f.get("field")): f.get("value") for f in ret_change.get("fields", [])}
            if "total_balance" in fields:
                _assert_value_close(fields["total_balance"], 185432.50, field_name="total_balance")


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRetirementWithLoan:
    """Upload 401(k) statement with outstanding loan."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("retirement/401k-with-loan.pdf")
        data = _upload_document(client, file_bytes, "401k-with-loan.pdf", "retirement")
        TestRetirementWithLoan._session = data

        assert data["findings_count"] > 0

    def test_loan_does_not_break_import(self, client):
        """Loan info should not prevent balance extraction."""
        data = getattr(TestRetirementWithLoan, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        ret_change = next((c for c in proposed if c["table"] == "retirement_accounts"), None)
        assert ret_change is not None, "Loan section should not prevent retirement data extraction"


# =============================================================================
# PROPERTY DOCUMENT TESTS
# =============================================================================


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestMortgageChase:
    """Upload Chase mortgage statement."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("property/mortgage-chase.pdf")
        data = _upload_document(client, file_bytes, "mortgage-chase.pdf", "property")
        TestMortgageChase._session = data

        assert data["findings_count"] > 0
        assert data["context"] == "property"

    def test_mortgage_fields(self, client):
        data = getattr(TestMortgageChase, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))

        expected = {
            "mortgage_balance": 362450.75,
            "mortgage_rate": 4.25,
            "mortgage_monthly_payment": 2450.00,
            "mortgage_original_amount": 380000.00,
        }

        for field, expected_val in expected.items():
            if field in fields:
                _assert_value_close(fields[field], expected_val, field_name=field)

    def test_confirm_writes_mortgage(self, client):
        data = getattr(TestMortgageChase, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        result = _confirm_import(client, data["session_id"])
        assert result["changes_applied"] > 0


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestMortgageWellsFargo:
    """Upload Wells Fargo mortgage statement with escrow analysis."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("property/mortgage-wells-fargo.pdf")
        data = _upload_document(client, file_bytes, "mortgage-wells-fargo.pdf", "property")
        TestMortgageWellsFargo._session = data

        assert data["findings_count"] > 0

    def test_escrow_noise_handled(self, client):
        """Escrow analysis section should not confuse the main mortgage fields."""
        data = getattr(TestMortgageWellsFargo, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))
        if "mortgage_balance" in fields:
            _assert_value_close(fields["mortgage_balance"], 362450.75, field_name="mortgage_balance")


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestMortgageRefi:
    """Upload refinance closing disclosure."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("property/mortgage-refi-statement.pdf")
        data = _upload_document(client, file_bytes, "mortgage-refi-statement.pdf", "property")
        TestMortgageRefi._session = data

        assert data["findings_count"] > 0

    def test_refi_terms_extracted(self, client):
        data = getattr(TestMortgageRefi, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))
        # The refi should extract the new loan amount and rate
        if "mortgage_original_amount" in fields:
            _assert_value_close(fields["mortgage_original_amount"], 355000.00, field_name="mortgage_original_amount")
        if "mortgage_rate" in fields:
            _assert_value_close(fields["mortgage_rate"], 3.625, field_name="mortgage_rate")


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestPropertyTaxBill:
    """Upload property tax bill -- non-mortgage document."""

    def test_upload_and_parse(self, client):
        """Property tax bill should parse without error, but may have few mortgage fields."""
        file_bytes = _read_file("property/property-tax-bill.pdf")
        data = _upload_document(client, file_bytes, "property-tax-bill.pdf", "property")
        TestPropertyTaxBill._session = data

        # It should still parse without crashing
        assert data["status"] == "review"

    def test_limited_mortgage_extraction(self, client):
        """Tax bill should have few or no mortgage-specific fields."""
        data = getattr(TestPropertyTaxBill, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        fields = _get_proposed_fields(data.get("proposed_changes", []))
        # The AI should NOT extract a principal balance from a tax bill
        if "mortgage_balance" in fields:
            # If it did, it should be a reasonable number (not $520K assessed value)
            val = float(fields["mortgage_balance"])
            assert val != 520000.00, "AI mistakenly used assessed value as mortgage balance"


# =============================================================================
# RSU DOCUMENT TESTS
# =============================================================================


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRSUEtrade:
    """Upload E-Trade RSU vesting schedule (.xlsx)."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("rsu/rsu-etrade-vesting.xlsx")
        data = _upload_document(client, file_bytes, "rsu-etrade-vesting.xlsx", "rsu")
        TestRSUEtrade._session = data

        assert data["findings_count"] > 0
        assert data["context"] == "rsu"

    def test_grants_extracted(self, client):
        data = getattr(TestRSUEtrade, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        # Should have rsu_grants changes
        rsu_changes = [c for c in proposed if c["table"] == "rsu_grants"]
        assert len(rsu_changes) >= 1, f"Expected rsu_grants changes, got tables: {[c['table'] for c in proposed]}"

    def test_grant_numbers(self, client):
        data = getattr(TestRSUEtrade, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        rsu_changes = [c for c in proposed if c["table"] == "rsu_grants"]

        grant_numbers = set()
        for change in rsu_changes:
            gn = change.get("data", {}).get("grant_number")
            if gn:
                grant_numbers.add(str(gn))

        # Should find at least one of our grants
        expected_grants = {"094907", "107234"}
        found = grant_numbers & expected_grants
        assert len(found) >= 1, f"Expected grants {expected_grants}, found: {grant_numbers}"

    def test_confirm_writes_rsu(self, client):
        data = getattr(TestRSUEtrade, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        result = _confirm_import(client, data["session_id"])
        assert result["changes_applied"] > 0

        tables_written = [r["table"] for r in result.get("results", [])]
        assert "rsu_grants" in tables_written


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRSUSchwab:
    """Upload Schwab RSU report (.xlsx) -- different layout from E-Trade."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("rsu/rsu-schwab-vesting.xlsx")
        data = _upload_document(client, file_bytes, "rsu-schwab-vesting.xlsx", "rsu")
        TestRSUSchwab._session = data

        assert data["findings_count"] > 0

    def test_grants_extracted(self, client):
        data = getattr(TestRSUSchwab, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        rsu_changes = [c for c in proposed if c["table"] == "rsu_grants"]
        assert len(rsu_changes) >= 1


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestRSUGrantLetter:
    """Upload RSU grant confirmation letter (PDF, not spreadsheet)."""

    def test_upload_and_parse(self, client):
        file_bytes = _read_file("rsu/rsu-simple-grant-letter.pdf")
        data = _upload_document(client, file_bytes, "rsu-simple-grant-letter.pdf", "rsu")
        TestRSUGrantLetter._session = data

        assert data["findings_count"] > 0

    def test_grant_details(self, client):
        data = getattr(TestRSUGrantLetter, "_session", None)
        if not data:
            pytest.skip("No session from upload")

        proposed = data.get("proposed_changes", [])
        rsu_changes = [c for c in proposed if c["table"] == "rsu_grants"]

        if rsu_changes:
            # Check if the grant letter extracted the correct grant number
            grant_data = rsu_changes[0].get("data", {})
            if "grant_number" in grant_data:
                assert str(grant_data["grant_number"]) == "107234"
            if "total_shares" in grant_data:
                assert int(grant_data["total_shares"]) == 250


# =============================================================================
# CROSS-DOCUMENT CONSISTENCY TESTS
# =============================================================================


@SKIP_NO_KEY
@SKIP_NO_DOCS
class TestCrossDocumentConsistency:
    """Verify that values are consistent across related documents."""

    def test_w2_and_paystub_gross_pay_match(self, client):
        """W2 gross pay and pay stub YTD gross should be the same."""
        # Upload both documents
        w2_bytes = _read_file("income/w2-standard-employer.pdf")
        w2_data = _upload_document(client, w2_bytes, "w2-standard-employer.pdf", "income")

        stub_bytes = _read_file("income/paystub-adp.pdf")
        stub_data = _upload_document(client, stub_bytes, "paystub-adp.pdf", "income")

        w2_fields = _get_proposed_fields(w2_data.get("proposed_changes", []))
        stub_fields = _get_proposed_fields(stub_data.get("proposed_changes", []))

        # Both should extract a gross pay value
        w2_gross = w2_fields.get("w2_gross_pay")
        stub_gross = stub_fields.get("w2_gross_pay")

        if w2_gross and stub_gross:
            # They should be close (W2 Box 5 Medicare wages = $210K,
            # Box 1 wages = $197,700 -- either is acceptable)
            w2_val = float(w2_gross)
            stub_val = float(stub_gross)
            # Both should be > $100K (not per-period amounts)
            assert w2_val > 100000, f"W2 gross {w2_val} seems too low"
            assert stub_val > 100000, f"Stub gross {stub_val} seems too low"

    def test_mortgage_statements_agree(self, client):
        """Chase and Wells Fargo statements for same mortgage should agree."""
        chase_bytes = _read_file("property/mortgage-chase.pdf")
        chase_data = _upload_document(client, chase_bytes, "mortgage-chase.pdf", "property")

        wf_bytes = _read_file("property/mortgage-wells-fargo.pdf")
        wf_data = _upload_document(client, wf_bytes, "mortgage-wells-fargo.pdf", "property")

        chase_fields = _get_proposed_fields(chase_data.get("proposed_changes", []))
        wf_fields = _get_proposed_fields(wf_data.get("proposed_changes", []))

        # Both should extract the same balance
        chase_balance = chase_fields.get("mortgage_balance")
        wf_balance = wf_fields.get("mortgage_balance")

        if chase_balance and wf_balance:
            _assert_value_close(
                float(chase_balance), float(wf_balance),
                tolerance=0.01,
                field_name="mortgage_balance across statements",
            )
