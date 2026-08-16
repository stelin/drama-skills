#!/usr/bin/env python3
"""Offline self-test for the standalone review checker."""

from __future__ import annotations

import copy
import sys

from review_check import SKILL_ROOT, ValidationError, load_jsonl, load_object, validate_records

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("selftest.py requires Python 3.10 or newer")


def fail(findings: list[dict], verdict: dict, marker: str) -> None:
    try:
        validate_records(findings, verdict)
    except ValidationError as exc:
        assert marker in str(exc), (marker, str(exc))
    else:
        raise AssertionError(f"expected failure containing {marker!r}")


def main() -> int:
    findings = load_jsonl(SKILL_ROOT / "examples/minimal-findings.jsonl")
    verdict = load_object(SKILL_ROOT / "examples/minimal-verdict.json")
    result = validate_records(findings, verdict)
    assert result["open_blockers"] == 1 and result["verdict"] == "REVISE"

    wrong_count = copy.deepcopy(verdict)
    wrong_count["open_blocker_count"] = 0
    fail(findings, wrong_count, "open_blocker_count")

    false_approval = copy.deepcopy(verdict)
    false_approval["verdict"] = "APPROVE"
    fail(findings, false_approval, "open blockers require REVISE")

    broken_finding = copy.deepcopy(findings)
    broken_finding[0]["evidence_refs"] = []
    fail(broken_finding, verdict, "evidence_refs")

    print("4 self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
