#!/usr/bin/env python3
"""Validate standalone image-prompt specs without generating media."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("image_prompt_check.py requires Python 3.10 or newer")

SKILL_ROOT = Path(__file__).resolve().parents[1]
HASH_RE = re.compile(r"[0-9a-f]{64}")
PURPOSES = {
    "character_sheet",
    "location_plate",
    "prop_plate",
    "look_state_variant",
    "edit_delta",
    "lookdev_frame",
}
VENDOR_FIELDS = {
    "authorization",
    "credential",
    "credentials",
    "model",
    "model_id",
    "model_name",
    "provider",
    "provider_id",
    "api_key",
    "task_id",
    "remote_id",
    "access_token",
    "token",
    "secret",
    "password",
}
NORMALIZED_VENDOR_FIELDS = {re.sub(r"[^a-z0-9]", "", key) for key in VENDOR_FIELDS}


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
            raise ValidationError(f"{path}:{number}: each record must be an object")
        records.append(record)
    if not records:
        raise ValidationError(f"{path}: no prompt specs")
    return records


def text(record: dict[str, Any], key: str, label: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}: {key} must be non-empty text")
    return value


def nonempty_list(record: dict[str, Any], key: str, label: str) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{label}: {key} must be a non-empty list")
    return value


def validate_ref(value: Any, label: str, *, field_allowed: bool = True) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{label}: reference must be an object")
    for key in ("owner", "artifact", "hash"):
        text(value, key, label)
    if HASH_RE.fullmatch(str(value["hash"])) is None:
        raise ValidationError(f"{label}: hash must be lowercase sha256")
    if "record_id" not in value and (not field_allowed or "field" not in value):
        raise ValidationError(f"{label}: record_id or field is required")


def validate_reference_bindings(record: dict[str, Any], label: str) -> None:
    bindings = record.get("reference_bindings", [])
    if not isinstance(bindings, list):
        raise ValidationError(f"{label}: reference_bindings must be a list")
    slots: set[str] = set()
    orders: set[int] = set()
    for index, binding in enumerate(bindings, 1):
        item = f"{label}.reference_bindings[{index}]"
        if not isinstance(binding, dict):
            raise ValidationError(f"{item}: binding must be an object")
        slot = text(binding, "slot_id", item)
        order = binding.get("order")
        if slot in slots:
            raise ValidationError(f"{item}: duplicate slot_id {slot}")
        if not isinstance(order, int) or order < 1 or order in orders:
            raise ValidationError(f"{item}: order must be a unique positive integer")
        slots.add(slot)
        orders.add(order)
        validate_ref(binding.get("artifact_ref"), f"{item}.artifact_ref")
        text(binding, "role", item)
        nonempty_list(binding, "may_control", item)
        nonempty_list(binding, "must_not_control", item)
        admission = binding.get("admission_status")
        if admission not in {"unverified", "creator_described", "visually_inspected"}:
            raise ValidationError(f"{item}: invalid admission_status")
        if admission == "unverified" and not binding.get("unresolved_risks"):
            raise ValidationError(f"{item}: unverified references need unresolved_risks")


def vendor_field_paths(value: object, prefix: str = "") -> list[str]:
    leaked: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
            if normalized in NORMALIZED_VENDOR_FIELDS:
                leaked.append(path)
            leaked.extend(vendor_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            leaked.extend(vendor_field_paths(child, f"{prefix}[{index}]"))
    return leaked


def validate_asset_spec(record: dict[str, Any], label: str) -> None:
    binding = record.get("asset_binding")
    if not isinstance(binding, dict):
        raise ValidationError(f"{label}: asset_binding must be an object")
    validate_ref(binding.get("identity_ref"), f"{label}.asset_binding.identity_ref")
    validate_ref(binding.get("variant_ref"), f"{label}.asset_binding.variant_ref")
    for index, ref in enumerate(nonempty_list(record, "source_refs", label), 1):
        validate_ref(ref, f"{label}.source_refs[{index}]")
    nonempty_list(record, "identity_or_form_anchors", label)

    if record["purpose"] == "edit_delta":
        edit = record.get("edit")
        if not isinstance(edit, dict):
            raise ValidationError(f"{label}: edit_delta requires edit")
        validate_ref(edit.get("target_ref"), f"{label}.edit.target_ref")
        nonempty_list(edit, "changes", f"{label}.edit")
        nonempty_list(edit, "preserve", f"{label}.edit")
        text(edit, "continuity_impact", f"{label}.edit")

    handling = record.get("text_handling")
    if isinstance(handling, dict):
        treatment = handling.get("render_treatment")
        if not isinstance(treatment, dict):
            raise ValidationError(f"{label}: text_handling.render_treatment is required")
        if handling.get("source_mode") == "exact_readable" and treatment.get("mode") == "readable":
            text(treatment, "exact_text", f"{label}.text_handling.render_treatment")
            negatives = " ".join(str(item).casefold() for item in record.get("negative_constraints", []))
            if "no text" in negatives or "无文字" in negatives:
                raise ValidationError(f"{label}: readable text conflicts with a no-text constraint")


def validate_lookdev_spec(record: dict[str, Any], label: str) -> None:
    validate_ref(record.get("direction_ref"), f"{label}.direction_ref")
    validate_ref(record.get("production_profile_ref"), f"{label}.production_profile_ref")
    subjects = nonempty_list(record, "subject_bindings", label)
    for index, subject in enumerate(subjects, 1):
        if not isinstance(subject, dict):
            raise ValidationError(f"{label}.subject_bindings[{index}]: must be an object")
        validate_ref(subject.get("identity_ref"), f"{label}.subject_bindings[{index}].identity_ref")
        text(subject, "role", f"{label}.subject_bindings[{index}]")
    text(record, "test_question", label)
    nonempty_list(record, "stable_visual_rules", label)
    if record.get("lookdev_axis") == "high_pressure_scene":
        refs = nonempty_list(record, "story_context_refs", label)
        for index, ref in enumerate(refs, 1):
            validate_ref(ref, f"{label}.story_context_refs[{index}]")


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    identifiers: set[str] = set()
    for index, record in enumerate(records, 1):
        label = f"spec[{index}]"
        spec_id = text(record, "spec_id", label)
        if spec_id in identifiers:
            raise ValidationError(f"{label}: duplicate spec_id {spec_id}")
        identifiers.add(spec_id)
        purpose = record.get("purpose")
        if purpose not in PURPOSES:
            raise ValidationError(f"{label}: invalid purpose {purpose!r}")
        if record.get("status") != "candidate":
            raise ValidationError(f"{label}: specs must remain candidate until creator acceptance")
        leaked = sorted(vendor_field_paths(record))
        if leaked:
            raise ValidationError(f"{label}: provider execution fields are forbidden: {', '.join(leaked)}")
        prompt = text(record, "generic_prompt", label)
        if HASH_RE.search(prompt) or "<sha256>" in prompt:
            raise ValidationError(f"{label}: generic_prompt leaks internal hashes")
        validate_reference_bindings(record, label)
        if purpose == "lookdev_frame":
            validate_lookdev_spec(record, label)
        else:
            validate_asset_spec(record, label)
    return {
        "status": "valid",
        "specs": len(records),
        "checks": ["unique_ids", "accepted_bindings", "reference_slots", "prompt_hygiene"],
    }


def validate_file(path: str | Path) -> dict[str, Any]:
    return validate_records(load_jsonl(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specs")
    args = parser.parse_args()
    try:
        result = validate_file(args.specs)
    except (OSError, ValidationError) as exc:
        print(f"image prompt check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
