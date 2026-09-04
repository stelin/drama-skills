"""The film-merge contract: derivation, duration ledger, delivery groups, scale, dialogue coverage.

Every check here is conditional on a declaration the creator wrote, so the
existing golden episode validates exactly as before; the film example carries
each declaration and must pass with the switches on.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples/creator-first/EP001"
FILM_PROJECT = ROOT / "examples/creator-first-film"
FILM_EPISODE = FILM_PROJECT / "剧集/EP001"
EXPECTED = {"剧本.md", "视觉设定.md", "分镜.md", "图片提示词.md", "视频提示词.md"}
EXPLICIT_TEXT_TO_VIDEO = "无（创作者已明确选择文生视频）。"


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


creator_markdown_check = load(
    "film_creator_markdown_check", "skills/short-drama/scripts/creator_markdown_check.py"
)
dialect_check = load(
    "film_dialect_check", "skills/short-drama-video-prompts/scripts/dialect_check.py"
)


def copy_golden(directory: str) -> tuple[Path, Path]:
    project = Path(directory)
    episode = project / "剧集/EP001"
    shutil.copytree(GOLDEN, episode)
    return project, episode


def rewrite(path: Path, old: str, new: str, count: int = 1) -> None:
    document = path.read_text(encoding="utf-8")
    assert old in document, f"{path.name} lacks {old!r}"
    path.write_text(document.replace(old, new, count), encoding="utf-8")


def append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def errors_of(episode: Path, project: Path, **options: bool) -> list[str]:
    return creator_markdown_check.validate_episode(episode, project, **options)


def report_of(episode: Path, project: Path) -> tuple[list[str], list[str]]:
    return creator_markdown_check.validate_episode_report(episode, project)


def profile(native: tuple[int, int] | None, target: float | None = None) -> str:
    document: dict = {"schema_version": "1.0.0-draft", "format": {}, "creator_authority": {}}
    if target is not None:
        document["format"]["target_seconds_per_episode"] = target
    if native is not None:
        document["creator_authority"]["production_profile"] = {
            "status": "accepted",
            "choices": {"native_duration_seconds": {"min": native[0], "max": native[1]}},
        }
    return json.dumps(document, ensure_ascii=False)


DERIVED_ENTRY = (
    "\n## 人物 · 江小晨\n\n"
    "- 10 岁东亚女孩，长脸，高眉骨。\n"
    "- 识别锚点：长脸、高眉骨、短发。\n"
    "- 画面代称：无\n"
    "- 派生自：人物「江晨」（继承：高眉骨、深眼窝；不继承：年龄、发型、服装、体型）\n"
    "- 派生关系：血缘子女\n"
    "- 派生状态：待上游定稿\n"
)


class DerivationTests(unittest.TestCase):
    def test_a_well_formed_derivation_adds_no_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY)
            self.assertEqual(errors_of(episode, project), [])

    def test_an_unresolved_upstream_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY.replace("人物「江晨」", "人物「不存在的人」"))
            errors = errors_of(episode, project)
            self.assertTrue(
                any("派生自指向不存在的人物条目: 人物「不存在的人」" in error for error in errors),
                errors,
            )

    def test_a_malformed_declaration_is_not_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(
                episode / "视觉设定.md",
                DERIVED_ENTRY.replace(
                    "（继承：高眉骨、深眼窝；不继承：年龄、发型、服装、体型）", "（像父亲）"
                ),
            )
            errors = errors_of(episode, project)
            self.assertTrue(any("派生自必须写成" in error for error in errors), errors)

    def test_a_derivation_cycle_is_caught_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY)
            rewrite(
                episode / "视觉设定.md",
                "- 画面代称：Jiangchen\n",
                "- 画面代称：Jiangchen\n- 派生自：人物「江小晨」（继承：高眉骨、深眼窝；不继承：年龄、发型）\n",
            )
            errors = errors_of(episode, project)
            cycles = [error for error in errors if "派生关系成环" in error]
            self.assertEqual(len(cycles), 1, errors)

    def test_an_unknown_kind_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY.replace("血缘子女", "远房亲戚"))
            errors = errors_of(episode, project)
            self.assertTrue(any("派生关系只能是" in error for error in errors), errors)

    def bind_identity(self, project: Path, episode: Path, labels: list[str]) -> None:
        """Bind identity pictures to SHOT-001 in both documents, as a creator would."""
        slots = []
        for index, label in enumerate(labels, 1):
            picture = project / f"输入/参考图/{label}.png"
            picture.parent.mkdir(parents=True, exist_ok=True)
            picture.write_bytes(b"structural fixture")
            slots.append(
                f"REF-ID-{index}（顺序：{index}）· 输入/参考图/{label}.png《{label}》"
                "（用途：身份；控制：脸型、体态；不得控制：构图、动作、表情）"
            )
        declaration = "；".join(slots)
        for name in ("分镜.md", "视频提示词.md"):
            rewrite(
                episode / name,
                f"- 输入参考图：{EXPLICIT_TEXT_TO_VIDEO}",
                f"- 输入参考图：{declaration}",
            )
        rewrite(episode / "视频提示词.md", "- 生成方式：文生视频", "- 生成方式：图生视频")

    def test_binding_a_derived_identity_before_its_upstream_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY)
            self.bind_identity(project, episode, ["江小晨定妆照"])
            errors = errors_of(episode, project)
            self.assertTrue(
                any(error.startswith("SHOT-EP001-001: 派生上游未定稿") for error in errors), errors
            )

    def test_an_upstream_identity_picture_anywhere_in_the_episode_unlocks_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视觉设定.md", DERIVED_ENTRY)
            self.bind_identity(project, episode, ["江小晨定妆照", "江晨定妆照"])
            errors = errors_of(episode, project)
            self.assertFalse(any("派生上游未定稿" in error for error in errors), errors)


class DurationLedgerTests(unittest.TestCase):
    def test_the_ledger_is_reported_not_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            (project / "short-drama.json").write_text(profile(None, target=40), encoding="utf-8")
            errors, notes = report_of(episode, project)
            self.assertEqual(errors, [])
            ledger = [note for note in notes if note.startswith("INFO 本集")]
            self.assertEqual(len(ledger), 1, notes)
            self.assertIn("合计 50s", ledger[0])
            self.assertIn("目标 40s，差 +10s", ledger[0])

    def test_a_pending_duration_is_suspended_not_zeroed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            rewrite(episode / "分镜.md", "- 时长：5s", "- 时长：待定")
            errors, notes = report_of(episode, project)
            self.assertEqual(errors, [])
            self.assertTrue(any("1 镜待定（SHOT-EP001-001）" in note for note in notes), notes)

    def test_an_unparsable_or_missing_duration_is_caught(self) -> None:
        for label, replacement, expected in (
            ("prose", "- 时长：五秒", "时长必须写成 Ns"),
            ("missing", "- 目的：本镜先", "缺少时长字段"),
        ):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                project, episode = copy_golden(directory)
                if label == "prose":
                    rewrite(episode / "分镜.md", "- 时长：5s", replacement)
                else:
                    rewrite(episode / "分镜.md", "- 时长：5s\n- 目的：先用身体", "- 目的：先用身体")
                errors = errors_of(episode, project)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_a_motion_duration_that_disagrees_with_its_shot_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            rewrite(episode / "视频提示词.md", "- 时长：5s", "- 时长：6s")
            errors = errors_of(episode, project)
            self.assertIn("MOTION-EP001-001: 时长与 SHOT-EP001-001 不一致", errors)

    def test_the_native_range_applies_only_under_an_accepted_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            rewrite(episode / "分镜.md", "- 时长：8s", "- 时长：20s")
            rewrite(episode / "视频提示词.md", "- 时长：8s", "- 时长：20s")
            self.assertEqual(errors_of(episode, project), [])
            (project / "short-drama.json").write_text(profile((4, 15)), encoding="utf-8")
            errors = errors_of(episode, project)
            self.assertTrue(
                any(error.startswith("SHOT-EP001-002: 时长 20s 不在已接受档案的原生区间") for error in errors),
                errors,
            )


GROUP = (
    "\n## 交付分组\n\n### GROUP-EP001-A · 办公室\n\n"
    "- 成员：MOTION-EP001-001、MOTION-EP001-002\n"
    "- 容器时长：13s\n"
    "- 成员理由：同场、连续\n"
)


class DeliveryGroupTests(unittest.TestCase):
    def test_a_correct_group_passes_and_is_not_folded_into_the_last_motion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视频提示词.md", GROUP)
            self.assertEqual(errors_of(episode, project), [])

    def test_a_container_sum_that_is_not_the_member_sum_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视频提示词.md", GROUP.replace("13s", "12s"))
            errors = errors_of(episode, project)
            self.assertIn("GROUP-EP001-A: 容器时长 12s 不等于成员时长之和 13s", errors)

    def test_non_contiguous_members_are_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(
                episode / "视频提示词.md",
                GROUP.replace("MOTION-EP001-002", "MOTION-EP001-003").replace("13s", "10s"),
            )
            errors = errors_of(episode, project)
            self.assertIn("GROUP-EP001-A: 成员必须按来源顺序连续", errors)

    def test_a_shot_in_two_groups_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(
                episode / "视频提示词.md",
                GROUP
                + "\n### GROUP-EP001-B · 重复\n\n- 成员：MOTION-EP001-002、MOTION-EP001-003\n"
                "- 容器时长：13s\n",
            )
            errors = errors_of(episode, project)
            self.assertTrue(
                any("一个镜头最多进一个交付分组" in error for error in errors), errors
            )

    def test_a_group_total_outside_the_native_range_is_caught_instead_of_its_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            append(episode / "视频提示词.md", GROUP)
            (project / "short-drama.json").write_text(profile((4, 12)), encoding="utf-8")
            errors = errors_of(episode, project)
            self.assertTrue(
                any(error.startswith("GROUP-EP001-A: 容器时长 13s 不在") for error in errors), errors
            )
            self.assertFalse(any(error.startswith("SHOT-EP001-002") for error in errors), errors)


PROP_SHEET = (
    "\n## IMG-PHONE-PROP · 江晨手机道具板\n\n- 用途：锁定形制。\n- 参考：无外部参考。\n\n"
    "### 可复制提示词\n> A cracked black slab phone with a dented silver frame, {scale}plain grey background, no hands.\n"
)


class ScaleAndSimilarityTests(unittest.TestCase):
    def test_a_declared_scale_tier_requires_its_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            rewrite(
                episode / "视觉设定.md",
                "- 识别锚点：黑色直板机、两角磕凹银边、右下放射裂纹、冷白等宽字黑底界面。",
                "- 识别锚点：黑色直板机、两角磕凹银边、右下放射裂纹、冷白等宽字黑底界面。\n- 尺度：手持级",
            )
            append(episode / "图片提示词.md", PROP_SHEET.format(scale=""))
            errors = errors_of(episode, project)
            self.assertTrue(
                any(error.startswith("IMG-PHONE-PROP: 道具「江晨手机」声明尺度 手持级") for error in errors),
                errors,
            )
            rewrite(episode / "图片提示词.md", "dented silver frame, plain", "dented silver frame, handheld scale, plain")
            self.assertEqual(errors_of(episode, project), [])

    def test_near_duplicate_identity_sheets_warn_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            images = episode / "图片提示词.md"
            document = images.read_text(encoding="utf-8")
            jiangchen = document.split("## IMG-JIANGCHEN-SHEET", 1)[1].split("## IMG-ZHOUBOSEN-SHEET", 1)[0]
            prompt = jiangchen.split("### 可复制提示词\n", 1)[1].strip()
            zhou_prompt = document.split("## IMG-ZHOUBOSEN-SHEET", 1)[1].split("### 可复制提示词\n", 1)[1].split("\n## ", 1)[0].strip()
            images.write_text(document.replace(zhou_prompt, prompt, 1), encoding="utf-8")
            errors, notes = report_of(episode, project)
            self.assertEqual(errors, [])
            self.assertTrue(any("IMG-17" in note and "WARN" in note for note in notes), notes)


class DialogueCoverageTests(unittest.TestCase):
    def test_coverage_is_off_by_default_and_reports_when_on(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            self.assertEqual(errors_of(episode, project), [])
            errors = errors_of(episode, project, dialogue_coverage=True)
            uncovered = [error for error in errors if "记忆里最后一幕" in error and "VID-26" in error]
            self.assertEqual(len(uncovered), 1, errors)

    def test_an_explicit_omission_before_the_first_shot_covers_a_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, episode = copy_golden(directory)
            rewrite(
                episode / "分镜.md",
                "## SHOT-EP001-001",
                "## 省略的对白\n\n- 省略：「记忆里最后一幕，是病床，和一屋子哭声。」 · 改为后期字幕\n\n## SHOT-EP001-001",
            )
            errors = errors_of(episode, project, dialogue_coverage=True)
            self.assertFalse(any("记忆里最后一幕" in error for error in errors), errors)

    def test_cli_switch_prints_notes_and_still_validates(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "skills/short-drama/scripts/creator_markdown_check.py"),
                str(FILM_EPISODE),
                "--project-root",
                str(FILM_PROJECT),
                "--dialogue-coverage",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("INFO 本集 8 镜时长合计 65s", completed.stdout)
        self.assertIn("OK:", completed.stdout)


class FilmExampleTests(unittest.TestCase):
    def test_the_film_example_exposes_a_project_and_five_documents(self) -> None:
        self.assertTrue((FILM_PROJECT / "short-drama.json").is_file())
        files = {path.name for path in FILM_EPISODE.iterdir() if path.is_file()}
        self.assertEqual(files, EXPECTED)
        self.assertFalse(list(FILM_EPISODE.rglob("*.json")))

    def test_the_film_example_declares_the_film_contract(self) -> None:
        visual = (FILM_EPISODE / "视觉设定.md").read_text(encoding="utf-8")
        self.assertIn("- 观看契约：电影长片", visual)
        self.assertIn("- 派生自：人物「林正国」、人物「周慧」", visual)
        self.assertIn("- 尺度：手持级", visual)
        storyboard = (FILM_EPISODE / "分镜.md").read_text(encoding="utf-8")
        self.assertLess(storyboard.index("## 省略的对白"), storyboard.index("## SHOT-EP001-001"))
        video = (FILM_EPISODE / "视频提示词.md").read_text(encoding="utf-8")
        self.assertIn("## 交付分组", video)
        self.assertIn("#### 可复制提示词", video)

    def test_the_film_example_passes_every_mechanical_check(self) -> None:
        errors, notes = creator_markdown_check.validate_episode_report(
            FILM_EPISODE, FILM_PROJECT, dialogue_coverage=True
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("合计 65s" in note and "目标 65s，差 +0s" in note for note in notes), notes)
        findings, info = dialect_check.check(FILM_EPISODE, FILM_PROJECT)
        self.assertEqual([finding.render() for finding in findings], [])
        self.assertTrue(any("seedance-2.5" in line for line in info), info)

    def test_the_film_example_is_hurt_by_a_drifted_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            shutil.copytree(FILM_PROJECT, project / "film")
            episode = project / "film/剧集/EP001"
            rewrite(episode / "视频提示词.md", "镜头 3 [0:13–0:22]", "镜头 3 [0:14–0:22]")
            findings, _ = dialect_check.check(episode, project / "film")
            self.assertIn("VID_DIALECT_RANGE", [finding.code for finding in findings])


if __name__ == "__main__":
    unittest.main()
