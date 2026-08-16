import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
import unicodedata
import unittest
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterator


SUITE = Path(__file__).resolve().parents[1]
GOLDEN = SUITE / "examples/golden-project"
CORE = SUITE / "skills/short-drama"


def load_module(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SUITE / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_tool = load_module("golden_project_tool", "skills/short-drama/scripts/project_tool.py")
screenplay_index = load_module(
    "golden_screenplay_index", "skills/short-drama-write/scripts/screenplay_index.py"
)
asset_check = load_module(
    "golden_asset_check", "skills/short-drama-assets/scripts/asset_check.py"
)
image_prompt_check = load_module(
    "golden_image_prompt_check",
    "skills/short-drama-image-prompts/scripts/image_prompt_check.py",
)
storyboard_check = load_module(
    "golden_storyboard_check",
    "skills/short-drama-storyboard/scripts/storyboard_check.py",
)
motion_timing_check = load_module(
    "golden_motion_timing_check",
    "skills/short-drama-video-prompts/scripts/motion_timing_check.py",
)
review_check = load_module(
    "golden_review_check", "skills/short-drama-review/scripts/review_check.py"
)


EPISODES = [f"EP{number:03d}" for number in range(1, 9)]
SHOT_COUNTS = [5, 3, 5, 4, 4, 5, 6, 5]
TEXT_SUFFIXES = {".json", ".jsonl", ".md"}
MEDIA_SUFFIXES = {
    ".aac",
    ".avi",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".pdf",
    ".png",
    ".wav",
    ".webm",
    ".webp",
    ".zip",
}
SENSITIVE_KEYS = {
    "_id",
    "created_at",
    "key",
    "model",
    "remote_id",
    "seed",
    "source_id",
    "task_id",
    "uid",
    "updated_at",
    "url",
    "userId",
}
SENSITIVE_TEXT = (
    "mongodb://",
    "http://",
    "https://",
    "/Users/",
    "C:\\Users\\",
)
IPV4_LITERAL = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
LONG_DECIMAL_LITERAL = re.compile(r"(?<![A-Za-z0-9])\d{6,}(?![A-Za-z0-9])")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def walk_values(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)


def record_with_id(records: list[dict[str, Any]], record_id: str) -> dict[str, Any] | None:
    for record in records:
        if record_id in record.values():
            return record
    return None


def resolve_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer.lstrip("/").split("/") if pointer != "/" else [""]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(pointer)
    return current


class GoldenProjectTests(unittest.TestCase):
    def test_has_exactly_eight_complete_episode_chains(self) -> None:
        episode_root = GOLDEN / "剧集"
        self.assertEqual([path.name for path in sorted(episode_root.iterdir())], EPISODES)
        required = {
            "episode-card.json",
            "beats.jsonl",
            "screenplay.md",
            "screenplay-index.jsonl",
            "assets/occurrences.jsonl",
            "assets/decisions.jsonl",
            "assets/continuity.jsonl",
            "assets/image-prompt-specs.jsonl",
            "assets/image-prompts.md",
            "storyboard/shots.jsonl",
            "storyboard/coverage.json",
            "storyboard/keyframes.jsonl",
            "storyboard/keyframe-prompts.md",
            "storyboard/motion-specs.jsonl",
            "storyboard/video-prompts.md",
        }
        for episode, shot_count in zip(EPISODES, SHOT_COUNTS):
            with self.subTest(episode=episode):
                root = episode_root / episode
                actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
                self.assertEqual(actual, required)
                shots = read_jsonl(root / "storyboard/shots.jsonl")
                self.assertEqual(len(shots), shot_count)
                self.assertTrue(all(shot["duration_seconds"] == 15 for shot in shots))
                self.assertEqual(sum(shot["duration_seconds"] for shot in shots), [75, 45, 75, 60, 60, 75, 90, 75][EPISODES.index(episode)])

    def test_fixture_is_portable_utf8_text_and_json_only(self) -> None:
        for path in GOLDEN.rglob("*"):
            relative = path.relative_to(GOLDEN).as_posix()
            with self.subTest(path=relative):
                self.assertFalse(path.is_symlink())
                self.assertEqual(relative, unicodedata.normalize("NFC", relative))
                self.assertNotIn("..", PurePosixPath(relative).parts)
                if not path.is_file():
                    continue
                self.assertIn(path.suffix, TEXT_SUFFIXES)
                text = path.read_bytes().decode("utf-8")
                self.assertNotIn("\x00", text)
                if path.suffix == ".json":
                    self.assertIsInstance(json.loads(text), dict)
                elif path.suffix == ".jsonl":
                    self.assertTrue(read_jsonl(path), relative)

    def test_fixture_contains_no_sensitive_fields_placeholders_or_media(self) -> None:
        placeholder = re.compile(r"<[^>\n]+>")
        for path in GOLDEN.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(GOLDEN).as_posix()
            with self.subTest(path=relative):
                self.assertNotIn(path.suffix.casefold(), MEDIA_SUFFIXES)
                text = path.read_text(encoding="utf-8")
                for needle in SENSITIVE_TEXT:
                    self.assertNotIn(needle, text)
                self.assertNotRegex(text, IPV4_LITERAL)
                self.assertNotRegex(text, LONG_DECIMAL_LITERAL)
                self.assertNotRegex(text, placeholder)
                if path.suffix == ".json":
                    documents = [json.loads(text)]
                elif path.suffix == ".jsonl":
                    documents = read_jsonl(path)
                else:
                    documents = []
                for value in walk_values(documents):
                    if isinstance(value, dict):
                        self.assertFalse(SENSITIVE_KEYS.intersection(value), relative)

    def test_screenplay_indexes_are_clean_and_byte_for_byte_rebuildable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for episode in EPISODES:
                with self.subTest(episode=episode):
                    root = GOLDEN / f"剧集/{episode}"
                    existing = root / "screenplay-index.jsonl"
                    meta = read_jsonl(existing)[0]
                    self.assertEqual(meta["review_status"], "clean")
                    speakers = json.loads((root / "episode-card.json").read_text(encoding="utf-8"))["speaker_roster"]
                    rebuilt = output_root / f"{episode}.jsonl"
                    screenplay_index.build_index(
                        root / "screenplay.md",
                        rebuilt,
                        source_ref=f"剧集/{episode}/screenplay.md",
                        speakers=speakers,
                    )
                    self.assertEqual(rebuilt.read_bytes(), existing.read_bytes())

    def test_every_direct_reference_resolves_to_its_exact_hash(self) -> None:
        checked = 0
        for source in GOLDEN.rglob("*"):
            if not source.is_file() or source.suffix not in {".json", ".jsonl"}:
                continue
            documents = [json.loads(source.read_text(encoding="utf-8"))] if source.suffix == ".json" else read_jsonl(source)
            for value in walk_values(documents):
                if not isinstance(value, dict) or not {"owner", "artifact", "hash"}.issubset(value):
                    continue
                checked += 1
                artifact = PurePosixPath(value["artifact"])
                self.assertFalse(artifact.is_absolute(), source)
                self.assertNotIn("..", artifact.parts, source)
                target = GOLDEN / artifact
                self.assertTrue(target.is_file(), f"{source}: {artifact}")
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), value["hash"], f"{source}: {artifact}")
                record: Any = None
                if target.suffix == ".jsonl" and "record_id" in value:
                    record = record_with_id(read_jsonl(target), value["record_id"])
                    self.assertIsNotNone(record, f"{source}: {artifact}#{value['record_id']}")
                elif target.suffix == ".json":
                    record = json.loads(target.read_text(encoding="utf-8"))
                    if "record_id" in value:
                        self.assertIn(value["record_id"], list(walk_values(record)))
                elif target.suffix == ".md" and "record_id" in value:
                    self.assertIn(
                        value["record_id"],
                        target.read_text(encoding="utf-8"),
                        f"{source}: {artifact}#{value['record_id']}",
                    )
                if "field" in value and record is not None:
                    try:
                        resolve_pointer(record, value["field"])
                    except (KeyError, IndexError, TypeError, ValueError) as error:
                        self.fail(f"{source}: unresolved field {artifact}{value['field']}: {error}")
        self.assertGreater(checked, 500)

    def test_each_skill_checker_accepts_its_own_golden_artifacts(self) -> None:
        assets = asset_check.validate_files(
            GOLDEN / "设定集/characters.jsonl", GOLDEN / "设定集/looks.jsonl"
        )
        self.assertEqual(assets["status"], "valid")
        for episode in EPISODES:
            with self.subTest(episode=episode):
                root = GOLDEN / f"剧集/{episode}"
                self.assertEqual(
                    image_prompt_check.validate_file(root / "assets/image-prompt-specs.jsonl")["status"],
                    "valid",
                )
                storyboard = storyboard_check.check(
                    root / "storyboard/coverage.json",
                    root / "storyboard/shots.jsonl",
                    root / "storyboard/keyframes.jsonl",
                    GOLDEN / "short-drama.json",
                )
                self.assertEqual(storyboard["status"], "pass")
                motion = motion_timing_check.check(
                    motion_timing_check._load_jsonl(root / "storyboard/motion-specs.jsonl"),
                    motion_timing_check._load_jsonl(root / "storyboard/shots.jsonl"),
                )
                self.assertEqual(motion["status"], "pass")
                self.assertEqual(motion["explicit_checked"], SHOT_COUNTS[EPISODES.index(episode)])
        review = review_check.validate_files(
            GOLDEN / "审查/findings.jsonl", GOLDEN / "审查/verdict.json"
        )
        self.assertEqual(review["verdict"], "APPROVE_WITH_NOTES")
        self.assertEqual(review["open_blockers"], 0)

    def test_approved_review_is_bound_to_creator_accepted_hashes_and_text_policy(self) -> None:
        acceptance_path = GOLDEN / "创作者决策/golden-production-acceptance.jsonl"
        decisions = read_jsonl(acceptance_path)
        self.assertEqual(len(decisions), 9)
        self.assertTrue(all(item["status"] == "accepted" for item in decisions))
        accepted = {
            (artifact["owner"], artifact["artifact"], artifact["hash"])
            for decision in decisions
            for artifact in decision["accepted_artifact_refs"]
        }
        verdict = json.loads((GOLDEN / "审查/verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(len(verdict["acceptance_refs"]), 9)
        for artifact in verdict["reviewed_artifacts"]:
            with self.subTest(artifact=artifact["artifact"]):
                self.assertEqual(artifact.get("authority"), "accepted")
                self.assertIn(
                    (artifact["owner"], artifact["artifact"], artifact["hash"]),
                    accepted,
                )
                if artifact["artifact"].endswith("motion-specs.jsonl"):
                    self.assertEqual(artifact["owner"], "short-drama-video-prompts")

        props = {item["prop_id"]: item for item in read_jsonl(GOLDEN / "设定集/props.jsonl")}
        for episode in EPISODES:
            specs = read_jsonl(
                GOLDEN / f"剧集/{episode}/assets/image-prompt-specs.jsonl"
            )
            prop_spec = next(item for item in specs if item["purpose"] == "prop_plate")
            prop_id = prop_spec["asset_binding"]["identity_ref"]["record_id"]
            handling = prop_spec["text_handling"]
            with self.subTest(episode=episode, prop=prop_id):
                self.assertEqual(handling["source_mode"], props[prop_id]["text_policy"]["mode"])
                expected_render = (
                    "postproduction"
                    if handling["source_mode"] == "exact_readable"
                    else "blank"
                )
                self.assertEqual(handling["render_treatment"]["mode"], expected_render)

    def test_storyboard_states_and_motion_follow_their_source_blocks(self) -> None:
        states = {
            item["state_id"]: item
            for item in read_jsonl(GOLDEN / "设定集/prop-states.jsonl")
        }
        characters = {
            item["display_name"]: item["character_id"]
            for item in read_jsonl(GOLDEN / "设定集/characters.jsonl")
        }
        for episode in EPISODES:
            root = GOLDEN / f"剧集/{episode}"
            index = {
                item["block_id"]: item
                for item in read_jsonl(root / "screenplay-index.jsonl")
                if item.get("record_type") == "block"
            }
            shots = read_jsonl(root / "storyboard/shots.jsonl")
            keyframes = read_jsonl(root / "storyboard/keyframes.jsonl")
            motions = read_jsonl(root / "storyboard/motion-specs.jsonl")
            by_boundary = {
                (item["boundary_ref"]["record_id"], item["boundary_role"]): item
                for item in keyframes
            }
            for position, (shot, motion) in enumerate(zip(shots, motions)):
                with self.subTest(episode=episode, shot=shot["shot_id"]):
                    transition = shot["state_transition"]
                    start_states = shot["start_boundary"]["visible_state"]
                    end_states = shot["end_boundary"]["visible_state"]
                    self.assertEqual(start_states, [] if transition["from"] is None else [transition["from"]])
                    self.assertEqual(end_states, [] if transition["to"] is None else [transition["to"]])
                    if position:
                        self.assertEqual(shots[position - 1]["state_transition"]["to"], transition["from"])
                    if transition["to"] != transition["from"] and transition["to"] is not None:
                        valid_from = states[transition["to"]]["validity"]["from"]
                        cause = valid_from.rsplit("/", 1)[-1]
                        self.assertIn(cause, {item["record_id"] for item in shot["source_refs"]})

                    for role, state_id in (("start", transition["from"]), ("end", transition["to"])):
                        frame = by_boundary[(shot["shot_id"], role)]
                        prop_variants = [
                            item["variant_ref"]["record_id"]
                            for item in frame["asset_bindings"]
                            if item["identity_ref"]["record_id"].startswith("PROP-")
                        ]
                        self.assertEqual(prop_variants, [] if state_id is None else [state_id])

                    shot_actors = {
                        item["identity_ref"]["record_id"]
                        for item in shot["asset_bindings"]
                        if item["identity_ref"]["record_id"].startswith("CHAR-")
                    }
                    motion_actors = {item["actor"] for item in motion["ordered_subject_motion"]}
                    self.assertTrue(motion_actors)
                    self.assertTrue(motion_actors.issubset(shot_actors))
                    source_ids = {item["record_id"] for item in shot["source_refs"]}
                    actions = []
                    for item in motion["ordered_subject_motion"]:
                        actions.append(item["action"])
                        self.assertNotIn(" / [", item["action"])
                        self.assertTrue(item["source_refs"])
                        self.assertTrue(
                            all(
                                index[source_ref["record_id"]]["kind"]
                                in {"action", "dialogue"}
                                for source_ref in item["source_refs"]
                            )
                        )
                        self.assertTrue(
                            {
                                source_ref["record_id"]
                                for source_ref in item["source_refs"]
                            }.issubset(source_ids)
                        )
                    self.assertTrue(
                        all(
                            "perform the shot's single visible story action" not in item["action"]
                            for item in motion["ordered_subject_motion"]
                        )
                    )
                    self.assertEqual(len(actions), len(set(actions)))

                    if shot["shot_id"] == "SHOT-EP001-05":
                        self.assertEqual(
                            {
                                item["actor"]: item["action"]
                                for item in motion["ordered_subject_motion"]
                            },
                            {
                                "CHAR-CHEN-YUAN": "陈予安在账本上写下一行。",
                                "CHAR-LIANG-FENG": "梁锋慢慢放下配送箱，双手捧住热碗。",
                            },
                        )

                    expected_dialogue = {
                        item["record_id"] for item in shot["dialogue_audio_refs"]
                    }
                    actual_dialogue = {
                        item["source_ref"]["record_id"]
                        for item in motion["audio"]
                        if item["kind"] == "dialogue"
                    }
                    self.assertEqual(actual_dialogue, expected_dialogue)
                    dialogue_actors = {
                        characters[index[block_id]["speaker"]]
                        for block_id in expected_dialogue
                    }
                    self.assertTrue(dialogue_actors.issubset(motion_actors))
                    for item in motion["audio"]:
                        if item["kind"] != "dialogue":
                            continue
                        block = index[item["source_ref"]["record_id"]]
                        self.assertEqual(
                            item["speaker_ref"]["record_id"], characters[block["speaker"]]
                        )
                        self.assertTrue(item["exact_text"])
                    if shot["shot_id"] == "SHOT-EP007-05":
                        self.assertEqual(
                            motion_actors,
                            {"CHAR-CHEN-YUAN", "CHAR-ZHOU-HAIPING"},
                        )

    def test_golden_files_complete_the_core_lifecycle_without_installing_every_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            project_tool.initialize_project(
                root,
                title="善意不结账",
                language="zh-CN",
                prompt_language="en",
                aspect_ratio="9:16",
                suite_root=CORE,
            )
            for name in ("输入", "项目开发", "设定集", "剧集", "创作者决策", "审查"):
                shutil.copytree(GOLDEN / name, root / name, dirs_exist_ok=True)

            outputs = {
                "剧集/EP001/screenplay.md": (GOLDEN / "剧集/EP001/screenplay.md").read_bytes(),
                "剧集/EP001/screenplay-index.jsonl": (GOLDEN / "剧集/EP001/screenplay-index.jsonl").read_bytes(),
            }
            result = project_tool.publish_candidate(
                root,
                owner="short-drama-write",
                artifact_id="EP001:script",
                outputs=outputs,
                inputs=["项目开发/episode-map.jsonl"],
            )
            self.assertEqual(result["state"], "needs_confirmation")
            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="accepted"
            )
            reviewed = project_tool.record_review(
                root,
                artifact_id="EP001:script",
                verdict="approve_with_notes",
                reviewer="golden fixture lifecycle",
                note="Exact readable text remains a postproduction task.",
            )
            self.assertEqual(reviewed["state"], "approved")
            package = project_tool.build_delivery_package(
                root,
                episode="EP001",
                includes=list(outputs),
            )
            self.assertEqual(len(package["files"]), 2)
            self.assertEqual(
                project_tool.verify_delivery_package(root, episode="EP001"),
                {"episode": "EP001", "status": "verified", "problems": []},
            )


if __name__ == "__main__":
    unittest.main()
