#!/usr/bin/env python3
"""Validate docs/requirements/ledger.yaml.

Run from anywhere: `python scripts/ledger_check.py [path/to/ledger.yaml]`.
Exit code 1 on any problem. Passes (with a note) when the ledger file is absent,
so the gate can be wired into CI before the first entry exists.

Schema (see docs/ARCHITECTURE.md, "Requirements ledger"):

  requirements:
    - id: LOOK-001                 # UPPER-CASE segments joined by dashes
      title: Net worth at a glance
      job: look                    # look | feed | understand | plan | platform
      area: dashboard              # free text, one page or subsystem
      priority: p0                 # p0 | p1 | p2
      visible: true                # optional; a done visible entry needs a screenshot
      done_means:
        - "Observable acceptance criterion naming the fixture that proves it."
      status: todo                 # todo | in_progress | done | deprecated
      evidence:                    # strings; see EVIDENCE FORMS below
        - backend/tests/test_spending.py::test_by_category_respects_date_range
        - frontend/tests/tour.spec.ts#dashboard renders every tile
        - artifacts/screens/dashboard/desktop.png
      notes:
        - "2026-10-29: why this exists / what changed"

EVIDENCE FORMS
  backend/tests/<file>.py::<test_name>     file exists and contains "def <test_name>"
  <file>.spec.ts#<title> or .test.ts#<title> file exists and contains the title text
  artifacts/screens/<flow>/<name>.png      file exists
  any other path                           file exists (relative to the repo root)

RULES
  done        needs at least one test as evidence, and every evidence entry must resolve.
              If visible: true, it also needs at least one screenshot.
  deprecated  needs at least one note and at least one evidence entry (proof it is off:
              a test asserting the route is gone, or a commit path).
  ids are unique.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not a ledger problem
    print("ledger: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

JOBS = {"look", "feed", "understand", "plan", "platform"}
PRIORITIES = {"p0", "p1", "p2"}
STATUSES = {"todo", "in_progress", "done", "deprecated"}
ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
PY_TEST_RE = re.compile(r"\.py$")
TS_TEST_RE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
SCREENSHOT_RE = re.compile(r"\.(png|jpg|jpeg|webp)$", re.IGNORECASE)


@dataclass
class Report:
    found: bool = False
    total: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(STATUSES, 0))
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _split_reference(reference: str) -> tuple[str, str | None]:
    for sep in ("::", "#", " > "):
        idx = reference.find(sep)
        if idx > 0:
            return reference[:idx].strip(), reference[idx + len(sep):].strip()
    return reference.strip(), None


def check_evidence(reference: str, repo_root: Path) -> tuple[str | None, str]:
    """Return (problem or None, kind) where kind is 'test', 'screenshot' or 'path'."""
    file_part, title = _split_reference(reference)
    is_test = bool(title) and (PY_TEST_RE.search(file_part) or TS_TEST_RE.search(file_part))
    kind = "test" if is_test else ("screenshot" if SCREENSHOT_RE.search(file_part) else "path")

    absolute = (repo_root / file_part).resolve()
    try:
        absolute.relative_to(repo_root.resolve())
    except ValueError:
        return f"evidence points outside the repository: {reference}", kind
    if not absolute.exists():
        return f"evidence does not exist: {file_part}", kind
    if is_test:
        text = absolute.read_text(encoding="utf-8", errors="replace")
        needle = f"def {title}" if PY_TEST_RE.search(file_part) else title
        if needle not in text:
            return f'test "{title}" not found in {file_part}', kind
    return None, kind


def validate_entry(raw: object, index: int, repo_root: Path, seen: set[str], report: Report) -> None:
    label = raw.get("id") if isinstance(raw, dict) and isinstance(raw.get("id"), str) else f"entry {index + 1}"
    if not isinstance(raw, dict):
        report.problems.append(f"{label}: entry must be a mapping")
        return

    problems: list[str] = []
    rid = raw.get("id")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        problems.append("id: ids look like LOOK-001 or NFR-SEC-003")
    if not isinstance(raw.get("title"), str) or not raw["title"].strip():
        problems.append("title: required")
    if raw.get("job") not in JOBS:
        problems.append(f"job: must be one of {sorted(JOBS)}")
    if not isinstance(raw.get("area"), str) or not raw["area"].strip():
        problems.append("area: required")
    if raw.get("priority") not in PRIORITIES:
        problems.append(f"priority: must be one of {sorted(PRIORITIES)}")
    done_means = raw.get("done_means")
    if not isinstance(done_means, list) or not done_means or not all(isinstance(d, str) and d.strip() for d in done_means):
        problems.append("done_means: at least one non-empty criterion")
    status = raw.get("status")
    if status not in STATUSES:
        problems.append(f"status: must be one of {sorted(STATUSES)}")
    evidence = raw.get("evidence", []) or []
    if not isinstance(evidence, list) or not all(isinstance(e, str) and e.strip() for e in evidence):
        problems.append("evidence: a list of strings")
        evidence = []
    notes = raw.get("notes", []) or []
    if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes):
        problems.append("notes: a list of strings")
        notes = []
    if "visible" in raw and not isinstance(raw["visible"], bool):
        problems.append("visible: true or false")

    for p in problems:
        report.problems.append(f"{label}: {p}")
    if problems:
        return

    report.total += 1
    report.counts[status] += 1
    if rid in seen:
        report.problems.append(f"{rid}: duplicate id")
    seen.add(rid)

    if status == "done":
        if not evidence:
            report.problems.append(f"{rid}: status is done but there is no evidence")
            return
        kinds = {"test": 0, "screenshot": 0, "path": 0}
        for ref in evidence:
            problem, kind = check_evidence(ref, repo_root)
            if problem:
                report.problems.append(f"{rid}: {problem}")
            kinds[kind] += 1
        if kinds["test"] == 0:
            report.problems.append(f"{rid}: done needs at least one automated test as evidence")
        if raw.get("visible") and kinds["screenshot"] == 0:
            report.problems.append(f"{rid}: visible and done needs at least one screenshot as evidence")
    elif status == "deprecated":
        if not notes:
            report.problems.append(f"{rid}: deprecated needs a dated note saying why")
        if not evidence:
            report.problems.append(f"{rid}: deprecated needs evidence that it is off")
        for ref in evidence:
            problem, _ = check_evidence(ref, repo_root)
            if problem:
                report.problems.append(f"{rid}: {problem}")


def validate_ledger(ledger_file: Path, repo_root: Path) -> Report:
    report = Report()
    if not ledger_file.exists():
        return report
    report.found = True
    try:
        raw = yaml.safe_load(ledger_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised by a malformed file
        report.problems.append(f"not valid YAML: {str(exc).splitlines()[0]}")
        return report
    if isinstance(raw, list):
        raw = {"requirements": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("requirements"), list):
        report.problems.append('the file must contain a "requirements" list')
        return report
    seen: set[str] = set()
    for i, entry in enumerate(raw["requirements"]):
        validate_entry(entry, i, repo_root, seen, report)
    return report


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    ledger_file = Path(argv[1]).resolve() if len(argv) > 1 else repo_root / "docs" / "requirements" / "ledger.yaml"
    report = validate_ledger(ledger_file, repo_root)
    if not report.found:
        print(f"ledger: {ledger_file.relative_to(repo_root) if ledger_file.is_relative_to(repo_root) else ledger_file} not found, nothing to check")
        return 0
    c = report.counts
    print(
        f"ledger: {report.total} requirements ({c['done']} done, {c['in_progress']} in progress, "
        f"{c['todo']} todo, {c['deprecated']} deprecated)"
    )
    for problem in report.problems:
        print(f"  x {problem}", file=sys.stderr)
    if report.problems:
        print(f"ledger: {len(report.problems)} problem(s)", file=sys.stderr)
        return 1
    print("ledger: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
