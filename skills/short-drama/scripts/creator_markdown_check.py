#!/usr/bin/env python3
"""Validate the executable cross-document contract of one creator-first episode."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from collections.abc import Iterable
from typing import NamedTuple, Optional


MINIMUM_PYTHON = (3, 9)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "creator_markdown_check.py requires Python {}.{}, running {}.{}".format(
            *MINIMUM_PYTHON, sys.version_info.major, sys.version_info.minor
        )
    )


REQUIRED_DOCUMENTS = (
    "剧本.md",
    "视觉设定.md",
    "图片提示词.md",
    "分镜.md",
    "视频提示词.md",
)
SECTION_RE = re.compile(r"^## ((?:SHOT|MOTION)-[A-Z0-9-]+)\b", re.MULTILINE)
IMG_RE = re.compile(r"\b(IMG-[A-Z0-9-]+)《([^》]+)》（控制：([^）]+)）")
# 用途 is optional in the pattern on purpose: a declaration written before this
# field existed still parses, so the creator gets "REF 缺少用途" instead of the
# generic syntax error that gives no hint about what to add.
REF_RE = re.compile(
    r"(REF-[A-Z0-9-]+)（顺序：([1-9]\d*)）· "
    r"([^；\n]+?\.(?:png|jpe?g|webp))《([^》\n]+)》"
    r"（(?:用途：([^；）\n]+)；)?控制：([^；）]+)；不得控制：([^）]+)）",
    re.IGNORECASE,
)
# One picture answers one question. 「同一张图承担两个作用时分开说明」 in
# references/reference-roles.md is what makes a slot translatable into a
# provider role, so the vocabulary is closed rather than free prose.
REF_PURPOSES = (
    "身份",
    "造型状态",
    "地理",
    "构图",
    "尺度",
    "效果",
    "起始帧",
    "结束帧",
    "风格",
)
EXPLICIT_TEXT_TO_VIDEO = "无（创作者已明确选择文生视频）"
PENDING_REFERENCE_SUFFIX_RE = re.compile(r"；待补参考图：[^；。\n]+。?$")
VISUAL_CATEGORIES = ("人物", "造型", "地点", "道具")
VISUAL_SETTING_LINE_RE = re.compile(
    r"^#{2,4}[ \t　]*(?:" + "|".join(VISUAL_CATEGORIES) + r")[^\n]*$", re.MULTILINE
)
VISUAL_SETTING_HEADING_RE = re.compile(
    r"^## (" + "|".join(VISUAL_CATEGORIES) + r") · (.+?)[ \t　]*$", re.MULTILINE
)
# Any other `## <word> · <name>` heading, so a 视觉依据 entry that fails to
# resolve can say "the entry is there, the section word is not one of the four"
# instead of blaming the storyboard for a `视觉设定.md` problem.
OTHER_SETTING_HEADING_RE = re.compile(r"^## ([^\n·]+?) · (.+?)[ \t　]*$", re.MULTILINE)
# 画面代称 is the one field the coverage check depends on, so — like a
# continuity lock — anything that looks like it has to parse rather than
# silently drop out.
# Anchored at the start of the line so a sentence that merely mentions the
# field is prose, not a malformed declaration.
SCREEN_NAME_LINE_RE = re.compile(
    r"^[ \t　]*[-*+]?[ \t　]*画面代称[ \t　]*[：:][^\n]*$", re.MULTILINE
)
SCREEN_NAME_RE = re.compile(
    r"^[ \t　]*[-*+][ \t　]*画面代称[：:](.+)$", re.MULTILINE
)
VISUAL_BASIS_PREFIX = "《视觉设定.md》·"
VISUAL_BASIS_ENTRY_RE = re.compile(
    r"(" + "|".join(VISUAL_CATEGORIES) + r")「([^」\n]+)」（控制：([^）\n]+)）"
)
# A subject a keyframe names but does not show — an owner's abandoned bag, a
# name on a screen, a homonym of an entry name. SHT-22 excludes these from
# coverage, so the field needs a way to say so instead of forcing the creator
# to declare an absent subject as present.
OFFSCREEN_PREFIX = "；画外："
OFFSCREEN_ENTRY_RE = re.compile(
    r"(" + "|".join(VISUAL_CATEGORIES) + r")「([^」\n]+)」"
)
# A declared lock must never become a no-op. Anything that *looks* like a lock
# line -- any list marker, any leading whitespace -- is captured here and then
# has to parse, so a creator who indents the bullet under 识别锚点 gets an error
# instead of silent non-enforcement.
LOCK_LINE_RE = re.compile(r"^[ \t\u3000]*[-*+][ \t\u3000]*连续性锁[：:].*$", re.MULTILINE)
LOCK_RE = re.compile(
    r"^[ \t\u3000]*[-*+][ \t\u3000]*连续性锁：(LOCK-[A-Z0-9-]+)《([^》\n]+)》"
    r"（镜头：([^；）\n]+)"
    r"(?:；图片提示词项：([^；）\n]+))?）"
    r"· 锁面：(.+)$"
)
# The surface has to name what is in the picture. A match glued to a negation
# ("no pale blue sweater") describes what must be absent, so it cannot be the
# evidence that the fact is present.
# Chinese runs without spaces, so the CJK markers cannot require a preceding
# boundary the way the English ones do. A bare 无 is deliberately not a marker:
# 无袖毛衣 describes the garment rather than excluding it.
NEGATION_RE = re.compile(
    r"(?:"
    r"(?:^|[\s,;:(\[/—-])(?:no|not|non|never|without|avoid|excludes?|excluding|"
    r"free\s+of|--?no)(?:\s+(?:a|an|the|any|some))?[\s-]*"
    r"|(?:不要|不得|不能|不应|不含|不出现|没有|未|避免|禁止|排除|去掉|移除)"
    r"(?:出现|包含|存在|带|有)?[\s]*"
    r")$",
    re.IGNORECASE,
)


def _sections(document: str, kind: str) -> dict[str, str]:
    matches = [
        match
        for match in SECTION_RE.finditer(document)
        if match.group(1).startswith(f"{kind}-")
    ]
    return {
        match.group(1): document[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else None
        ]
        for index, match in enumerate(matches)
    }


def _fields(section: str, *, owner: str, errors: list[str]) -> dict[str, str]:
    pairs = re.findall(r"^- ([^：\n]+)：(.+)$", section, re.MULTILINE)
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            errors.append(f"{owner}: 字段重复: {key}")
        fields[key] = value
    return fields


def _plain(value: str) -> str:
    return value.strip().rstrip("。")


def _contains_ref_token(value: str) -> bool:
    return "ref-" in value.casefold()


def _is_none(value: str) -> bool:
    return not _contains_ref_token(value) and bool(
        re.fullmatch(r"无(?:（[^）]+）)?", _plain(value))
    )


def _is_explicit_text_to_video(value: str) -> bool:
    return _plain(value) == EXPLICIT_TEXT_TO_VIDEO


def _has_pending_references(value: str) -> bool:
    plain = _plain(value)
    return plain.startswith("无（待补参考图：") or bool(
        PENDING_REFERENCE_SUFFIX_RE.search(value.strip())
    )


def _is_no_external_reference(value: str) -> bool:
    return not _contains_ref_token(value) and bool(
        re.fullmatch(r"无(?:外部参考)?(?:；[^\n]*)?。?", value.strip())
    )


def _copyable_prompt(
    section: str, heading: str = r"可复制(?:通用)?提示词"
) -> Optional[str]:
    markers = list(re.finditer(rf"^### {heading}\s*$", section, re.MULTILINE))
    if len(markers) != 1:
        return None
    body = section[markers[0].end() :]
    following = re.search(r"^###\s+|^##\s+", body, re.MULTILINE)
    if following is not None:
        body = body[: following.start()]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines or any(not line.startswith(">") for line in lines):
        return None
    prompt = "\n".join(line[1:].lstrip() for line in lines).strip()
    return prompt or None


def _portable_path(value: str) -> bool:
    if not value or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return False
    parts = value.split("/")
    return not PurePosixPath(value).is_absolute() and not any(
        part in {"", ".", ".."} for part in parts
    )


def _inside(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _references(value: str, owner: str, project_root: Path, errors: list[str]) -> None:
    if _is_none(value):
        return
    reference_value = PENDING_REFERENCE_SUFFIX_RE.sub("", value.strip())
    matches = list(REF_RE.finditer(value))
    cursor = 0
    separators_are_valid = True
    for index, match in enumerate(matches):
        if reference_value[cursor : match.start()] != ("" if index == 0 else "；"):
            separators_are_valid = False
        cursor = match.end()
    trailing = reference_value[cursor:]
    if (
        len(matches) != len(re.findall(r"\bREF-[A-Z0-9-]+\b", value))
        or not matches
        or not separators_are_valid
        or trailing not in {"", "。"}
    ):
        # A gap list joined with ； reads as a fourth REF slot and would otherwise
        # be reported as broken REF syntax, whose obvious repair is deleting the
        # gap record -- the silent downgrade this contract exists to prevent.
        if "待补参考图" in value and not _has_pending_references(value):
            errors.append(
                f"{owner}: 待补参考图必须写在最后一个 REF 槽位之后，"
                "缺口之间只用、分隔"
            )
        else:
            errors.append(f"{owner}: 输入参考图必须使用完整 REF 语法")
        return
    refs = [(match.group(1), int(match.group(2)), match.group(3)) for match in matches]
    slots = [item[0] for item in refs]
    orders = [item[1] for item in refs]
    paths = [item[2] for item in refs]
    if len(slots) != len(set(slots)):
        errors.append(f"{owner}: REF 槽位重复")
    if len(orders) != len(set(orders)) or sorted(orders) != list(
        range(1, len(orders) + 1)
    ):
        errors.append(f"{owner}: REF 顺序必须唯一且从 1 连续编号")
    purposes = [
        match.group(5).strip() if match.group(5) else "" for match in matches
    ]
    path_purposes = list(zip(paths, purposes))
    if len(path_purposes) != len(set(path_purposes)):
        errors.append(f"{owner}: REF 路径与用途完全重复")
    for slot, purpose in zip(slots, purposes):
        if not purpose:
            errors.append(
                f"{owner}: REF 缺少用途: {slot}；用途只能是"
                f"{'、'.join(REF_PURPOSES)}其中一个"
            )
        elif purpose not in REF_PURPOSES:
            errors.append(
                f"{owner}: REF 用途不在允许集合内: {slot}（{purpose}）；"
                f"只能是{'、'.join(REF_PURPOSES)}"
            )
    for role in ("起始帧", "结束帧"):
        if purposes.count(role) > 1:
            errors.append(f"{owner}: 同一条目只能有一张{role}参考图")
    if "结束帧" in purposes and "起始帧" not in purposes:
        errors.append(f"{owner}: 绑定结束帧参考图时必须同时绑定起始帧")
    for match, (_, _, raw_path) in zip(matches, refs):
        label, may_control, must_not_control = (
            match.group(4),
            match.group(6),
            match.group(7),
        )
        if not _portable_path(raw_path):
            errors.append(f"{owner}: REF 路径不是安全的项目相对路径: {raw_path}")
        else:
            reference_path = project_root / raw_path
            if not _inside(reference_path, project_root):
                errors.append(f"{owner}: REF 路径越出项目根目录: {raw_path}")
            elif not reference_path.is_file():
                errors.append(f"{owner}: REF 文件不存在: {raw_path}")
        if not re.search(r"[\u4e00-\u9fff]", label):
            errors.append(f"{owner}: REF 缺少中文名称: {match.group(1)}")
        if not may_control.strip() or not must_not_control.strip():
            errors.append(f"{owner}: REF 必须同时声明控制与不得控制: {match.group(1)}")
        allowed = {item.strip() for item in re.split(r"[、,，]", may_control)}
        prohibited = {item.strip() for item in re.split(r"[、,，]", must_not_control)}
        if "" in allowed or "" in prohibited or allowed & prohibited:
            errors.append(f"{owner}: REF 控制与不得控制范围冲突: {match.group(1)}")


def _excerpt(value: str, limit: int = 60) -> str:
    """A short, single-line quote of an offending line for a diagnostic."""
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _unique(values: "Iterable[str]") -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalized(value: str) -> str:
    """Fold case and collapse whitespace so a hard-wrapped prompt still matches.

    A copyable prompt is one rendered paragraph; the line breaks the repo's
    Markdown style puts in it are not part of the text a creator wrote.
    """
    return re.sub(r"\s+", " ", value).strip().casefold()


def _wordish(character: str) -> bool:
    return bool(character) and character.isascii() and (
        character.isalnum() or character == "-"
    )


def _carries_surface(prompt: str, surface: str) -> bool:
    """Is this lock surface actually asserted by this prompt?

    Plain containment is not enough. `chipped white enamel mug` must not be
    satisfied by `unchipped ... mug`, and `no pale blue sweater` in a negative
    tail asserts the opposite of the fact the lock exists to hold.
    """
    haystack = _normalized(prompt)
    needle = _normalized(surface)
    if not needle:
        return False
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        before = haystack[start - 1] if start else ""
        after = haystack[end] if end < len(haystack) else ""
        # Only ASCII words have boundaries to glue across. Chinese is written
        # without spaces, so treating an adjacent CJK character as "glued" would
        # make a Chinese surface impossible to satisfy.
        glued = (
            (_wordish(needle[:1]) and _wordish(before))
            or (_wordish(needle[-1:]) and _wordish(after))
        )
        if not glued and NEGATION_RE.search(haystack[:start]) is None:
            return True
        start = haystack.find(needle, start + 1)
    return False


class VisualEntry(NamedTuple):
    """One `视觉设定.md` entry plus every name a prompt body may call it by."""

    category: str
    name: str
    designators: list[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.category, self.name)


def _visual_entries(document: str, errors: list[str]) -> list[VisualEntry]:
    """Parse the 人物/造型/地点/道具 entries of one `视觉设定.md`.

    A heading that *looks* like an entry but does not parse would silently drop
    out of the coverage check and then reappear as "视觉依据 names an entry that
    does not exist", so it is rejected here where the cause is visible.
    """
    for line in VISUAL_SETTING_LINE_RE.findall(document):
        if VISUAL_SETTING_HEADING_RE.match(line) is None:
            errors.append(
                "视觉设定.md: 条目标题必须写成 `## <人物|造型|地点|道具> · <名称>`: "
                + _excerpt(line)
            )
    for line in SCREEN_NAME_LINE_RE.findall(document):
        if SCREEN_NAME_RE.match(line) is None:
            errors.append(
                "视觉设定.md: 画面代称必须写成 `- 画面代称：<正文里的拼写>`: "
                + _excerpt(line)
            )
    headings = list(VISUAL_SETTING_HEADING_RE.finditer(document))
    entries: list[VisualEntry] = []
    seen: set[tuple[str, str]] = set()
    for index, heading in enumerate(headings):
        end = (
            headings[index + 1].start()
            if index + 1 < len(headings)
            else len(document)
        )
        category, name = heading.group(1), heading.group(2).strip()
        if not name:
            errors.append(f"视觉设定.md: {category}条目缺少名称")
            continue
        if (category, name) in seen:
            errors.append(f"视觉设定.md: 条目重复: {category}「{name}」")
            continue
        seen.add((category, name))
        declared = SCREEN_NAME_RE.findall(document[heading.end() : end])
        if not declared:
            # No declaration: the entry's own name is the designator, which is
            # what a prompt body written in the project's own language calls it.
            designators = [name]
        elif all(_is_none(_plain(raw)) for raw in declared):
            # `画面代称：无` is the deliberate opt-out for a name too common to
            # match reliably in prose (道具「手机」 against 手机店). It removes the
            # derived name too, otherwise the opt-out would do nothing.
            designators = []
        else:
            designators = []
            for raw in declared:
                value = _plain(raw)
                if _is_none(value):
                    continue
                for item in re.split(r"[、,，]", value):
                    item = item.strip()
                    if item and item not in designators:
                        designators.append(item)
        # Only a *declared* designator earns this diagnostic: the creator chose a
        # spelling the matcher cannot honour and deserves to know. A one-character
        # entry name they never declared is simply not name-matched, the same as
        # any entry in a project whose prompt body is written in another language.
        if declared:
            for designator in designators:
                if len(designator.strip()) < 2:
                    errors.append(
                        f"视觉设定.md: {category}「{name}」的画面代称「{designator}」"
                        "过短，无法在正文中可靠识别；请写成至少两个字符，或写「画面代称：无」"
                    )
        entries.append(VisualEntry(category, name, designators))
    return entries


def _named_entries(
    prompt: str, entries: list[VisualEntry], *, fold_case: bool = False
) -> set[tuple[str, str]]:
    """Which declared entries does this frozen keyframe actually call by name?

    Longer designators win: a keyframe that shows 「江晨手机」 names the prop, and
    the 人物「江晨」 substring inside it is not a second, unrelated claim.
    """
    haystack = re.sub(r"\s+", " ", prompt).strip()
    if fold_case:
        haystack = haystack.casefold()
    owners: dict[str, list[VisualEntry]] = {}
    for entry in entries:
        for designator in entry.designators:
            needle = re.sub(r"\s+", " ", designator).strip()
            if fold_case:
                needle = needle.casefold()
            # A one-character designator matches far too much prose to be
            # evidence; _visual_entries already reports it.
            if len(needle) < 2:
                continue
            owners.setdefault(needle, []).append(entry)
    named: set[tuple[str, str]] = set()
    # Spans of every occurrence of a longer designator, whether or not it was
    # credited. 「戒指盒」 occupies its characters even when the sentence is
    # 「没有戒指」, so 道具「戒指」 must not be read out of it.
    taken: list[tuple[int, int]] = []
    for needle in sorted(owners, key=len, reverse=True):
        occurrences: list[tuple[int, int]] = []
        start = haystack.find(needle)
        while start != -1:
            end = start + len(needle)
            occurrences.append((start, end))
            start = haystack.find(needle, start + 1)
        for start, end in occurrences:
            before = haystack[start - 1] if start else ""
            after = haystack[end] if end < len(haystack) else ""
            glued = (
                (_wordish(needle[:1]) and _wordish(before))
                or (_wordish(needle[-1:]) and _wordish(after))
            )
            # Strictly longer, so two entries sharing one designator are both
            # credited instead of the first in document order winning.
            inside_longer = any(
                taken_start <= start
                and end <= taken_end
                and taken_end - taken_start > end - start
                for taken_start, taken_end in taken
            )
            if (
                not glued
                and not inside_longer
                and NEGATION_RE.search(haystack[:start]) is None
            ):
                named.update(entry.key for entry in owners[needle])
        taken.extend(occurrences)
    return named


class VisualBasis(NamedTuple):
    """One shot's parsed 视觉依据: what it declares, and what it excludes."""

    parsed: bool
    declared: set[tuple[str, str]]
    offscreen: set[tuple[str, str]]

    @property
    def accounted(self) -> set[tuple[str, str]]:
        return self.declared | self.offscreen


def _resolve_entry(
    key: tuple[str, str],
    known: set[tuple[str, str]],
    other_headings: dict[str, str],
    owner: str,
    errors: list[str],
) -> None:
    if key in known:
        return
    category, name = key
    section = other_headings.get(name)
    if section is not None:
        errors.append(
            f"{owner}: 《视觉设定.md》里有「{name}」，但它的分节词是「{section}」；"
            "条目标题必须写成 `## <人物|造型|地点|道具> · <名称>`"
        )
    else:
        errors.append(
            f"{owner}: 视觉依据指向不存在的《视觉设定.md》条目: {category}「{name}」"
        )


def _check_named_coverage(
    prompt: str,
    owner: str,
    where: str,
    basis: "VisualBasis",
    entries: list[VisualEntry],
    errors: list[str],
) -> None:
    """Every entry this text calls by name is either in frame or declared 画外."""
    # Matching is case-sensitive so an ordinary English word never impersonates a
    # character called May or Will. A body that writes the name in another case
    # would otherwise fall out of the check silently, so it is reported here.
    named = _named_entries(prompt, entries)
    folded = _named_entries(prompt, entries, fold_case=True)
    for category, name in sorted(folded - named):
        errors.append(
            f"{owner}: {where}里的名字与画面代称大小写不一致: {category}「{name}」；"
            "同一个名字全集只用一个拼写"
        )
    for category, name in sorted(named):
        if (category, name) not in basis.accounted:
            errors.append(
                f"{owner}: {where}写到{category}「{name}」，视觉依据没有覆盖；"
                "本镜确实看不见时在视觉依据末尾加「；画外："
                f"{category}「{name}」」，正文里这个名字不可靠时在《视觉设定.md》"
                "写「画面代称：无」"
            )


def _visual_basis(
    value: str,
    owner: str,
    entries: list[VisualEntry],
    other_headings: dict[str, str],
    errors: list[str],
) -> VisualBasis:
    """Parse one shot's 视觉依据 and resolve it against `视觉设定.md`."""
    empty = VisualBasis(True, set(), set())
    if _is_none(value):
        return empty
    plain = _plain(value)
    offscreen_raw = ""
    if OFFSCREEN_PREFIX in plain:
        plain, _, offscreen_raw = plain.partition(OFFSCREEN_PREFIX)
    prefixed = plain.startswith(VISUAL_BASIS_PREFIX)
    body = plain[len(VISUAL_BASIS_PREFIX) :] if prefixed else ""
    matches = list(VISUAL_BASIS_ENTRY_RE.finditer(body)) if prefixed else []
    cursor = 0
    separators_are_valid = True
    for index, match in enumerate(matches):
        # Repeating 《视觉设定.md》· before each entry says the same thing and
        # reads naturally; rejecting it would cost a round trip over nothing.
        separator = body[cursor : match.start()]
        allowed = (
            {""}
            if index == 0
            else {"；", "；" + VISUAL_BASIS_PREFIX}
        )
        if separator not in allowed:
            separators_are_valid = False
        cursor = match.end()
    if not prefixed or not matches or not separators_are_valid or body[cursor:]:
        errors.append(
            f"{owner}: 视觉依据必须使用完整语法："
            "《视觉设定.md》·<人物|造型|地点|道具>「<名称>」（控制：<范围>），多项用；连接"
        )
        # Coverage is not reported on top of a parse failure: every entry would
        # be listed as uncovered and bury the one error that matters.
        return VisualBasis(False, set(), set())
    known = {entry.key for entry in entries}
    declared: set[tuple[str, str]] = set()
    for match in matches:
        key = (match.group(1), match.group(2).strip())
        if key in declared:
            errors.append(f"{owner}: 视觉依据条目重复: {key[0]}「{key[1]}」")
        declared.add(key)
        _resolve_entry(key, known, other_headings, owner, errors)
        if not match.group(3).strip():
            errors.append(f"{owner}: 视觉依据缺少控制范围: {key[0]}「{key[1]}」")
    offscreen: set[tuple[str, str]] = set()
    if offscreen_raw:
        offscreen_raw = offscreen_raw.replace(VISUAL_BASIS_PREFIX, "")
        remainder = OFFSCREEN_ENTRY_RE.sub("", offscreen_raw).strip("；、 ")
        offscreen_matches = list(OFFSCREEN_ENTRY_RE.finditer(offscreen_raw))
        if not offscreen_matches or remainder:
            errors.append(
                f"{owner}: 画外清单必须写成 `；画外：<人物|造型|地点|道具>「<名称>」`，多项用；连接"
            )
            return VisualBasis(False, set(), set())
        for match in offscreen_matches:
            key = (match.group(1), match.group(2).strip())
            if key in declared:
                errors.append(
                    f"{owner}: {key[0]}「{key[1]}」同时写进视觉依据和画外清单"
                )
            offscreen.add(key)
            _resolve_entry(key, known, other_headings, owner, errors)
    return VisualBasis(True, declared, offscreen)


class ContinuityLock(NamedTuple):
    """One declared cross-shot lock: the exact surface and where it applies."""

    lock_id: str
    surface: str
    shots: list[str]
    images: list[str]


def _continuity_locks(document: str, errors: list[str]) -> list[ContinuityLock]:
    """Parse the declared continuity locks of one 视觉设定.md."""
    locks: list[ContinuityLock] = []
    seen: set[str] = set()
    for line in LOCK_LINE_RE.findall(document):
        match = LOCK_RE.match(line)
        if match is None:
            errors.append(
                "视觉设定.md: 连续性锁必须使用完整语法: " + _excerpt(line)
            )
            continue
        lock_id, label, scope, image_scope, surface = match.groups()
        if lock_id in seen:
            errors.append(f"{lock_id}: 连续性锁 ID 重复")
            continue
        seen.add(lock_id)
        if not re.search(r"[\u3400-\u9fff]", label):
            errors.append(f"{lock_id}: 连续性锁缺少中文名称")
        surface = _plain(surface)
        if not surface:
            errors.append(f"{lock_id}: 连续性锁缺少锁面")
            continue
        shots = _unique(
            item.strip() for item in re.split(r"[、,，]", _plain(scope)) if item.strip()
        )
        if not shots:
            errors.append(f"{lock_id}: 连续性锁缺少镜头范围")
            continue
        if "全集" in shots and len(shots) != 1:
            errors.append(f"{lock_id}: 连续性锁的镜头范围不能把全集与具体镜头混写")
            continue
        images: list[str] = []
        if image_scope is not None and not _is_none(image_scope):
            images = _unique(
                item.strip()
                for item in re.split(r"[、,，]", _plain(image_scope))
                if item.strip()
            )
            if any(not item.startswith("IMG-") for item in images):
                errors.append(f"{lock_id}: 连续性锁的图片提示词项必须使用 IMG-  ID")
                continue
        locks.append(ContinuityLock(lock_id, surface, shots, images))
    return locks


def _prompt_language(project_root: Path) -> str:
    """The language a copyable prompt body is written in.

    Mirrors the skills' own routing: the project's declared prompt language,
    falling back to `en` when there is no `short-drama.json` -- which is what
    the storyboard skill tells the keyframe author to assume.
    """
    configuration = project_root / "short-drama.json"
    if not configuration.is_file():
        return "en"
    try:
        project = json.loads(configuration.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "en"
    if not isinstance(project, dict):
        return "en"
    authority = project.get("creator_authority")
    profile = (
        authority.get("production_profile") if isinstance(authority, dict) else None
    )
    if isinstance(profile, dict) and profile.get("status") == "accepted":
        choices = profile.get("choices")
        if isinstance(choices, dict):
            declared = choices.get("video_prompt_language")
            if isinstance(declared, str) and declared:
                return declared
    formats = project.get("format")
    declared = formats.get("prompt_language") if isinstance(formats, dict) else None
    return declared if isinstance(declared, str) and declared else "en"


def _check_language_designators(
    project_root: Path, *, entries: list[VisualEntry], errors: list[str]
) -> None:
    """Every character must be nameable in the prompt body's language.

    Without this, omitting `画面代称` is a silent opt-out of the coverage check
    for exactly the projects that need it -- the keyframe body defaults to `en`
    while `视觉设定.md` is Chinese, which is the shape issue #94 reported.

    This deliberately does not wait until some shot's 视觉依据 references the
    entry. Gating on that made the two halves of the contract land in different
    rounds: a document missing 视觉依据 got one error, and only after fixing it
    did the missing 画面代称 appear.
    """
    if _prompt_language(project_root).casefold().startswith("zh"):
        return
    for entry in entries:
        if entry.category != "人物":
            continue
        if entry.designators == [entry.name]:
            errors.append(
                f"视觉设定.md: 人物「{entry.name}」缺少画面代称；"
                "提示词正文不是中文时，写「画面代称：<正文里的拼写>」，"
                "正文从不点名时写「画面代称：无」"
            )


def _check_continuity_locks(
    locks: list[ContinuityLock],
    *,
    shots: dict[str, str],
    motion_by_shot: dict[str, tuple[str, str, Optional[str]]],
    image_prompts: dict[str, Optional[str]],
    errors: list[str],
) -> None:
    """Require every declared lock surface to be present where it was scoped."""
    for lock in locks:
        lock_id = lock.lock_id
        surface = lock.surface
        targets = sorted(shots) if lock.shots == ["全集"] else lock.shots
        for shot_id in targets:
            if shot_id not in shots:
                errors.append(f"{lock_id}: 连续性锁指向不存在的镜头: {shot_id}")
                continue
            keyframe = _copyable_prompt(shots[shot_id], heading=r"冻结关键帧提示词")
            if keyframe is None:
                errors.append(f"{lock_id}: {shot_id} 缺少可读的冻结关键帧提示词")
            elif not _carries_surface(keyframe, surface):
                errors.append(f"{lock_id}: {shot_id} 冻结关键帧提示词缺少锁面")
            motion = motion_by_shot.get(shot_id)
            if motion is None:
                continue
            motion_id, _, copyable_prompt = motion
            if copyable_prompt is not None and not _carries_surface(
                copyable_prompt, surface
            ):
                errors.append(f"{lock_id}: {motion_id} 可复制提示词缺少锁面")
        for image_id in lock.images:
            if image_id not in image_prompts:
                errors.append(f"{lock_id}: 连续性锁指向不存在的 IMG 条目: {image_id}")
                continue
            image_prompt = image_prompts[image_id]
            if image_prompt is not None and not _carries_surface(image_prompt, surface):
                errors.append(f"{lock_id}: {image_id} 可复制提示词缺少锁面")


# ---------------------------------------------------------------------------
# Derivation (AST-15), duration ledger (SHT-16 / SHT-27), delivery groups
# (VID-13 / VID-15), prop scale phrase (IMG-16), identity-sheet similarity
# warning (IMG-17) and opt-in dialogue coverage (VID-26).
#
# Every check below is conditional on a declaration the creator wrote — a
# `派生自` line, a `尺度` line, an accepted production profile, a 交付分组
# section, the `--dialogue-coverage` switch — so a document that predates them
# validates exactly as before.
# ---------------------------------------------------------------------------

DERIVATION_LINE_RE = re.compile(
    r"^[ \t　]*[-*+][ \t　]*派生自[：:].*$", re.MULTILINE
)
DERIVATION_RE = re.compile(
    r"^[ \t　]*[-*+][ \t　]*派生自：((?:人物「[^」\n]+」[、,，]?)+)"
    r"（继承：([^；）\n]+)；不继承：([^）\n]+)）。?$"
)
DERIVATION_NAME_RE = re.compile(r"人物「([^」\n]+)」")
DERIVATION_KIND_RE = re.compile(
    r"^[ \t　]*[-*+][ \t　]*派生关系[：:](.+)$", re.MULTILINE
)
DERIVATION_KINDS = ("血缘子女", "血缘同辈", "年龄阶段", "变异形态", "双胞胎/克隆", "宿主与变身")
SCALE_LINE_RE = re.compile(r"^[ \t　]*[-*+][ \t　]*尺度[：:](.+)$", re.MULTILINE)
SCALE_PHRASES = {
    "手持级": ("handheld scale", "手持级"),
    "桌面级": ("tabletop scale", "桌面级"),
    "家具级": ("furniture scale", "家具级"),
}
DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*s$")
DURATION_PENDING = "待定"
GROUP_SECTION_MARK = "\n## 交付分组"
GROUP_HEADING_RE = re.compile(r"^### (GROUP-[A-Z0-9-]+)\b", re.MULTILINE)
OMISSION_RE = re.compile(r"^[ \t　]*[-*+][ \t　]*省略：「([^」\n]+)」", re.MULTILINE)
SPEECH_TAG_RE = re.compile(r"^\[(?:VO|OS)\]\s*[^：\n]+：(.+)$")
DIALOGUE_LINE_RE = re.compile(r"^([^\[\s：，。！？；、]{1,12})(?:（[^）]*）)?：(.+)$")
NON_SPEECH_PREFIXES = ("#", ">", "[画面文字]", "[SFX]", "[连续性]", "[转场]")
SIMILARITY_WARN_DEFAULT = 0.75


class Derivation(NamedTuple):
    """One `派生自` declaration: who inherits what from whom."""

    name: str
    upstream: list[str]
    inherited: list[str]
    kind: Optional[str]


class DeliveryGroup(NamedTuple):
    """One multi-shot container declared under `## 交付分组`."""

    group_id: str
    members: list[str]
    duration: Optional[float]


def _entry_bodies(document: str) -> dict[tuple[str, str], str]:
    """Body text of every `视觉设定.md` entry, keyed like ``VisualEntry.key``."""
    headings = list(VISUAL_SETTING_HEADING_RE.finditer(document))
    bodies: dict[tuple[str, str], str] = {}
    for index, heading in enumerate(headings):
        end = (
            headings[index + 1].start()
            if index + 1 < len(headings)
            else len(document)
        )
        key = (heading.group(1), heading.group(2).strip())
        bodies.setdefault(key, document[heading.end() : end])
    return bodies


def _derivations(
    document: str, entries: list[VisualEntry], errors: list[str]
) -> list[Derivation]:
    """Parse every `派生自` declaration and resolve its upstream names."""
    known = {entry.name for entry in entries if entry.category == "人物"}
    result: list[Derivation] = []
    for (category, name), body in _entry_bodies(document).items():
        lines = DERIVATION_LINE_RE.findall(body)
        if not lines:
            continue
        if category != "人物":
            errors.append(
                f"视觉设定.md: {category}「{name}」写了派生自，派生自只能写在人物条目里"
            )
            continue
        if len(lines) > 1:
            errors.append(f"视觉设定.md: 人物「{name}」的派生自只能写一行")
            continue
        match = DERIVATION_RE.match(lines[0])
        if match is None:
            errors.append(
                f"视觉设定.md: 人物「{name}」的派生自必须写成 "
                "`派生自：人物「…」（继承：…；不继承：…）`: " + _excerpt(lines[0])
            )
            continue
        upstream = _unique(
            item.strip() for item in DERIVATION_NAME_RE.findall(match.group(1))
        )
        for parent in upstream:
            if parent not in known:
                errors.append(
                    f"视觉设定.md: 人物「{name}」的派生自指向不存在的人物条目: 人物「{parent}」"
                )
        if name in upstream:
            errors.append(f"视觉设定.md: 人物「{name}」不能派生自自己")
        inherited = [
            item.strip() for item in re.split(r"[、,，]", match.group(2)) if item.strip()
        ]
        excluded = [
            item.strip() for item in re.split(r"[、,，]", match.group(3)) if item.strip()
        ]
        if not inherited or not excluded:
            errors.append(f"视觉设定.md: 人物「{name}」的派生自必须同时写继承项与不继承项")
        kind: Optional[str] = None
        kinds = DERIVATION_KIND_RE.findall(body)
        if kinds:
            kind = _plain(kinds[0])
            if kind not in DERIVATION_KINDS:
                errors.append(
                    f"视觉设定.md: 人物「{name}」的派生关系只能是"
                    f"{'、'.join(DERIVATION_KINDS)}之一"
                )
        result.append(Derivation(name, upstream, inherited, kind))
    return result


def _check_derivation_cycles(derivations: list[Derivation], errors: list[str]) -> None:
    graph = {item.name: item.upstream for item in derivations}
    reported: set[frozenset[str]] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in trail:
            cycle = trail[trail.index(node) :] + [node]
            key = frozenset(cycle)
            if key not in reported:
                reported.add(key)
                errors.append("视觉设定.md: 派生关系成环: " + " → ".join(cycle))
            return
        for parent in graph.get(node, []):
            visit(parent, trail + [node])

    for name in graph:
        visit(name, [])


def _identity_labels(value: str) -> list[str]:
    """Chinese labels of the `用途：身份` slots in one reference declaration."""
    return [
        match.group(4).strip()
        for match in REF_RE.finditer(value)
        if (match.group(5) or "").strip() == "身份"
    ]


def _check_derivation_readiness(
    derivations: list[Derivation],
    shot_fields: dict[str, dict[str, str]],
    image_reference_values: list[str],
    errors: list[str],
) -> None:
    """A derived entry is bound as identity only after its upstream has an identity picture.

    Which picture belongs to whom is read from the slot's Chinese label: a
    label that contains the entry name is that entry's picture. This is the
    same convention the storyboard uses when it names 《江晨定妆照》.
    """
    episode_labels: list[str] = []
    for value in image_reference_values:
        episode_labels.extend(_identity_labels(value))
    per_shot = {
        shot_id: _identity_labels(fields.get("输入参考图", ""))
        for shot_id, fields in shot_fields.items()
    }
    for labels in per_shot.values():
        episode_labels.extend(labels)
    for item in derivations:
        for shot_id, labels in per_shot.items():
            if not any(item.name in label for label in labels):
                continue
            for parent in item.upstream:
                if not any(parent in label for label in episode_labels):
                    errors.append(
                        f"{shot_id}: 派生上游未定稿：人物「{item.name}」绑定了身份图，"
                        f"但上游人物「{parent}」在本集没有 用途：身份 的 REF"
                    )


def _project_document(project_root: Path) -> dict:
    configuration = project_root / "short-drama.json"
    if not configuration.is_file():
        return {}
    try:
        project = json.loads(configuration.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return project if isinstance(project, dict) else {}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _target_seconds(project: dict) -> Optional[float]:
    formats = project.get("format")
    value = formats.get("target_seconds_per_episode") if isinstance(formats, dict) else None
    return float(value) if _is_number(value) else None


def _accepted_choices(project: dict) -> dict:
    authority = project.get("creator_authority")
    profile = (
        authority.get("production_profile") if isinstance(authority, dict) else None
    )
    if (
        isinstance(profile, dict)
        and profile.get("status") == "accepted"
        and isinstance(profile.get("choices"), dict)
    ):
        return profile["choices"]
    return {}


def _native_range(choices: dict) -> Optional[tuple[float, float]]:
    declared = choices.get("native_duration_seconds")
    if isinstance(declared, dict):
        low, high = declared.get("min"), declared.get("max")
        if _is_number(low) and _is_number(high) and low <= high:
            return float(low), float(high)
    return None


def _similarity_threshold(project: dict) -> float:
    formats = project.get("format")
    value = formats.get("identity_sheet_similarity_warn") if isinstance(formats, dict) else None
    if _is_number(value) and 0 < value <= 1:
        return float(value)
    return SIMILARITY_WARN_DEFAULT


def _shot_duration(
    fields: dict[str, str], owner: str, errors: list[str]
) -> tuple[Optional[float], bool]:
    """(seconds, pending). A missing or unparsable duration is reported; 待定 is not."""
    raw = fields.get("时长", "")
    if not raw:
        errors.append(f"{owner}: 缺少时长字段")
        return None, False
    plain = _plain(raw)
    if plain == DURATION_PENDING:
        return None, True
    match = DURATION_RE.match(plain)
    if match is None:
        errors.append(f"{owner}: 时长必须写成 Ns（如 4.5s）或 待定: {_excerpt(raw)}")
        return None, False
    return float(match.group(1)), False


def _delivery_groups(
    text: str,
    motion_by_shot: dict[str, tuple[str, str, Optional[str]]],
    shot_order: list[str],
    errors: list[str],
) -> list[DeliveryGroup]:
    """Parse `## 交付分组`: members resolve, stay contiguous, and belong to one group."""
    groups: list[DeliveryGroup] = []
    if not text.strip():
        return groups
    matches = list(GROUP_HEADING_RE.finditer(text))
    if not matches:
        errors.append("视频提示词.md: 交付分组章节没有 `### GROUP-...` 条目")
        return groups
    shot_of_motion = {
        motion_id: shot_id for shot_id, (motion_id, _, _) in motion_by_shot.items()
    }
    claimed: dict[str, str] = {}
    seen: set[str] = set()
    for index, match in enumerate(matches):
        group_id = match.group(1)
        body = text[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else None
        ]
        if group_id in seen:
            errors.append(f"{group_id}: 交付分组 ID 重复")
            continue
        seen.add(group_id)
        fields = _fields(body, owner=group_id, errors=errors)
        raw_members = fields.get("成员", "")
        if not raw_members:
            errors.append(f"{group_id}: 缺少成员字段")
            continue
        members: list[str] = []
        for motion_id in (
            item.strip() for item in re.split(r"[、,，]", _plain(raw_members)) if item.strip()
        ):
            shot_id = shot_of_motion.get(motion_id)
            if shot_id is None:
                errors.append(f"{group_id}: 成员不存在: {motion_id}")
                continue
            if shot_id in claimed:
                errors.append(
                    f"{group_id}: {motion_id} 已属于 {claimed[shot_id]}，一个镜头最多进一个交付分组"
                )
            claimed[shot_id] = group_id
            members.append(shot_id)
        positions = [shot_order.index(shot_id) for shot_id in members]
        if positions and positions != list(range(positions[0], positions[0] + len(positions))):
            errors.append(f"{group_id}: 成员必须按来源顺序连续")
        raw_duration = fields.get("容器时长", "")
        duration: Optional[float] = None
        if not raw_duration:
            errors.append(f"{group_id}: 缺少容器时长字段")
        else:
            duration_match = DURATION_RE.match(_plain(raw_duration))
            if duration_match is None:
                errors.append(f"{group_id}: 容器时长必须写成 Ns")
            else:
                duration = float(duration_match.group(1))
        groups.append(DeliveryGroup(group_id, members, duration))
    return groups


def _check_scale_phrases(
    entry_bodies: dict[tuple[str, str], str],
    image_headings: dict[str, str],
    image_prompts: dict[str, Optional[str]],
    errors: list[str],
) -> None:
    for (category, name), body in entry_bodies.items():
        if category != "道具":
            continue
        declared = SCALE_LINE_RE.findall(body)
        if not declared:
            continue
        tier = _plain(declared[0])
        if not tier:
            errors.append(f"视觉设定.md: 道具「{name}」的尺度不能为空")
            continue
        phrases = SCALE_PHRASES.get(tier, (tier,))
        for image_id, label in image_headings.items():
            if name not in label:
                continue
            prompt = image_prompts.get(image_id)
            if prompt is None:
                continue
            haystack = _normalized(prompt)
            if not any(_normalized(phrase) in haystack for phrase in phrases):
                errors.append(
                    f"{image_id}: 道具「{name}」声明尺度 {tier}，可复制提示词缺少尺度短语"
                    f"（{' / '.join(phrases)}）"
                )


def _token_set(text: str) -> set[str]:
    folded = text.casefold()
    tokens = set(re.findall(r"[a-z0-9]{3,}", folded))
    for run in re.findall(r"[㐀-鿿]{2,}", folded):
        tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _check_identity_similarity(
    entries: list[VisualEntry],
    image_headings: dict[str, str],
    image_prompts: dict[str, Optional[str]],
    threshold: float,
    notes: list[str],
) -> None:
    """Two identity sheets that differ only by identifiers are a template (IMG-17)."""
    sheets: list[tuple[str, str, set[str]]] = []
    for entry in entries:
        if entry.category != "人物":
            continue
        for image_id, label in image_headings.items():
            prompt = image_prompts.get(image_id)
            if entry.name in label and prompt:
                sheets.append((image_id, entry.name, _token_set(prompt)))
    for first in range(len(sheets)):
        for second in range(first + 1, len(sheets)):
            left, right = sheets[first], sheets[second]
            if left[1] == right[1] or not left[2] or not right[2]:
                continue
            jaccard = len(left[2] & right[2]) / len(left[2] | right[2])
            if jaccard >= threshold:
                notes.append(
                    f"WARN {left[0]} 与 {right[0]} 的可复制正文词级相似度 {jaccard:.2f} ≥ "
                    f"{threshold:.2f}，两条身份板可能只差标识符（IMG-17）"
                )


def _squash(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _screenplay_speech(screenplay: str) -> list[str]:
    """Every dialogue, VO and OS line of `剧本.md`, text only."""
    lines: list[str] = []
    for raw in screenplay.splitlines():
        line = raw.strip()
        if not line or line.startswith(NON_SPEECH_PREFIXES):
            continue
        tagged = SPEECH_TAG_RE.match(line)
        if tagged is not None:
            lines.append(tagged.group(1).strip())
            continue
        if line.startswith("["):
            continue
        spoken = DIALOGUE_LINE_RE.match(line)
        if spoken is not None:
            lines.append(spoken.group(2).strip())
    return lines


def _check_dialogue_coverage(
    screenplay: str,
    storyboard: str,
    shot_fields: dict[str, dict[str, str]],
    motion_by_shot: dict[str, tuple[str, str, Optional[str]]],
    errors: list[str],
) -> None:
    carriers: list[str] = [
        prompt for _, (_, _, prompt) in motion_by_shot.items() if prompt
    ]
    carriers.extend(fields.get("声音", "") for fields in shot_fields.values())
    carriers.extend(OMISSION_RE.findall(storyboard))
    haystack = _squash("\n".join(carriers))
    for line in _screenplay_speech(screenplay):
        needle = _squash(line)
        alternatives = {needle, needle.rstrip("。！？，…")}
        if not any(alternative and alternative in haystack for alternative in alternatives):
            errors.append(
                f"剧本.md: 对白「{_excerpt(line, 30)}」未被任何视频正文或分镜声音字段承载，"
                "也未在「省略的对白」显式省略（VID-26）"
            )


def validate_episode_report(
    episode: Path,
    project_root: Optional[Path] = None,
    *,
    dialogue_coverage: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (deterministic contract errors, informational notes) for ``episode``."""
    episode = episode.resolve()
    project_root = (project_root or episode.parent.parent).resolve()
    errors: list[str] = []
    notes: list[str] = []
    missing = [name for name in REQUIRED_DOCUMENTS if not (episode / name).is_file()]
    if missing:
        return [f"缺少创作文档: {', '.join(missing)}"], []

    images = (episode / "图片提示词.md").read_text(encoding="utf-8")
    storyboard = (episode / "分镜.md").read_text(encoding="utf-8")
    video_document = (episode / "视频提示词.md").read_text(encoding="utf-8")
    # A delivery-group section is not a MOTION entry; cut it off before the
    # section parser would fold it into the last MOTION's body.
    video, _, group_text = video_document.partition(GROUP_SECTION_MARK)
    visual = (episode / "视觉设定.md").read_text(encoding="utf-8")
    screenplay = (episode / "剧本.md").read_text(encoding="utf-8")
    locks = _continuity_locks(visual, errors)
    visual_entries = _visual_entries(visual, errors)
    other_headings = {
        match.group(2).strip(): match.group(1).strip()
        for match in OTHER_SETTING_HEADING_RE.finditer(visual)
        if match.group(1).strip() not in VISUAL_CATEGORIES
    }
    image_pairs = re.findall(r"^## (IMG-[A-Z0-9-]+) · (.+)$", images, re.MULTILINE)
    image_headings = dict(image_pairs)
    all_image_headings = re.findall(r"^## (IMG-[A-Z0-9-]+)\b", images, re.MULTILINE)
    if len(image_pairs) != len(all_image_headings):
        errors.append("图片提示词.md: IMG 标题必须包含中文名称")
    if len(image_pairs) != len(image_headings):
        errors.append("图片提示词.md: IMG 标题 ID 重复")
    for image_id, label in image_pairs:
        if not re.search(r"[\u3400-\u9fff]", label):
            errors.append(f"{image_id}: IMG 标题缺少中文名称")
    image_matches = list(re.finditer(r"^## (IMG-[A-Z0-9-]+)\b", images, re.MULTILINE))
    image_prompts: dict[str, Optional[str]] = {}
    image_reference_values: list[str] = []
    for index, match in enumerate(image_matches):
        body = images[
            match.start() : image_matches[index + 1].start()
            if index + 1 < len(image_matches)
            else None
        ]
        reference_value = _fields(body, owner=match.group(1), errors=errors).get(
            "参考", ""
        )
        image_reference_values.append(reference_value)
        if not reference_value:
            errors.append(f"{match.group(1)}: 缺少参考字段")
        elif _is_no_external_reference(reference_value):
            pass
        elif "REF-" in reference_value:
            _references(reference_value, match.group(1), project_root, errors)
        else:
            errors.append(
                f"{match.group(1)}: 参考必须声明无外部参考或使用完整 REF 语法"
            )
        image_prompt = _copyable_prompt(body)
        image_prompts[match.group(1)] = image_prompt
        if image_prompt is None:
            errors.append(f"{match.group(1)}: 缺少唯一且非空的可复制提示词")

    shots = _sections(storyboard, "SHOT")
    motions = _sections(video, "MOTION")
    shot_ids = re.findall(r"^## (SHOT-[A-Z0-9-]+)\b", storyboard, re.MULTILINE)
    motion_ids = re.findall(r"^## (MOTION-[A-Z0-9-]+)\b", video, re.MULTILINE)
    if len(shot_ids) != len(set(shot_ids)):
        errors.append("分镜.md: SHOT 标题 ID 重复")
    if len(motion_ids) != len(set(motion_ids)):
        errors.append("视频提示词.md: MOTION 标题 ID 重复")
    named_shots = re.findall(
        r"^## (SHOT-[A-Z0-9-]+) · ([^\n]+)$", storyboard, re.MULTILINE
    )
    named_motions = re.findall(
        r"^## (MOTION-[A-Z0-9-]+) · ([^\n]+)$", video, re.MULTILINE
    )
    if len(named_shots) != len(shot_ids):
        errors.append("分镜.md: SHOT 标题必须包含中文名称")
    if len(named_motions) != len(motion_ids):
        errors.append("视频提示词.md: MOTION 标题必须包含中文名称")
    for shot_id, label in named_shots:
        if not re.search(r"[\u3400-\u9fff]", label):
            errors.append(f"{shot_id}: SHOT 标题缺少中文名称")
    for motion_id, label in named_motions:
        if not re.search(r"[\u3400-\u9fff]", label):
            errors.append(f"{motion_id}: MOTION 标题缺少中文名称")
    if not shots:
        errors.append("分镜.md: 没有 SHOT 条目")
    if not motions:
        errors.append("视频提示词.md: 没有 MOTION 条目")

    motion_by_shot: dict[str, tuple[str, str, Optional[str]]] = {}
    shot_fields: dict[str, dict[str, str]] = {}
    motion_field_map: dict[str, dict[str, str]] = {}
    for motion_id, body in motions.items():
        fields = _fields(body, owner=motion_id, errors=errors)
        shot_id = _plain(fields.get("分镜", ""))
        copyable_prompt = _copyable_prompt(body)
        if not shot_id:
            errors.append(f"{motion_id}: 缺少分镜字段")
        elif shot_id in motion_by_shot:
            errors.append(f"{motion_id}: 分镜 {shot_id} 被多个 MOTION 引用")
        else:
            motion_by_shot[shot_id] = (motion_id, body, copyable_prompt)
        if motion_id.removeprefix("MOTION-") != shot_id.removeprefix("SHOT-"):
            errors.append(f"{motion_id}: ID 必须与分镜 {shot_id} 一一对应")
        if copyable_prompt is None:
            errors.append(f"{motion_id}: 缺少唯一且非空的可复制提示词")

    if set(motion_by_shot) != set(shots):
        errors.append("分镜.md/视频提示词.md: SHOT 与 MOTION 未一一对应")

    for shot_id, shot_body in shots.items():
        fields = _fields(shot_body, owner=shot_id, errors=errors)
        shot_fields[shot_id] = fields
        image_value = fields.get("图片提示词项", "")
        if not image_value:
            errors.append(f"{shot_id}: 缺少图片提示词项字段")
        image_refs = IMG_RE.findall(image_value)
        image_remainder = IMG_RE.sub("", image_value).strip("；。 ")
        if not _is_none(image_value) and (
            len(image_refs) != len(re.findall(r"\bIMG-[A-Z0-9-]+\b", image_value))
            or image_remainder
        ):
            errors.append(f"{shot_id}: 图片提示词项语法不完整")
        for image_id, label, _ in image_refs:
            if image_id not in image_headings:
                errors.append(f"{shot_id}: IMG 标题不存在: {image_id}")
            elif label != image_headings[image_id]:
                errors.append(f"{shot_id}: IMG 中文名称与标题不一致: {image_id}")

        shot_input = fields.get("输入参考图", "")
        if not shot_input:
            errors.append(f"{shot_id}: 缺少输入参考图字段")
        _references(shot_input, shot_id, project_root, errors)

        basis_value = fields.get("视觉依据", "")
        if not basis_value:
            errors.append(f"{shot_id}: 缺少视觉依据字段")
            basis = VisualBasis(False, set(), set())
        else:
            basis = _visual_basis(
                basis_value, shot_id, visual_entries, other_headings, errors
            )
        # The keyframe is the only place the frame's contents exist as text, so a
        # shot without one would make the coverage check below vacuous.
        keyframe = _copyable_prompt(shot_body, heading=r"冻结关键帧提示词")
        if keyframe is None:
            errors.append(f"{shot_id}: 缺少唯一且非空的冻结关键帧提示词")
        elif basis.parsed:
            _check_named_coverage(
                keyframe, shot_id, "冻结关键帧提示词", basis, visual_entries, errors
            )

        motion = motion_by_shot.get(shot_id)
        if not motion:
            continue
        motion_id, motion_body, copyable_prompt = motion
        motion_fields = _fields(motion_body, owner=motion_id, errors=errors)
        motion_field_map[motion_id] = motion_fields
        motion_input = motion_fields.get("输入参考图", "")
        _references(motion_input, motion_id, project_root, errors)
        if _plain(motion_input) != _plain(shot_input):
            errors.append(f"{motion_id}: 输入参考图与 {shot_id} 不一致")

        if _has_pending_references(shot_input):
            errors.append(f"{motion_id}: 仍有待补参考图，不能生成最终视频提示词")

        has_real_image = not _is_none(shot_input)
        expected_mode = "图生视频" if has_real_image else "文生视频"
        if _plain(motion_fields.get("生成方式", "")) != expected_mode:
            errors.append(f"{motion_id}: 生成方式应为{expected_mode}")
        if not has_real_image:
            if not _is_explicit_text_to_video(shot_input):
                errors.append(
                    f"{motion_id}: 无真实输入参考图时不能静默降级为文生视频；"
                    "请先绑定已有图片、列出待补图片，或记录创作者已明确选择文生视频"
                )
            anchor = _plain(motion_fields.get("静态视觉锚点", ""))
            if not anchor or anchor == "无":
                errors.append(f"{motion_id}: 文生视频缺少静态视觉锚点")
            if (
                copyable_prompt is not None
                and anchor
                and anchor != "无"
                and anchor not in copyable_prompt
            ):
                errors.append(f"{motion_id}: 可复制提示词没有包含静态视觉锚点")
            # In text-to-video the anchor carries the appearance the keyframe
            # would otherwise have carried, so it is the same claim about the
            # same frame and answers to the same visual basis. The rest of the
            # motion body is not checked: it may legitimately name an offscreen
            # speaker, which SHT-22 excludes.
            if anchor and anchor != "无" and basis.parsed:
                _check_named_coverage(
                    anchor, motion_id, "静态视觉锚点", basis, visual_entries, errors
                )

    _check_language_designators(
        project_root, entries=visual_entries, errors=errors
    )
    _check_continuity_locks(
        locks,
        shots=shots,
        motion_by_shot=motion_by_shot,
        image_prompts=image_prompts,
        errors=errors,
    )

    # Derivation: resolve, no cycles, upstream identity picture before binding.
    entry_bodies = _entry_bodies(visual)
    derivations = _derivations(visual, visual_entries, errors)
    _check_derivation_cycles(derivations, errors)
    _check_derivation_readiness(derivations, shot_fields, image_reference_values, errors)

    # Duration ledger: every shot parses or is explicitly 待定; the episode sum is
    # reported against the declared target, never used as a gate (SHT-16).
    project = _project_document(project_root)
    native_range = _native_range(_accepted_choices(project))
    target = _target_seconds(project)
    shot_durations: dict[str, Optional[float]] = {}
    pending_shots: list[str] = []
    for shot_id, fields in shot_fields.items():
        seconds, pending = _shot_duration(fields, shot_id, errors)
        shot_durations[shot_id] = seconds
        if pending:
            pending_shots.append(shot_id)
        motion = motion_by_shot.get(shot_id)
        if motion is None or seconds is None:
            continue
        motion_seconds, _ = _shot_duration(motion_field_map.get(motion[0], {}), motion[0], [])
        if motion_seconds is not None and abs(motion_seconds - seconds) > 1e-9:
            errors.append(f"{motion[0]}: 时长与 {shot_id} 不一致")

    # Delivery groups: contiguous members, one group per shot, container sum
    # (VID-13 / VID-15); the accepted native range checks the container, not
    # its members (SHT-27).
    groups = _delivery_groups(group_text, motion_by_shot, list(shots), errors)
    grouped_shots: set[str] = set()
    for group in groups:
        grouped_shots.update(group.members)
        member_durations = [shot_durations.get(shot_id) for shot_id in group.members]
        if not group.members:
            continue
        if any(value is None for value in member_durations):
            notes.append(f"INFO {group.group_id} 有成员时长待定，容器算术挂起")
            continue
        total = sum(value for value in member_durations if value is not None)
        if group.duration is None:
            continue
        if abs(total - group.duration) > 1e-6:
            errors.append(
                f"{group.group_id}: 容器时长 {group.duration:g}s 不等于成员时长之和 {total:g}s"
            )
        elif native_range is not None and not (native_range[0] <= total <= native_range[1]):
            errors.append(
                f"{group.group_id}: 容器时长 {total:g}s 不在已接受档案的原生区间 "
                f"[{native_range[0]:g}, {native_range[1]:g}] 内（SHT-27）"
            )
    if native_range is not None:
        for shot_id, seconds in shot_durations.items():
            if seconds is None or shot_id in grouped_shots:
                continue
            if not (native_range[0] <= seconds <= native_range[1]):
                errors.append(
                    f"{shot_id}: 时长 {seconds:g}s 不在已接受档案的原生区间 "
                    f"[{native_range[0]:g}, {native_range[1]:g}] 内（SHT-27）"
                )
    if shot_durations:
        total_seconds = sum(value for value in shot_durations.values() if value is not None)
        ledger = f"INFO 本集 {len(shot_durations)} 镜时长合计 {total_seconds:g}s"
        if pending_shots:
            ledger += f"，{len(pending_shots)} 镜待定（{'、'.join(pending_shots)}）"
        if target is not None:
            ledger += f"；目标 {target:g}s，差 {total_seconds - target:+g}s"
        notes.append(ledger)

    _check_scale_phrases(entry_bodies, image_headings, image_prompts, errors)
    _check_identity_similarity(
        visual_entries, image_headings, image_prompts, _similarity_threshold(project), notes
    )
    if dialogue_coverage:
        _check_dialogue_coverage(screenplay, storyboard, shot_fields, motion_by_shot, errors)
    return errors, notes


def validate_episode(
    episode: Path,
    project_root: Optional[Path] = None,
    *,
    dialogue_coverage: bool = False,
) -> list[str]:
    """Return all deterministic contract errors for ``episode``."""
    return validate_episode_report(
        episode, project_root, dialogue_coverage=dialogue_coverage
    )[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path, help="包含五份 Markdown 的剧集目录")
    parser.add_argument("--project-root", type=Path, help="用于解析 REF 项目相对路径")
    parser.add_argument(
        "--dialogue-coverage",
        action="store_true",
        help="按 VID-26 核对剧本每句对白是否被视频正文或分镜声音字段逐字承载",
    )
    args = parser.parse_args()
    # 诊断与剧集路径都是中文。stdout 重定向时 Windows 用 ANSI 代码页，默认的
    # strict 处理器会在打印这一步抛错；stderr 早就是 backslashreplace，这里让
    # stdout 用同一个处理器：能编码就照常显示中文，不能编码才退成转义。
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")
    errors, notes = validate_episode_report(
        args.episode, args.project_root, dialogue_coverage=args.dialogue_coverage
    )
    # The verdict line stays first so callers that read only the first line keep
    # working; the ledger and warnings follow it.
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
    else:
        print(f"OK: {args.episode}")
    for note in notes:
        print(note)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
