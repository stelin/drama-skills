#!/usr/bin/env python3
"""Validate the structural core of standalone character and look records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("asset_check.py requires Python 3.10 or newer")

SKILL_ROOT = Path(__file__).resolve().parents[1]
HASH_RE = re.compile(r"[0-9a-f]{64}")
ACCEPTANCE_STATUSES = {"accepted", "proposed", "pending_choice"}


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
            raise ValidationError(f"{path}:{number}: each JSONL record must be an object")
        records.append(record)
    if not records:
        raise ValidationError(f"{path}: no records")
    return records


def require_text(record: dict[str, Any], key: str, label: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}: {key} must be non-empty text")
    return value


def require_list(record: dict[str, Any], key: str, label: str) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{label}: {key} must be a non-empty list")
    return value


def validate_ref(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{label}: reference must be an object")
    for key in ("owner", "artifact", "hash", "record_id"):
        require_text(value, key, label)
    if HASH_RE.fullmatch(str(value["hash"])) is None:
        raise ValidationError(f"{label}: hash must be lowercase sha256")


def validate_acceptance(value: Any, label: str) -> None:
    if not isinstance(value, dict) or value.get("status") not in ACCEPTANCE_STATUSES:
        raise ValidationError(f"{label}: invalid creator_acceptance status")
    decision_ref = value.get("decision_ref")
    if value["status"] == "accepted":
        validate_ref(decision_ref, f"{label}.decision_ref")
    elif decision_ref is not None:
        validate_ref(decision_ref, f"{label}.decision_ref")


def validate_records(
    characters: list[dict[str, Any]], looks: list[dict[str, Any]]
) -> dict[str, Any]:
    character_ids: set[str] = set()
    for index, record in enumerate(characters, 1):
        label = f"character[{index}]"
        character_id = require_text(record, "character_id", label)
        if not character_id.startswith("CHAR-"):
            raise ValidationError(f"{label}: character_id must start with CHAR-")
        if character_id in character_ids:
            raise ValidationError(f"{label}: duplicate character_id {character_id}")
        character_ids.add(character_id)
        require_text(record, "display_name", label)
        anchors = require_list(record, "identity_anchors", label)
        if any(not isinstance(item, str) or not item.strip() for item in anchors):
            raise ValidationError(f"{label}: identity_anchors must contain text")
        for ref_index, ref in enumerate(require_list(record, "source_refs", label), 1):
            validate_ref(ref, f"{label}.source_refs[{ref_index}]")
        validate_acceptance(record.get("creator_acceptance"), label)

    look_ids: set[str] = set()
    for index, record in enumerate(looks, 1):
        label = f"look[{index}]"
        look_id = require_text(record, "look_id", label)
        if not look_id.startswith("LOOK-"):
            raise ValidationError(f"{label}: look_id must start with LOOK-")
        if look_id in look_ids:
            raise ValidationError(f"{label}: duplicate look_id {look_id}")
        look_ids.add(look_id)
        character_ref = record.get("character_ref")
        validate_ref(character_ref, f"{label}.character_ref")
        assert isinstance(character_ref, dict)
        if character_ref["record_id"] not in character_ids:
            raise ValidationError(
                f"{label}: character_ref does not resolve: {character_ref['record_id']}"
            )
        differences = record.get("differences")
        if not isinstance(differences, dict) or not any(differences.values()):
            raise ValidationError(f"{label}: differences must describe an observable change")
        validity = record.get("validity")
        if not isinstance(validity, dict) or not validity.get("from"):
            raise ValidationError(f"{label}: validity.from is required")
        validate_acceptance(record.get("creator_acceptance"), label)

    return {
        "status": "valid",
        "characters": len(characters),
        "looks": len(looks),
        "checks": ["unique_ids", "acceptance_shape", "source_refs", "look_binding"],
    }


def validate_files(characters: str | Path, looks: str | Path) -> dict[str, Any]:
    return validate_records(load_jsonl(characters), load_jsonl(looks))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--characters", required=True)
    parser.add_argument("--looks", required=True)
    args = parser.parse_args()
    try:
        result = validate_files(args.characters, args.looks)
    except (OSError, ValidationError) as exc:
        print(f"asset check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
