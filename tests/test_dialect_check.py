"""`VID-25`: dialect tokens are derived, so they are compared, not read.

A `<Picture 3>` where only two pictures are bound, a `[Shot 2] At 00:05.000,` in a
container whose first member runs six seconds, a `镜头 2 [0:06–0:12]` that does not
end at the accepted duration — every one of these is accepted by the provider and
renders the wrong thing. None of them needs a reading of the drama.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SUITE = Path(__file__).resolve().parents[1]
SCRIPT = SUITE / "skills/short-drama-video-prompts/scripts/dialect_check.py"
SPEC = importlib.util.spec_from_file_location("short_drama_dialect_check", SCRIPT)
assert SPEC and SPEC.loader
dialect_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect_check)


SCREENPLAY = """# EP001 · 号牌

## EP001-SC001 内 · 渡站值班室 · 夜

顾禾把铁皮匣推到柜台中央。

魏叔（不看她）：你找的东西不在里面。

[VO] 顾禾：他知道我会来。
"""

VISUAL = """# EP001 视觉设定

## 人物 · 顾禾

- 识别锚点：窄长脸，左眉尾短缺口，自然卷黑发。
"""

IMAGES = """# EP001 图片提示词

## IMG-GUHE-SHEET · 顾禾角色板

- 用途：锁定身份。
- 参考：无外部参考。

### 可复制提示词
> 顾禾角色板正文。
"""

REFERENCES = (
    "REF-SHOT001-START（顺序：1）· 输入/起始帧.png《SHOT-EP001-001 起始帧》"
    "（用途：起始帧；控制：起始构图；不得控制：终态）；"
    "REF-GUHE-SHEET（顺序：2）· 输入/顾禾定妆.png《顾禾定妆照》"
    "（用途：身份；控制：脸型；不得控制：构图、动作）"
)

STORYBOARD = f"""# EP001 分镜

## SHOT-EP001-001 · 推匣

- 来源：EP001-SC001
- 时长：6s
- 目的：把匣子推到两人之间。
- 图片提示词项：无
- 输入参考图：{REFERENCES}
- 视觉依据：《视觉设定.md》·人物「顾禾」（控制：身份）。

### 冻结关键帧提示词
> 顾禾站在柜台内侧，双手按在铁皮匣上。

## SHOT-EP001-002 · 不看她

- 来源：EP001-SC001
- 时长：4s
- 目的：魏叔拒绝抬眼。
- 图片提示词项：无
- 输入参考图：无（创作者已明确选择文生视频）。
- 视觉依据：无

### 冻结关键帧提示词
> 魏叔低头擦着号牌。
"""

H3_FULL = (
    "subject_definitions: <Subject 1> is the woman in <Picture 2>.\n"
    "summary: She pushes the tin case to the middle of the counter.\n"
    "retention_analysis: <Picture 1> (appears in [Shot 1]): fully_preserved - opening framing.\n"
    "detailed_description: [Shot 1] She pushes the case forward and waits.\n"
    "overall_soundscape: room tone, tin scraping on wood.\n"
    "non_diegetic_music: N/A"
)

H3_BASE = (
    "integrated_multimodal_description: [Shot 1] An old man keeps polishing a badge "
    "and (S1) says in an off-screen voiceover <d>[Chinese] 你找的东西不在里面。</d> "
    "while his lips remain completely closed.\n"
    "overall_soundscape: cloth on porcelain.\n"
    "non_diegetic_music: N/A"
)

H3_GROUP = (
    "integrated_multimodal_description:\n"
    "[Shot 1] She pushes the case forward.\n"
    "[Shot 2] At 00:06.000, the camera cuts to the old man polishing the badge; "
    "(S1) says <d>[Chinese] 你找的东西不在里面。</d>\n"
    "overall_soundscape: room tone.\n"
    "non_diegetic_music: N/A"
)


def quote(prompt: str) -> str:
    """A copyable prompt is one Markdown quote block: every non-empty line carries `>`."""
    return "\n".join(f"> {line}" for line in prompt.split("\n"))


def video_document(first: str, second: str, group: str | None = H3_GROUP) -> str:
    first, second = quote(first), quote(second)
    if group is not None:
        group = quote(group)
    text = f"""# EP001 视频提示词

## MOTION-EP001-001 · 推匣

- 分镜：SHOT-EP001-001
- 时长：6s
- 生成方式：图生视频
- 输入参考图：{REFERENCES}

### 可复制提示词
{first}

## MOTION-EP001-002 · 不看她

- 分镜：SHOT-EP001-002
- 时长：4s
- 生成方式：文生视频
- 输入参考图：无（创作者已明确选择文生视频）。
- 静态视觉锚点：An old man behind a wooden counter polishes a porcelain badge.

### 可复制提示词
{second}
"""
    if group is not None:
        text += f"""
## 交付分组

### GROUP-EP001-A · 值班室

- 成员：MOTION-EP001-001、MOTION-EP001-002
- 容器时长：10s
- 成员理由：同场、连续、同一绑定链

#### 可复制提示词
{group}
"""
    return text


def profile(dialect: str | None) -> dict:
    document: dict = {"schema_version": "1.0.0-draft", "creator_authority": {}}
    if dialect is not None:
        document["creator_authority"]["production_profile"] = {
            "status": "accepted",
            "choices": {"video_prompt_dialect": dialect},
        }
    return document


def write_project(root: Path, video: str, dialect: str | None = "minimax-h3") -> Path:
    episode = root / "剧集/EP001"
    episode.mkdir(parents=True)
    (episode / "剧本.md").write_text(SCREENPLAY, encoding="utf-8")
    (episode / "视觉设定.md").write_text(VISUAL, encoding="utf-8")
    (episode / "图片提示词.md").write_text(IMAGES, encoding="utf-8")
    (episode / "分镜.md").write_text(STORYBOARD, encoding="utf-8")
    (episode / "视频提示词.md").write_text(video, encoding="utf-8")
    (root / "short-drama.json").write_text(
        json.dumps(profile(dialect), ensure_ascii=False), encoding="utf-8"
    )
    return episode


def codes(findings: list) -> list[str]:
    return [finding.code for finding in findings]


class MiniMaxH3DialectTests(unittest.TestCase):
    def run_check(self, video: str, dialect: str | None = "minimax-h3") -> tuple[list, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = write_project(root, video, dialect)
            return dialect_check.check(episode, root)

    def test_a_reconciled_episode_has_no_findings(self) -> None:
        findings, info = self.run_check(video_document(H3_FULL, H3_BASE))
        self.assertEqual(findings, [], [finding.render() for finding in findings])
        self.assertTrue(any("minimax-h3" in line for line in info), info)

    def test_a_picture_index_beyond_the_bound_slots_is_caught(self) -> None:
        drifted = H3_FULL.replace("<Picture 2>", "<Picture 3>")
        findings, _ = self.run_check(video_document(drifted, H3_BASE))
        self.assertIn("VID_DIALECT_PICTURE_INDEX", codes(findings))

    def test_full_reference_must_cite_the_first_picture(self) -> None:
        drifted = H3_FULL.replace("<Picture 1>", "<Picture 2>")
        findings, _ = self.run_check(video_document(drifted, H3_BASE))
        self.assertIn("VID_DIALECT_PICTURE_INDEX", codes(findings))

    def test_a_missing_field_is_a_field_order_finding(self) -> None:
        drifted = H3_FULL.replace("summary: She pushes the tin case to the middle of the counter.\n", "")
        findings, _ = self.run_check(video_document(drifted, H3_BASE))
        self.assertIn("VID_DIALECT_FIELD_ORDER", codes(findings))

    def test_three_field_mode_is_read_from_the_purpose_combination(self) -> None:
        # The text-to-video shot must not be held to the six-field structure.
        findings, _ = self.run_check(video_document(H3_FULL, H3_BASE, group=None))
        self.assertEqual(findings, [], [finding.render() for finding in findings])

    def test_a_container_cut_mark_that_drifts_from_member_durations_is_caught(self) -> None:
        drifted = H3_GROUP.replace("[Shot 2] At 00:06.000,", "[Shot 2] At 00:05.000,")
        findings, _ = self.run_check(video_document(H3_FULL, H3_BASE, drifted))
        self.assertIn("VID_DIALECT_CUT_TIME", codes(findings))
        self.assertTrue(any("00:06.000" in finding.message for finding in findings))

    def test_a_container_without_its_own_prompt_is_reported(self) -> None:
        video = video_document(H3_FULL, H3_BASE, H3_GROUP).replace(
            "#### 可复制提示词\n" + quote(H3_GROUP), ""
        )
        findings, _ = self.run_check(video)
        self.assertIn("VID_DIALECT_FIELD_ORDER", codes(findings))

    def test_fenced_dialogue_must_be_verbatim_screenplay_text(self) -> None:
        drifted = H3_BASE.replace("你找的东西不在里面。", "你要找的东西不在这里。")
        findings, _ = self.run_check(video_document(H3_FULL, drifted))
        self.assertIn("VID_DIALECT_DIALOGUE_VERBATIM", codes(findings))

    def test_an_unset_profile_is_information_not_a_defect(self) -> None:
        findings, info = self.run_check(video_document(H3_FULL, H3_BASE), dialect=None)
        self.assertEqual(findings, [])
        self.assertTrue(any("VID_DIALECT_PROFILE_UNSET" in line for line in info), info)


SEEDANCE_ONE = "镜头 1 [0:00–0:06]：顾禾把铁皮匣推到柜台中央，{魏叔用中文说：“你找的东西不在里面。”}<声音>铁皮擦过木面"
SEEDANCE_TWO = "镜头 1 [0:00–0:04]：魏叔低头擦号牌，不抬眼。"
SEEDANCE_GROUP = "镜头 1 [0:00–0:06]：顾禾推匣。镜头 2 [0:06–0:10]：魏叔擦号牌，{魏叔用中文说：“你找的东西不在里面。”}"


class SeedanceDialectTests(unittest.TestCase):
    def run_check(self, video: str) -> list:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = write_project(root, video, "seedance-2.5")
            return dialect_check.check(episode, root)[0]

    def test_contiguous_ranges_ending_at_the_accepted_duration_pass(self) -> None:
        findings = self.run_check(video_document(SEEDANCE_ONE, SEEDANCE_TWO, SEEDANCE_GROUP))
        self.assertEqual(findings, [], [finding.render() for finding in findings])

    def test_a_range_that_stops_short_of_the_duration_is_caught(self) -> None:
        findings = self.run_check(
            video_document(SEEDANCE_ONE.replace("[0:00–0:06]", "[0:00–0:05]"), SEEDANCE_TWO, SEEDANCE_GROUP)
        )
        self.assertIn("VID_DIALECT_RANGE", codes(findings))

    def test_a_gap_between_container_ranges_is_caught(self) -> None:
        findings = self.run_check(
            video_document(SEEDANCE_ONE, SEEDANCE_TWO, SEEDANCE_GROUP.replace("[0:06–0:10]", "[0:07–0:10]"))
        )
        self.assertIn("VID_DIALECT_RANGE", codes(findings))

    def test_an_ascii_hyphen_and_millisecond_stamps_are_accepted(self) -> None:
        findings = self.run_check(
            video_document(SEEDANCE_ONE.replace("[0:00–0:06]", "[00:00.000-00:06.000]"), SEEDANCE_TWO, SEEDANCE_GROUP)
        )
        self.assertEqual(findings, [], [finding.render() for finding in findings])

    def test_a_picture_binding_beyond_the_bound_slots_is_caught(self) -> None:
        findings = self.run_check(
            video_document(SEEDANCE_ONE + " 人物 @图片3", SEEDANCE_TWO, SEEDANCE_GROUP)
        )
        self.assertIn("VID_DIALECT_PICTURE_INDEX", codes(findings))

    def test_braced_dialogue_must_be_verbatim(self) -> None:
        findings = self.run_check(
            video_document(SEEDANCE_ONE.replace("你找的东西不在里面。", "东西不在这里。"), SEEDANCE_TWO, SEEDANCE_GROUP)
        )
        self.assertIn("VID_DIALECT_DIALOGUE_VERBATIM", codes(findings))


class DialectCheckCliTests(unittest.TestCase):
    def test_cli_reports_findings_and_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = write_project(root, video_document(H3_FULL, H3_BASE))
            passed = subprocess.run(
                [sys.executable, str(SCRIPT), str(episode), "--project-root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("OK:", passed.stdout)

            (episode / "视频提示词.md").write_text(
                video_document(H3_FULL.replace("<Picture 2>", "<Picture 9>"), H3_BASE),
                encoding="utf-8",
            )
            failed = subprocess.run(
                [sys.executable, str(SCRIPT), str(episode), "--project-root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1)
            self.assertIn("VID_DIALECT_PICTURE_INDEX", failed.stdout)

    def test_cli_dialect_override_works_without_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = write_project(root, video_document(SEEDANCE_ONE, SEEDANCE_TWO, SEEDANCE_GROUP), None)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(episode), "--dialect", "seedance-2.5"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
