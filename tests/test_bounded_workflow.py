import json
import unittest
from pathlib import Path


SUITE = Path(__file__).resolve().parents[1]
SKILLS = SUITE / "skills"


def read(relative: str) -> str:
    return (SUITE / relative).read_text(encoding="utf-8")


class BoundedWorkflowContractTests(unittest.TestCase):
    def test_end_to_end_preview_runs_one_bounded_work_unit_per_turn(self) -> None:
        workflow = read("skills/short-drama/references/creator-workflow.md")
        router = read("skills/short-drama/references/routing-examples.md")

        for marker in (
            "one bounded work unit per turn",
            "return control to the creator",
            "do not automatically enter the next owner stage, review, or production",
        ):
            self.assertIn(marker, workflow)

        self.assertIn("one bounded work unit", router)
        self.assertIn("never the whole remaining pipeline", router)

    def test_high_fanout_stages_declare_a_batch_boundary_and_stop(self) -> None:
        expected_scopes = {
            "short-drama-write": "scene or scene group",
            "short-drama-assets": "source scene/block range",
            "short-drama-image-prompts": "explicit asset-ID set",
            "short-drama-storyboard": "one scene or contiguous shot range",
            "short-drama-video-prompts": "one scene or contiguous shot range",
        }

        for skill, scope in expected_scopes.items():
            with self.subTest(skill=skill):
                document = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("## Bounded execution", document)
                self.assertIn(scope, document)
                self.assertIn("included scope", document)
                self.assertIn("remaining scope", document)
                self.assertIn("return control", document)
                self.assertIn("do not invoke `$short-drama-review` automatically", document)

    def test_review_and_revision_are_single_pass_unless_explicitly_requested(self) -> None:
        review = read("skills/short-drama-review/SKILL.md")
        workflow = read("skills/short-drama/references/creator-workflow.md")

        self.assertIn("one bounded review pass", review)
        self.assertIn("do not edit owner artifacts or start a re-review loop", review)
        self.assertIn("Review is a separate bounded work unit", workflow)

    def test_reviewer_independence_is_not_a_completion_gate(self) -> None:
        forbidden = (
            "required_reviewer_independence",
            '"requested_review_mode"',
            '"effective_review_mode"',
            "自检只能是 `PROVISIONAL`",
            "最终通过必须由独立审查者签发",
            "不接受负责人自审",
            "独立审查者签发结论",
            "同一写作产物不能自证通过",
            "自己的资产发最终 approval",
            "最终通过必须由reviewer签发",
        )
        public_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in SKILLS.rglob("*")
            if path.is_file() and path.suffix in {".md", ".json", ".yaml"}
        )
        for marker in forbidden:
            self.assertNotIn(marker, public_text, marker)

        stage_contract = read("skills/short-drama-review/references/stage-contract.md")
        self.assertIn("Self-review may record any evidence-supported verdict", stage_contract)
        self.assertIn("never retry isolation as a completion strategy", stage_contract)

        verdict = json.loads(
            read("skills/short-drama-review/assets/verdict-template.json")
        )
        self.assertEqual(verdict["review_method"], "uninvolved_reviewer | self_check")
        self.assertIsInstance(verdict["reviewer"], str)
        self.assertNotIn("required_reviewer_independence", verdict)


if __name__ == "__main__":
    unittest.main()
