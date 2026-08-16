#!/usr/bin/env python3
"""Offline self-test for the standalone asset checker."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from asset_check import SKILL_ROOT, ValidationError, load_jsonl, validate_records

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("selftest.py requires Python 3.10 or newer")


def expect_failure(characters: list[dict], looks: list[dict], marker: str) -> None:
    try:
        validate_records(characters, looks)
    except ValidationError as exc:
        if marker not in str(exc):
            raise AssertionError(f"expected {marker!r}, got {exc!s}") from exc
    else:
        raise AssertionError(f"expected validation failure containing {marker!r}")


def main() -> int:
    example = Path(SKILL_ROOT, "examples/minimal")
    characters = load_jsonl(example / "characters.jsonl")
    looks = load_jsonl(example / "looks.jsonl")
    result = validate_records(characters, looks)
    assert result["characters"] == 1 and result["looks"] == 1

    duplicate = copy.deepcopy(characters[0])
    expect_failure([*characters, duplicate], looks, "duplicate character_id")

    broken_look = copy.deepcopy(looks)
    broken_look[0]["character_ref"]["record_id"] = "CHAR-MISSING"
    expect_failure(characters, broken_look, "does not resolve")

    candidate = copy.deepcopy(characters)
    candidate[0]["creator_acceptance"] = {"status": "proposed", "decision_ref": None}
    assert validate_records(candidate, looks)["status"] == "valid"

    invalid = copy.deepcopy(characters)
    invalid[0]["creator_acceptance"] = {"status": "approved", "decision_ref": None}
    expect_failure(invalid, looks, "invalid creator_acceptance status")

    print("5 self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
