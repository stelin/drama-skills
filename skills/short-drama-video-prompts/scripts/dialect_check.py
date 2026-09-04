#!/usr/bin/env python3
"""Reconcile the fixed structural tokens of `视频提示词.md` with the documents that derive them (`VID-25`).

A dialect prompt carries a few tokens that are not prose: material indices such as
`<Picture 2>` or `@图片2`, container cut marks such as `[Shot 3] At 00:07.000,`, timestamp
ranges such as `镜头 2 [0:06–0:12]`, and fenced dialogue. Every one of them is derived from
another document -- the shot's `输入参考图` order, the accepted member durations, the
screenplay line -- and every one of them fails silently when it drifts: the provider
accepts the request and renders the wrong picture, the wrong cut, the wrong words.

This script reads the accepted dialect from `short-drama.json` (or `--dialect` for a
standalone run) and compares those tokens byte-for-byte. It checks only structures the
dialect reference files spell out; it does not read prose and it never writes.

Exit code 1 when any finding is an error. An unset or unaccepted dialect is reported as
`VID_DIALECT_PROFILE_UNSET` and exits 0: an undeclared profile is not a defect.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

# Creators run these scripts on whatever interpreter their machine provides, so
# an unsupported version must say so instead of failing inside an import.
MINIMUM_PYTHON = (3, 9)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "dialect_check.py requires Python {}.{}, running {}.{}".format(
            *MINIMUM_PYTHON, sys.version_info.major, sys.version_info.minor
        )
    )

REQUIRED_DOCUMENTS = ("剧本.md", "分镜.md", "视频提示词.md")
SECTION_RE = re.compile(r"^## ((?:SHOT|MOTION)-[A-Z0-9-]+)\b", re.MULTILINE)
SCENE_HEADING_RE = re.compile(r"^## (EP\d+-SC\d+)\b", re.MULTILINE)
# The same slot grammar the core validator accepts; only the picture count and the
# purposes are read here.
REF_RE = re.compile(
    r"(REF-[A-Z0-9-]+)（顺序：([1-9]\d*)）· "
    r"([^；\n]+?\.(?:png|jpe?g|webp))《([^》\n]+)》"
    r"（(?:用途：([^；）\n]+)；)?控制：([^；）]+)；不得控制：([^）]+)）",
    re.IGNORECASE,
)
DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*s$")
GROUP_SECTION_MARK = "\n## 交付分组"
GROUP_HEADING_RE = re.compile(r"^### (GROUP-[A-Z0-9-]+)\b", re.MULTILINE)
SUPPORTED_DIALECTS = ("minimax-h3", "seedance-2.5")

H3_THREE_FIELDS = (
    "integrated_multimodal_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
H3_SIX_FIELDS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
H3_PICTURE_RE = re.compile(r"<Picture (\d+)>")
H3_CUT_RE = re.compile(r"\[Shot (\d+)\] At (\d{2}):(\d{2})\.(\d{3}),")
H3_DIALOGUE_RE = re.compile(r"<d>\[[^\]]*\]\s*(.*?)\s*</d>", re.DOTALL)
SEEDANCE_RANGE_RE = re.compile(
    r"镜头\s*(\d+)\s*\[\s*(\d{1,2}:\d{2}(?:\.\d{1,3})?)\s*[–\-—]\s*(\d{1,2}:\d{2}(?:\.\d{1,3})?)\s*\]"
)
SEEDANCE_PICTURE_RE = re.compile(r"@图片(\d+)")
SEEDANCE_DIALOGUE_RE = re.compile(r"\{[^{}]*?说：[“\"](.+?)[”\"]\}", re.DOTALL)
TIME_TOLERANCE = 0.0005


class Finding(NamedTuple):
    code: str
    owner: str
    message: str

    def render(self) -> str:
        return f"ERROR {self.code} {self.owner}: {self.message}"


class CheckError(ValueError):
    pass


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


def _fields(section: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in re.findall(r"^- ([^：\n]+)：(.+)$", section, re.MULTILINE):
        fields.setdefault(key, value)
    return fields


def _plain(value: str) -> str:
    return value.strip().rstrip("。")


def _copyable_prompt(section: str, level: int = 3) -> Optional[str]:
    marker = "#" * level
    markers = list(
        re.finditer(rf"^{marker} 可复制(?:通用)?提示词\s*$", section, re.MULTILINE)
    )
    if len(markers) != 1:
        return None
    body = section[markers[0].end() :]
    following = re.search(r"^#{2,4}\s+", body, re.MULTILINE)
    if following is not None:
        body = body[: following.start()]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines or any(not line.startswith(">") for line in lines):
        return None
    prompt = "\n".join(line[1:].lstrip() for line in lines).strip()
    return prompt or None


def _is_none(value: str) -> bool:
    return "ref-" not in value.casefold() and bool(
        re.fullmatch(r"无(?:（[^）]+）)?", _plain(value))
    )


def _picture_count(value: str) -> int:
    return len(REF_RE.findall(value))


def _purposes(value: str) -> list[str]:
    return [
        (match.group(5) or "").strip() for match in REF_RE.finditer(value)
    ]


def _duration(fields: dict[str, str]) -> Optional[float]:
    match = DURATION_RE.match(_plain(fields.get("时长", "")))
    return float(match.group(1)) if match else None


def _scene_texts(screenplay: str) -> dict[str, str]:
    matches = list(SCENE_HEADING_RE.finditer(screenplay))
    return {
        match.group(1): screenplay[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else None
        ]
        for index, match in enumerate(matches)
    }


def _squash(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _seconds(stamp: str) -> float:
    minutes, seconds = stamp.split(":", 1)
    return int(minutes) * 60 + float(seconds)


def _h3_mark(total: float) -> str:
    minutes = int(total // 60)
    remainder = total - minutes * 60
    return f"{minutes:02d}:{remainder:06.3f}"


class Shot(NamedTuple):
    shot_id: str
    scene: Optional[str]
    duration: Optional[float]
    reference_value: str


class Group(NamedTuple):
    group_id: str
    members: list[str]
    duration: Optional[float]
    prompt: Optional[str]


def _shots(storyboard: str) -> dict[str, Shot]:
    shots: dict[str, Shot] = {}
    for shot_id, body in _sections(storyboard, "SHOT").items():
        fields = _fields(body)
        source = _plain(fields.get("来源", ""))
        shots[shot_id] = Shot(
            shot_id,
            source or None,
            _duration(fields),
            fields.get("输入参考图", ""),
        )
    return shots


def _groups(text: str, shot_of_motion: dict[str, str]) -> list[Group]:
    groups: list[Group] = []
    matches = list(GROUP_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        body = text[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else None
        ]
        fields = _fields(body)
        members = [
            shot_of_motion[item.strip()]
            for item in re.split(r"[、,，]", _plain(fields.get("成员", "")))
            if item.strip() in shot_of_motion
        ]
        duration_match = DURATION_RE.match(_plain(fields.get("容器时长", "")))
        groups.append(
            Group(
                match.group(1),
                members,
                float(duration_match.group(1)) if duration_match else None,
                _copyable_prompt(body, level=4),
            )
        )
    return groups


def _dialect_from_project(project_root: Path) -> tuple[Optional[str], str]:
    configuration = project_root / "short-drama.json"
    if not configuration.is_file():
        return None, "没有 short-drama.json"
    try:
        project = json.loads(configuration.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "short-drama.json 不可读"
    if not isinstance(project, dict):
        return None, "short-drama.json 不是对象"
    authority = project.get("creator_authority")
    profile = (
        authority.get("production_profile") if isinstance(authority, dict) else None
    )
    if not isinstance(profile, dict) or profile.get("status") != "accepted":
        return None, "production_profile 未接受"
    choices = profile.get("choices")
    dialect = choices.get("video_prompt_dialect") if isinstance(choices, dict) else None
    if not isinstance(dialect, str) or not dialect.strip():
        return None, "已接受档案没有声明 video_prompt_dialect"
    return dialect.strip(), ""


def _check_dialogue(
    prompt: str,
    pattern: "re.Pattern[str]",
    owner: str,
    scene_text: str,
    findings: list[Finding],
) -> None:
    haystack = _squash(scene_text)
    for match in pattern.finditer(prompt):
        line = _squash(match.group(1)).strip("“”\"")
        if line and line not in haystack:
            findings.append(
                Finding(
                    "VID_DIALECT_DIALOGUE_VERBATIM",
                    owner,
                    f"围栏内台词在来源场次找不到逐字原文: {match.group(1)[:24]}",
                )
            )


def _check_picture_indices(
    prompt: str,
    pattern: "re.Pattern[str]",
    owner: str,
    picture_count: int,
    findings: list[Finding],
) -> None:
    for raw in pattern.findall(prompt):
        index = int(raw)
        if index < 1 or index > picture_count:
            findings.append(
                Finding(
                    "VID_DIALECT_PICTURE_INDEX",
                    owner,
                    f"引用了第 {index} 张图片，本镜输入参考图只有 {picture_count} 张",
                )
            )


def _check_h3_fields(prompt: str, owner: str, six: bool, findings: list[Finding]) -> None:
    fields = H3_SIX_FIELDS if six else H3_THREE_FIELDS
    positions = [prompt.find(field) for field in fields]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append(
            Finding(
                "VID_DIALECT_FIELD_ORDER",
                owner,
                f"{'六' if six else '三'}段字段缺失或顺序不对: {' '.join(fields)}",
            )
        )
        return
    description_start = positions[3 if six else 0]
    if "[Shot 1]" not in prompt[description_start:]:
        findings.append(
            Finding("VID_DIALECT_FIELD_ORDER", owner, "描述段缺少 [Shot 1]")
        )


def _check_h3_motion(
    motion_id: str,
    prompt: str,
    shot: Shot,
    scene_text: str,
    findings: list[Finding],
) -> None:
    if _is_none(shot.reference_value):
        six = False
        picture_count = 0
    else:
        purposes = _purposes(shot.reference_value)
        six = bool(set(purposes) - {"起始帧", "结束帧"})
        picture_count = _picture_count(shot.reference_value)
    _check_h3_fields(prompt, motion_id, six, findings)
    _check_picture_indices(prompt, H3_PICTURE_RE, motion_id, picture_count, findings)
    if six and "<Picture 1>" not in prompt:
        findings.append(
            Finding(
                "VID_DIALECT_PICTURE_INDEX",
                motion_id,
                "full-reference 正文没有引用 <Picture 1>",
            )
        )
    _check_dialogue(prompt, H3_DIALOGUE_RE, motion_id, scene_text, findings)


def _check_h3_group(
    group: Group, shots: dict[str, Shot], scene_text: str, findings: list[Finding]
) -> None:
    if len(group.members) < 2:
        return
    if group.prompt is None:
        findings.append(
            Finding(
                "VID_DIALECT_FIELD_ORDER",
                group.group_id,
                "多镜容器缺少可复制提示词（#### 可复制提示词）",
            )
        )
        return
    if "[Shot 1]" not in group.prompt:
        findings.append(
            Finding("VID_DIALECT_FIELD_ORDER", group.group_id, "容器正文缺少 [Shot 1]")
        )
    elapsed = 0.0
    for index, shot_id in enumerate(group.members[:-1], 1):
        duration = shots[shot_id].duration
        if duration is None:
            return
        elapsed += duration
        expected = f"[Shot {index + 1}] At {_h3_mark(elapsed)},"
        if expected not in group.prompt:
            findings.append(
                Finding(
                    "VID_DIALECT_CUT_TIME",
                    group.group_id,
                    f"缺少「{expected}」——切点时刻必须等于前 {index} 个成员已接受时长的累计",
                )
            )
    picture_count = max(
        (_picture_count(shots[shot_id].reference_value) for shot_id in group.members),
        default=0,
    )
    _check_picture_indices(
        group.prompt, H3_PICTURE_RE, group.group_id, picture_count, findings
    )
    _check_dialogue(group.prompt, H3_DIALOGUE_RE, group.group_id, scene_text, findings)


def _check_seedance_ranges(
    prompt: str, owner: str, total: Optional[float], findings: list[Finding]
) -> None:
    ranges = SEEDANCE_RANGE_RE.findall(prompt)
    if not ranges:
        return
    previous_end: Optional[float] = None
    for position, (raw_index, raw_start, raw_end) in enumerate(ranges, 1):
        start, end = _seconds(raw_start), _seconds(raw_end)
        if int(raw_index) != position:
            findings.append(
                Finding(
                    "VID_DIALECT_RANGE",
                    owner,
                    f"镜头编号必须从 1 连续递增，第 {position} 段写的是 镜头 {raw_index}",
                )
            )
        if position == 1 and abs(start) > TIME_TOLERANCE:
            findings.append(
                Finding("VID_DIALECT_RANGE", owner, f"首段必须从 0:00 开始，实际 {raw_start}")
            )
        if previous_end is not None and abs(start - previous_end) > TIME_TOLERANCE:
            findings.append(
                Finding(
                    "VID_DIALECT_RANGE",
                    owner,
                    f"镜头 {raw_index} 的起点 {raw_start} 不等于上一段终点",
                )
            )
        if end <= start:
            findings.append(
                Finding("VID_DIALECT_RANGE", owner, f"镜头 {raw_index} 的区间为空或倒置")
            )
        previous_end = end
    if total is not None and previous_end is not None and abs(previous_end - total) > TIME_TOLERANCE:
        findings.append(
            Finding(
                "VID_DIALECT_RANGE",
                owner,
                f"末段终点 {previous_end:g}s 不等于已接受时长 {total:g}s",
            )
        )


def _check_seedance_motion(
    motion_id: str,
    prompt: str,
    shot: Shot,
    scene_text: str,
    findings: list[Finding],
) -> None:
    _check_seedance_ranges(prompt, motion_id, shot.duration, findings)
    picture_count = 0 if _is_none(shot.reference_value) else _picture_count(shot.reference_value)
    _check_picture_indices(prompt, SEEDANCE_PICTURE_RE, motion_id, picture_count, findings)
    _check_dialogue(prompt, SEEDANCE_DIALOGUE_RE, motion_id, scene_text, findings)


def _check_seedance_group(
    group: Group, shots: dict[str, Shot], scene_text: str, findings: list[Finding]
) -> None:
    if group.prompt is None:
        return
    _check_seedance_ranges(group.prompt, group.group_id, group.duration, findings)
    picture_count = max(
        (
            0 if _is_none(shots[shot_id].reference_value) else _picture_count(shots[shot_id].reference_value)
            for shot_id in group.members
        ),
        default=0,
    )
    _check_picture_indices(
        group.prompt, SEEDANCE_PICTURE_RE, group.group_id, picture_count, findings
    )
    _check_dialogue(group.prompt, SEEDANCE_DIALOGUE_RE, group.group_id, scene_text, findings)


def check(
    episode: Path, project_root: Optional[Path] = None, dialect: Optional[str] = None
) -> tuple[list[Finding], list[str]]:
    """Return (error findings, informational lines) for one episode."""
    episode = episode.resolve()
    project_root = (project_root or episode.parent.parent).resolve()
    findings: list[Finding] = []
    info: list[str] = []
    missing = [name for name in REQUIRED_DOCUMENTS if not (episode / name).is_file()]
    if missing:
        raise CheckError(f"缺少创作文档: {', '.join(missing)}")
    if dialect is None:
        dialect, reason = _dialect_from_project(project_root)
        if dialect is None:
            info.append(f"INFO VID_DIALECT_PROFILE_UNSET: {reason}，本次跳过方言结构对账")
            return findings, info
    if dialect not in SUPPORTED_DIALECTS:
        info.append(
            f"INFO VID_DIALECT_PROFILE_UNSET: 方言 {dialect} 没有机械核对规则，本次只跳过"
        )
        return findings, info

    screenplay = (episode / "剧本.md").read_text(encoding="utf-8")
    storyboard = (episode / "分镜.md").read_text(encoding="utf-8")
    video = (episode / "视频提示词.md").read_text(encoding="utf-8")
    scenes = _scene_texts(screenplay)
    shots = _shots(storyboard)
    video_main, _, group_text = video.partition(GROUP_SECTION_MARK)
    motions = _sections(video_main, "MOTION")
    shot_of_motion: dict[str, str] = {}
    for motion_id, body in motions.items():
        shot_id = _plain(_fields(body).get("分镜", ""))
        if shot_id in shots:
            shot_of_motion[motion_id] = shot_id

    def scene_text_for(shot_ids: list[str]) -> str:
        texts = [
            scenes[shots[shot_id].scene]
            for shot_id in shot_ids
            if shots[shot_id].scene in scenes
        ]
        return "\n".join(texts) if texts else screenplay

    for motion_id, body in motions.items():
        prompt = _copyable_prompt(body)
        shot_id = shot_of_motion.get(motion_id)
        if prompt is None or shot_id is None:
            continue
        shot = shots[shot_id]
        text = scene_text_for([shot_id])
        if dialect == "minimax-h3":
            _check_h3_motion(motion_id, prompt, shot, text, findings)
        else:
            _check_seedance_motion(motion_id, prompt, shot, text, findings)

    for group in _groups(group_text, shot_of_motion):
        text = scene_text_for(group.members)
        if dialect == "minimax-h3":
            _check_h3_group(group, shots, text, findings)
        else:
            _check_seedance_group(group, shots, text, findings)
    info.append(
        f"INFO 按 {dialect} 方言核对了 {len(motions)} 条 MOTION 正文"
        + (f"、{len(_groups(group_text, shot_of_motion))} 个交付分组" if group_text else "")
    )
    return findings, info


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("episode", type=Path, help="包含五份 Markdown 的剧集目录")
    parser.add_argument("--project-root", type=Path, help="含 short-drama.json 的项目根目录")
    parser.add_argument(
        "--dialect",
        choices=SUPPORTED_DIALECTS,
        help="没有项目配置时显式指定方言",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")
    try:
        findings, info = check(args.episode, args.project_root, args.dialect)
    except CheckError as exc:
        print(f"ERROR {exc}")
        return 1
    for line in info:
        print(line)
    for finding in findings:
        print(finding.render())
    if findings:
        return 1
    print(f"OK: {args.episode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
