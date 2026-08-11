#!/usr/bin/env python3
"""Build and verify one stable chapter index for a long source novel.

Every stage of novel analysis slices the same source file. If each stage ran its
own regular expression the slices would disagree, and a chapter analysed under
one boundary would be aggregated under another. This script owns the only
slicing truth: it detects chapter boundaries once, binds each span to a content
hash, and refuses an index whose numbering is not continuous.

It performs no editorial judgement. Which chapters matter, what they mean and
how they adapt are decisions for the skill workflow, not for this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


# Creators run these scripts on whatever interpreter their machine provides, so
# an unsupported version must say so instead of failing inside an import.
MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "short-drama needs Python {}.{} or newer; this interpreter is {}.{}".format(
            *MINIMUM_PYTHON, sys.version_info.major, sys.version_info.minor
        )
    )

SCHEMA_VERSION = "1.0.0-draft"

# Chapter numbers appear as Arabic digits or Chinese numerals. 千 and 两 are
# included because serialized fiction routinely passes 1000 chapters, and
# 第两百章 is as common as 第二百章 in that range.
CHINESE_NUMERALS = "零一二三四五六七八九十百千两"
CHAPTER_RE = re.compile(
    r"^[ \t　]*第\s*([0-9]+|[" + CHINESE_NUMERALS + r"]+)\s*[章节回]"
    r"[ \t　]*(.*?)[ \t　]*$"
)
CHINESE_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000}


def chinese_to_int(text: str) -> int | None:
    """Convert 一 / 十五 / 两百零三 / 一千零一 to an int, or None if malformed.

    Returning None rather than raising matters: a heading whose number cannot be
    read must be reported as an unreadable heading, not crash the whole index
    and leave the creator with no boundary table at all.
    """

    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    digit_seen = False
    for character in text:
        if character in CHINESE_DIGITS:
            section = CHINESE_DIGITS[character]
            digit_seen = True
        elif character in CHINESE_UNITS:
            unit = CHINESE_UNITS[character]
            # 十五 means 15, so a leading 十 carries an implicit one.
            section = section or 1
            if unit == 10:
                total += section * unit
            else:
                total += section * unit
            section = 0
            digit_seen = True
        else:
            return None
    if not digit_seen:
        return None
    return total + section


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _visible_width(text: str) -> int:
    """Count characters as a creator counts them, not as bytes."""

    return sum(1 for character in text if not unicodedata.combining(character))


def find_heading_lines(lines: list[str]) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for offset, line in enumerate(lines):
        match = CHAPTER_RE.match(line)
        if match is None:
            continue
        number = chinese_to_int(match.group(1))
        headings.append(
            {
                "line_index": offset,
                "raw": line.strip(),
                "number": number,
                "title": match.group(2).strip(),
            }
        )
    return headings


# A contents entry is one line; the next follows immediately or after a blank.
# Chapter prose never packs headings this tightly, so the gap is an absolute
# signal and does not need calibrating against the rest of the file.
CONTENTS_MAX_GAP = 3
CONTENTS_MIN_ENTRIES = 3


def drop_leading_table_of_contents(
    headings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Discard a leading contents block, which repeats every chapter heading.

    Density alone is not enough to decide. A median-based threshold breaks
    exactly when the contents block is a large share of all headings, because
    the block then drags the median into its own range and survives the test.

    So the rule is density plus corroboration: a leading run of headings packed
    within `CONTENTS_MAX_GAP` lines is dropped only if the chapter numbers it
    lists reappear among the headings that follow. A contents block always
    duplicates the chapters it indexes; a genuinely dense opening does not.
    Without this the index carries two "第一章" rows and every later stage
    slices at the contents entry, which holds no prose at all.
    """

    if len(headings) < CONTENTS_MIN_ENTRIES * 2:
        return headings, 0
    numbers = [heading["number"] for heading in headings]
    if numbers[0] is None:
        return headings, 0
    # The cut is where numbering restarts: a contents block is followed by the
    # same chapters again. Anchoring on the gap instead is off by one, because
    # the step from the last contents entry to chapter one is itself small.
    cut = 0
    for index in range(1, len(headings)):
        if numbers[index] is not None and numbers[index] <= numbers[0]:
            cut = index
            break
    if cut < CONTENTS_MIN_ENTRIES or cut > len(headings) - cut:
        return headings, 0
    internal_gaps = [
        headings[index + 1]["line_index"] - headings[index]["line_index"]
        for index in range(cut - 1)
    ]
    if any(gap > CONTENTS_MAX_GAP for gap in internal_gaps):
        # Numbering restarts, but the prefix holds real prose between headings.
        # That is a multi-volume book, not a contents block.
        return headings, 0
    dropped = {number for number in numbers[:cut] if number is not None}
    remaining = {number for number in numbers[cut:] if number is not None}
    if not dropped or not dropped <= remaining:
        # The packed prefix indexes chapters that never appear. It is part of
        # the story, not a contents list, so keep it.
        return headings, 0
    return headings[cut:], cut


def build_chapters(
    lines: list[str], headings: list[dict[str, Any]], raw: bytes
) -> list[dict[str, Any]]:
    text = raw.decode("utf-8")
    line_offsets: list[int] = []
    cursor = 0
    for line in lines:
        line_offsets.append(cursor)
        cursor += len(line) + 1
    chapters: list[dict[str, Any]] = []
    for position, heading in enumerate(headings):
        start_line = heading["line_index"]
        end_line = (
            headings[position + 1]["line_index"]
            if position + 1 < len(headings)
            else len(lines)
        )
        start_char = line_offsets[start_line]
        end_char = (
            line_offsets[end_line] if end_line < len(line_offsets) else len(text)
        )
        body = text[start_char:end_char]
        chapters.append(
            {
                "sequence": position + 1,
                "source_number": heading["number"],
                "title": heading["title"],
                "heading": heading["raw"],
                "line_start": start_line + 1,
                "line_end": end_line,
                "char_count": _visible_width(body),
                "content_sha256": sha256_bytes(body.encode("utf-8")),
            }
        )
    return chapters


def disambiguate_volumes(chapters: list[dict[str, Any]]) -> bool:
    """Flag a multi-volume source instead of guessing which 第一章 is real.

    A book whose volumes each restart at 第一章 is a legal structure, not a
    defect. Sequence numbering already gives every chapter one identity, so the
    only thing needed here is to say the source numbers repeat, and let the
    workflow keep volume context in the title.
    """

    seen: set[int] = set()
    for chapter in chapters:
        number = chapter["source_number"]
        if number is None:
            continue
        if number in seen:
            return True
        seen.add(number)
    return False


def validate_chapters(chapters: list[dict[str, Any]], restarts: bool) -> list[str]:
    problems: list[str] = []
    if not chapters:
        problems.append("no chapter heading matched; the source may need manual spans")
        return problems
    unreadable = [
        chapter["heading"]
        for chapter in chapters
        if chapter["source_number"] is None
    ]
    if unreadable:
        problems.append(
            "unreadable chapter numbers: " + ", ".join(unreadable[:5])
        )
    if not restarts:
        numbers = [
            chapter["source_number"]
            for chapter in chapters
            if chapter["source_number"] is not None
        ]
        for previous, current in zip(numbers, numbers[1:]):
            if current == previous:
                problems.append(f"duplicate chapter number {current}")
                break
            if current != previous + 1:
                problems.append(
                    f"chapter numbering jumps from {previous} to {current}"
                )
                break
    empty = [
        chapter["sequence"] for chapter in chapters if chapter["char_count"] < 50
    ]
    if empty:
        problems.append(
            "chapters with almost no body text at sequence "
            + ", ".join(str(item) for item in empty[:5])
        )
    return problems


def build_index(source: Path) -> dict[str, Any]:
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    lines = text.split("\n")
    headings = find_heading_lines(lines)
    headings, dropped = drop_leading_table_of_contents(headings)
    chapters = build_chapters(lines, headings, raw)
    restarts = disambiguate_volumes(chapters)
    problems = validate_chapters(chapters, restarts)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "novel_chapter_index",
        "source": {
            "artifact": source.name,
            "sha256": sha256_bytes(raw),
            "char_count": _visible_width(text),
            "line_count": len(lines),
        },
        "contents_entries_dropped": dropped,
        "volume_numbering_restarts": restarts,
        "chapter_count": len(chapters),
        "chapters": chapters,
        "problems": problems,
    }


def verify_index(index_path: Path, source: Path) -> dict[str, Any]:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    raw = source.read_bytes()
    problems: list[str] = []
    if index.get("source", {}).get("sha256") != sha256_bytes(raw):
        problems.append(
            "source bytes changed since the index was built; rebuild the index"
        )
        return {"verified": False, "problems": problems}
    text = raw.decode("utf-8")
    lines = text.split("\n")
    line_offsets: list[int] = []
    cursor = 0
    for line in lines:
        line_offsets.append(cursor)
        cursor += len(line) + 1
    for chapter in index.get("chapters", []):
        start = line_offsets[chapter["line_start"] - 1]
        end = (
            line_offsets[chapter["line_end"]]
            if chapter["line_end"] < len(line_offsets)
            else len(text)
        )
        digest = sha256_bytes(text[start:end].encode("utf-8"))
        if digest != chapter["content_sha256"]:
            problems.append(
                f"chapter {chapter['sequence']} span no longer matches its hash"
            )
    return {"verified": not problems, "problems": problems}


def coverage(index_path: Path, analysis_dir: Path) -> dict[str, Any]:
    """Report which chapters have no analysis file yet.

    Counting is the whole point: a pipeline that silently skips chapter 47
    produces an aggregate that looks complete and is not.
    """

    index = json.loads(index_path.read_text(encoding="utf-8"))
    expected = {chapter["sequence"] for chapter in index.get("chapters", [])}
    found: set[int] = set()
    pattern = re.compile(r"(?:^|\D)(\d+)")
    for path in sorted(analysis_dir.glob("*.md")):
        match = pattern.search(path.stem)
        if match is not None:
            found.add(int(match.group(1)))
    missing = sorted(expected - found)
    return {
        "expected": len(expected),
        "present": len(expected & found),
        "missing": missing,
        "unexpected": sorted(found - expected),
        "complete": not missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("index", help="build the chapter index for one source")
    build.add_argument("source", type=Path)
    build.add_argument("--out", type=Path, default=None)

    check = sub.add_parser("verify", help="re-check an index against its source")
    check.add_argument("index", type=Path)
    check.add_argument("source", type=Path)

    cover = sub.add_parser("coverage", help="report chapters with no analysis file")
    cover.add_argument("index", type=Path)
    cover.add_argument("analysis_dir", type=Path)

    args = parser.parse_args(argv)

    if args.command == "index":
        document = build_index(args.source)
        payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out is not None:
            args.out.write_text(payload + "\n", encoding="utf-8")
            summary = {
                "chapter_count": document["chapter_count"],
                "problems": document["problems"],
                "out": str(args.out),
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(payload)
        return 1 if document["problems"] else 0

    if args.command == "verify":
        result = verify_index(args.index, args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["verified"] else 1

    result = coverage(args.index, args.analysis_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
