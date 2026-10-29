"""Tests for scripts/ledger_check.py, the requirements-ledger gate."""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ledger_check.py"

spec = importlib.util.spec_from_file_location("ledger_check", SCRIPT)
ledger_check = importlib.util.module_from_spec(spec)
sys.modules["ledger_check"] = ledger_check
spec.loader.exec_module(ledger_check)


def write_ledger(root: Path, body: str) -> Path:
    ledger = root / "docs" / "requirements" / "ledger.yaml"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(body, encoding="utf-8")
    return ledger


def entry(**overrides) -> str:
    fields = {
        "id": "LOOK-001",
        "title": "Net worth at a glance",
        "job": "look",
        "area": "dashboard",
        "priority": "p0",
        "status": "todo",
    }
    fields.update(overrides)
    lines = ["  - " + f"id: {fields['id']}"]
    for key in ("title", "job", "area", "priority", "status"):
        lines.append(f"    {key}: {fields[key]}")
    if "visible" in fields:
        lines.append(f"    visible: {'true' if fields['visible'] else 'false'}")
    lines.append("    done_means:")
    lines.append('      - "The dashboard shows a net worth tile for Claudius."')
    if fields.get("evidence"):
        lines.append("    evidence:")
        lines.extend(f"      - '{e}'" for e in fields["evidence"])
    if fields.get("notes"):
        lines.append("    notes:")
        lines.extend(f"      - '{n}'" for n in fields["notes"])
    return "\n".join(lines) + "\n"


def test_missing_ledger_passes(tmp_path):
    report = ledger_check.validate_ledger(tmp_path / "nope.yaml", tmp_path)
    assert report.found is False
    assert report.ok


def test_todo_entry_needs_no_evidence(tmp_path):
    ledger = write_ledger(tmp_path, "requirements:\n" + entry())
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert report.ok, report.problems
    assert report.counts["todo"] == 1


def test_done_without_evidence_fails(tmp_path):
    ledger = write_ledger(tmp_path, "requirements:\n" + entry(status="done"))
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert any("no evidence" in p for p in report.problems)


def test_done_needs_a_test_not_just_a_screenshot(tmp_path):
    shot = tmp_path / "artifacts" / "screens" / "dashboard" / "desktop.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"png")
    ledger = write_ledger(
        tmp_path, "requirements:\n" + entry(status="done", evidence=["artifacts/screens/dashboard/desktop.png"])
    )
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert any("at least one automated test" in p for p in report.problems)


def test_python_test_evidence_checks_def_exists(tmp_path):
    test_file = tmp_path / "backend" / "tests" / "test_dashboard.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_net_worth_tile():\n    pass\n")
    good = entry(status="done", evidence=["backend/tests/test_dashboard.py::test_net_worth_tile"])
    bad = entry(id="LOOK-002", status="done", evidence=["backend/tests/test_dashboard.py::test_missing"])
    ledger = write_ledger(tmp_path, "requirements:\n" + good + bad)
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert report.problems == ['LOOK-002: test "test_missing" not found in backend/tests/test_dashboard.py']


def test_visible_done_needs_screenshot(tmp_path):
    test_file = tmp_path / "backend" / "tests" / "test_dashboard.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_net_worth_tile():\n    pass\n")
    ledger = write_ledger(
        tmp_path,
        "requirements:\n"
        + entry(status="done", visible=True, evidence=["backend/tests/test_dashboard.py::test_net_worth_tile"]),
    )
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert any("needs at least one screenshot" in p for p in report.problems)


def test_ts_spec_evidence_checks_title_text(tmp_path):
    spec_file = tmp_path / "frontend" / "tests" / "tour.spec.ts"
    spec_file.parent.mkdir(parents=True)
    spec_file.write_text("test('dashboard renders every tile', async () => {})\n")
    ledger = write_ledger(
        tmp_path,
        "requirements:\n" + entry(status="done", evidence=["frontend/tests/tour.spec.ts#dashboard renders every tile"]),
    )
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert report.ok, report.problems


def test_deprecated_needs_note_and_evidence(tmp_path):
    ledger = write_ledger(tmp_path, "requirements:\n" + entry(status="deprecated"))
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert any("dated note" in p for p in report.problems)
    assert any("evidence that it is off" in p for p in report.problems)


def test_duplicate_ids_and_bad_fields_reported(tmp_path):
    ledger = write_ledger(
        tmp_path,
        "requirements:\n" + entry() + entry() + entry(id="bad id", job="fly"),
    )
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert "LOOK-001: duplicate id" in report.problems
    assert any("ids look like" in p for p in report.problems)
    assert any("job: must be one of" in p for p in report.problems)


def test_evidence_outside_repo_rejected(tmp_path):
    ledger = write_ledger(tmp_path, "requirements:\n" + entry(status="done", evidence=["../etc/passwd"]))
    report = ledger_check.validate_ledger(ledger, tmp_path)
    assert any("outside the repository" in p for p in report.problems)


def test_real_ledger_if_present_is_valid():
    """The repository's own ledger must always pass the gate."""
    ledger = REPO_ROOT / "docs" / "requirements" / "ledger.yaml"
    if not ledger.exists():
        pytest.skip("no ledger yet")
    report = ledger_check.validate_ledger(ledger, REPO_ROOT)
    assert report.ok, "\n".join(report.problems)
