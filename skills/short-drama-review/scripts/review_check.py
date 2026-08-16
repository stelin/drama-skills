#!/usr/bin/env python3
"""Validate standalone review findings and their verdict summary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("review_check.py requires Python 3.10 or newer")

SKILL_ROOT = Path(__file__).resolve().parents[1]
HASH_RE = re.compile(r"[0-9a-f]{64}")
SEVERITIES = {"fatal", "error", "warning", "note"}
STATUSES = {"open", "closed"}
VERDICTS = {"APPROVE", "APPROVE_WITH_NOTES", "REVISE", "PROVISIONAL"}
DISPOSITIONS = {"keep", "post_production", "targeted_edit", "resubmit", "rewrite", "not_applicable"}


class ValidationError(ValueError):
    pass


def resolve_input(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.exists() or path.is_absolute():
        return path
    return SKILL_ROOT / path


def load_jsonl(value: str | Path) -> list[dict[str, Any]]:
    path = resolve_input(value)
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path}:{number}: invalid JSON") from exc
        if not isinstance(record, dict):
            raise ValidationError(f"{path}:{number}: finding must be an object")
        records.append(record)
    return records


def load_object(value: str | Path) -> dict[str, Any]:
    path = resolve_input(value)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON") from exc
    if not isinstance(document, dict):
        raise ValidationError(f"{path}: verdict must be an object")
    return document


def text(record: dict[str, Any], key: str, label: str, *, empty_ok: bool = False) -> str:
    value = record.get(key)
    if not isinstance(value, str) or (not empty_ok and not value.strip()):
        qualifier = "text" if empty_ok else "non-empty text"
        raise ValidationError(f"{label}: {key} must be {qualifier}")
    return value


def validate_ref(value: Any, label: str, *, record_optional: bool = False) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{label}: reference must be an object")
    for key in ("owner", "artifact", "hash"):
        text(value, key, label)
    if HASH_RE.fullmatch(str(value["hash"])) is None:
        raise ValidationError(f"{label}: hash must be lowercase sha256")
    if not record_optional and not value.get("record_id") and not value.get("field"):
        raise ValidationError(f"{label}: record_id or field is required")


def validate_findings(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, finding in enumerate(findings, 1):
        label = f"finding[{index}]"
        finding_id = text(finding, "finding_id", label)
        if finding_id in indexed:
            raise ValidationError(f"{label}: duplicate finding_id {finding_id}")
        indexed[finding_id] = finding
        for key in (
            "diagnostic_code",
            "scope",
            "classification",
            "enforcer",
            "evidence",
            "impact",
            "disposition_rationale",
            "owner_skill",
        ):
            text(finding, key, label)
        text(finding, "required_change", label, empty_ok=True)
        if finding.get("severity") not in SEVERITIES:
            raise ValidationError(f"{label}: invalid severity")
        if finding.get("status") not in STATUSES:
            raise ValidationError(f"{label}: invalid status")
        disposition = finding.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ValidationError(f"{label}: invalid disposition")
        if disposition in {"targeted_edit", "resubmit", "rewrite"} and not finding["required_change"].strip():
            raise ValidationError(f"{label}: disposition requires required_change")
        refs = finding.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ValidationError(f"{label}: evidence_refs must be a non-empty list")
        for ref_index, ref in enumerate(refs, 1):
            validate_ref(ref, f"{label}.evidence_refs[{ref_index}]")
        validate_ref(finding.get("target_ref"), f"{label}.target_ref")
    return indexed


def validate_records(findings: list[dict[str, Any]], verdict: dict[str, Any]) -> dict[str, Any]:
    indexed = validate_findings(findings)
    text(verdict, "review_id", "verdict")
    scopes = verdict.get("scope")
    if not isinstance(scopes, list) or not scopes or any(not isinstance(item, str) or not item for item in scopes):
        raise ValidationError("verdict: scope must be a non-empty text list")
    artifacts = verdict.get("reviewed_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValidationError("verdict: reviewed_artifacts must be non-empty")
    for index, artifact in enumerate(artifacts, 1):
        validate_ref(artifact, f"verdict.reviewed_artifacts[{index}]", record_optional=True)
    validate_ref(verdict.get("findings_ref"), "verdict.findings_ref", record_optional=True)
    if verdict.get("review_method") not in {"uninvolved_reviewer", "self_check"}:
        raise ValidationError("verdict: review_method must be uninvolved_reviewer or self_check")
    text(verdict, "reviewer", "verdict")
    if verdict.get("verdict") not in VERDICTS:
        raise ValidationError("verdict: invalid verdict")

    blockers = sorted(
        finding_id
        for finding_id, finding in indexed.items()
        if finding["status"] == "open" and finding["severity"] in {"fatal", "error"}
    )
    declared = verdict.get("blocking_findings")
    if not isinstance(declared, list) or sorted(declared) != blockers:
        raise ValidationError("verdict: blocking_findings must equal the open fatal/error findings")
    if verdict.get("open_blocker_count") != len(blockers):
        raise ValidationError("verdict: open_blocker_count does not match blocking_findings")
    decision = verdict["verdict"]
    if blockers and decision != "REVISE":
        raise ValidationError("verdict: open blockers require REVISE")
    if not blockers and decision == "REVISE":
        raise ValidationError("verdict: REVISE requires an open blocker")

    return {
        "status": "valid",
        "findings": len(findings),
        "open_blockers": len(blockers),
        "verdict": decision,
        "checks": ["finding_shape", "evidence_refs", "blocker_count", "verdict_consistency"],
    }


def validate_files(findings: str | Path, verdict: str | Path) -> dict[str, Any]:
    return validate_records(load_jsonl(findings), load_object(verdict))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--verdict", required=True)
    args = parser.parse_args()
    try:
        result = validate_files(args.findings, args.verdict)
    except (OSError, ValidationError) as exc:
        print(f"review check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
