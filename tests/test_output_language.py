import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
SCRIPT = SUITE / "skills/short-drama/scripts/project_tool.py"
SPEC = importlib.util.spec_from_file_location("short_drama_project_tool", SCRIPT)
assert SPEC and SPEC.loader
project_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_tool)

CORE = SUITE / "skills/short-drama"


class LanguageTagTests(unittest.TestCase):
    def test_well_formed_tags_are_accepted_and_trimmed(self) -> None:
        for value, expected in (
            ("zh-CN", "zh-CN"),
            (" en ", "en"),
            ("ko", "ko"),
            ("zh-Hant-TW", "zh-Hant-TW"),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    project_tool.normalize_language_tag(value, field="language"),
                    expected,
                )

    def test_malformed_tag_is_refused_at_init_not_at_use(self) -> None:
        # Nothing downstream re-checks this value, so a bad tag would otherwise
        # propagate into every artifact that claims to follow it.
        for value in ("", "   ", "zh_CN", "中文", "e", "en--US"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    project_tool.normalize_language_tag(value, field="language")


class ProjectLanguageTests(unittest.TestCase):
    def initialize(self, **kwargs: str) -> tuple[Path, dict]:
        directory = tempfile.mkdtemp()
        root = Path(directory) / "project"
        options = {"title": "测试项目", "language": "zh-CN", "aspect_ratio": "9:16"}
        options.update(kwargs)
        result = project_tool.initialize_project(root, suite_root=CORE, **options)
        return root, result["project"]

    def test_defaults_split_creator_language_from_prompt_language(self) -> None:
        _, project = self.initialize()
        self.assertEqual(project["language"], "zh-CN")
        self.assertEqual(project["format"]["prompt_language"], "en")

    def test_prompt_language_can_follow_the_project_language_on_request(self) -> None:
        _, project = self.initialize(prompt_language="zh-CN")
        self.assertEqual(project["format"]["prompt_language"], "zh-CN")
        self.assertEqual(project["language"], "zh-CN")

    def test_creator_language_change_does_not_move_prompt_language(self) -> None:
        # The two fields address different audiences. Writing a project in
        # Korean must not silently change what generators are asked to render.
        _, project = self.initialize(language="ko")
        self.assertEqual(project["language"], "ko")
        self.assertEqual(project["format"]["prompt_language"], "en")

    def test_malformed_language_refuses_initialization(self) -> None:
        for kwargs in ({"language": "zh_CN"}, {"prompt_language": ""}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.initialize(**kwargs)

    def test_status_reports_both_languages_so_skills_stop_guessing(self) -> None:
        root, _ = self.initialize(language="ja", prompt_language="en")
        status = project_tool.project_status(root)
        self.assertEqual(status["language"], "ja")
        self.assertEqual(status["prompt_language"], "en")

    def test_status_falls_back_for_projects_created_before_the_field(self) -> None:
        root, _ = self.initialize()
        project_path = root / project_tool.PROJECT_FILE
        project = json.loads(project_path.read_text(encoding="utf-8"))
        del project["format"]["prompt_language"]
        project_path.write_text(
            json.dumps(project, ensure_ascii=False), encoding="utf-8"
        )

        status = project_tool.project_status(root)
        self.assertEqual(status["prompt_language"], project_tool.DEFAULT_PROMPT_LANGUAGE)


class TemplateTests(unittest.TestCase):
    def test_template_ships_the_documented_default(self) -> None:
        template = json.loads(
            (CORE / "assets/project-template/short-drama.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(template["language"], "zh-CN")
        self.assertEqual(template["format"]["prompt_language"], "en")

    def test_contract_documents_both_fields(self) -> None:
        contract = (CORE / "references/contract-and-ownership.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("#/format/prompt_language", contract)
        self.assertIn("Output language contract", contract)


class VoicePromptOwnershipTests(unittest.TestCase):
    def test_projected_timbre_prompt_has_its_own_owner(self) -> None:
        # Voice identity stays with assets; the copyable prompt projected from
        # it is a separate artifact, so a change to one cannot silently rewrite
        # the other's authority.
        self.assertEqual(
            project_tool._expected_path_owner("设定集/characters.jsonl"),
            "short-drama-assets",
        )
        self.assertEqual(
            project_tool._expected_path_owner("设定集/voice-prompt-specs.jsonl"),
            "short-drama-voice-prompts",
        )
        self.assertEqual(
            project_tool._expected_path_owner("设定集/voice-prompts.md"),
            "short-drama-voice-prompts",
        )


class NovelAnalysisOwnershipTests(unittest.TestCase):
    def test_declared_analysis_artifacts_are_owned(self) -> None:
        for relative in (
            "项目开发/原著分析/_index.json",
            "项目开发/原著分析/分集候选.jsonl",
            "项目开发/原著分析/改编价值.md",
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    project_tool._expected_path_owner(relative),
                    "short-drama-novel-analyze",
                )

    def test_adaptation_contract_still_belongs_to_develop(self) -> None:
        # The analysis layer proposes; only develop may write the contract.
        self.assertEqual(
            project_tool._expected_path_owner("项目开发/adaptation-map.jsonl"),
            "short-drama-develop",
        )

    def test_generated_chapter_files_stay_owner_unconstrained(self) -> None:
        # Per-chapter names are generated, so declaring them is impossible;
        # they follow the same rule as every other undeclared path.
        self.assertIsNone(
            project_tool._expected_path_owner("项目开发/原著分析/章节/第1章-提取.md")
        )


if __name__ == "__main__":
    unittest.main()
