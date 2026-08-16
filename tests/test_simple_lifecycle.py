import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SUITE = Path(__file__).resolve().parents[1]
SKILL = SUITE / "skills/short-drama"
SCRIPT = SKILL / "scripts/project_tool.py"
SPEC = importlib.util.spec_from_file_location("simple_lifecycle", SCRIPT)
assert SPEC and SPEC.loader
project_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_tool)


class SimpleLifecycleTests(unittest.TestCase):
    def make_project(self, directory: str, *, chinese: bool = True) -> Path:
        root = Path(directory) / "project"
        project_tool.initialize_project(
            root,
            title="轻量短剧",
            language="zh-CN",
            aspect_ratio="9:16",
            suite_root=SKILL,
        )
        if not chinese:
            state_path = root / ".short-drama/state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project_layout_mode"] = "legacy"
            project_tool.atomic_json(state_path, state)
        return root

    def publish_script(
        self, root: Path, *, input_path: str | None = None, text: str = "# 第一集\n"
    ) -> None:
        project_tool.publish_candidate(
            root,
            owner="short-drama-write",
            artifact_id="EP001:script",
            outputs={"剧集/EP001/screenplay.md": text},
            inputs=[input_path] if input_path else [],
        )

    def approve_script(self, root: Path) -> None:
        project_tool.record_creator_acceptance(
            root, artifact_id="EP001:script", decision="accepted"
        )
        project_tool.record_review(
            root,
            artifact_id="EP001:script",
            verdict="approve",
            reviewer="review pass",
        )

    def test_init_creates_small_state_and_creator_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            state = json.loads((root / ".short-drama/state.json").read_text())
            project = json.loads((root / "short-drama.json").read_text())
            self.assertEqual(state["schema_version"], "2.0")
            self.assertEqual(state["artifacts"], {})
            self.assertNotIn("current_checkpoint", project)
            self.assertNotIn("current_checkpoint", project_tool.project_status(root))
            self.assertNotIn("active_transaction", state)
            self.assertNotIn("blocked_transactions", state)
            for relative in ("输入", "项目开发", "设定集", "剧集", "交付", "创作者决策", "审查"):
                self.assertTrue((root / relative).is_dir(), relative)
            self.assertFalse((root / ".short-drama/transactions").exists())

    def test_cli_exposes_no_recovery_command(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        for command in ("publish", "accept", "review", "package", "verify"):
            self.assertIn(command, result.stdout)
        self.assertNotIn("recover", result.stdout)
        self.assertFalse(hasattr(project_tool, "record_independent_review"))

    def test_publish_accept_review_use_one_creator_facing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "needs_confirmation",
            )
            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="accepted"
            )
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "accepted",
            )
            project_tool.record_review(
                root, artifact_id="EP001:script", verdict="approve"
            )
            status = project_tool.project_status(root)
            self.assertEqual(status["artifacts"]["EP001:script"], "approved")
            self.assertEqual(status["lifecycle"], {"artifact_state": {"approved": 1}})

    def test_rejection_and_revision_are_plain_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="rejected", note="重写开场"
            )
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "revise",
            )
            self.publish_script(root, text="# 第一集\n新版\n")
            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="accepted"
            )
            project_tool.record_review(
                root, artifact_id="EP001:script", verdict="revise", note="动机不足"
            )
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "revise",
            )

    def test_direct_input_change_is_detected_without_propagation_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            source = root / "项目开发/episode-map.jsonl"
            source.write_text('{"episode_id":"EP001"}\n', encoding="utf-8")
            self.publish_script(root, input_path="项目开发/episode-map.jsonl")
            self.approve_script(root)
            source.write_text('{"episode_id":"EP001","changed":true}\n', encoding="utf-8")
            status = project_tool.project_status(root)
            self.assertEqual(status["artifacts"]["EP001:script"], "update_needed")
            persisted = json.loads((root / ".short-drama/state.json").read_text())
            self.assertNotIn("stale", json.dumps(persisted))

    def test_output_edit_invalidates_acceptance_on_read_without_rewriting_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            state_before = (root / ".short-drama/state.json").read_bytes()
            (root / "剧集/EP001/screenplay.md").write_text("外部修改\n", encoding="utf-8")
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "update_needed",
            )
            self.assertEqual((root / ".short-drama/state.json").read_bytes(), state_before)

    def test_republish_replaces_current_acceptance_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            self.publish_script(root, text="# 第一集\n第二版\n")
            state = json.loads((root / ".short-drama/state.json").read_text())
            record = state["artifacts"]["EP001:script"]
            self.assertIsNone(record["acceptance"])
            self.assertIsNone(record["review"])

    def test_review_requires_current_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            with self.assertRaisesRegex(project_tool.ProjectConflictError, "acceptance"):
                project_tool.record_review(
                    root, artifact_id="EP001:script", verdict="approve"
                )

    def test_review_accepts_a_plain_reviewer_label_without_provenance_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="accepted"
            )
            result = project_tool.record_review(
                root,
                artifact_id="EP001:script",
                verdict="approve_with_notes",
                reviewer="同事复核",
                note="可以投产",
            )
            self.assertEqual(result["state"], "approved")

    def test_acceptance_refuses_a_changed_direct_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            source = root / "项目开发/episode-map.jsonl"
            source.write_text("{}\n", encoding="utf-8")
            self.publish_script(root, input_path="项目开发/episode-map.jsonl")
            source.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(project_tool.ProjectConflictError, "input changed"):
                project_tool.record_creator_acceptance(
                    root, artifact_id="EP001:script", decision="accepted"
                )

    def test_publish_rejects_invalid_json_and_jsonl_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            for relative, content in (
                ("剧集/EP001/episode-card.json", "{"),
                ("剧集/EP001/beats.jsonl", '{}\n{"bad"\n'),
            ):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    project_tool.publish_candidate(
                        root,
                        owner="short-drama-write",
                        artifact_id=f"bad:{relative}",
                        outputs={relative: content},
                    )
                self.assertFalse((root / relative).exists())

    def test_publish_allows_first_writer_and_protects_non_stage_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            published = project_tool.publish_candidate(
                root,
                owner="independent-script-skill",
                artifact_id="independent-script",
                outputs={"剧集/EP001/screenplay.md": "x"},
            )
            self.assertEqual(published["owner"], "independent-script-skill")
            with self.assertRaisesRegex(ValueError, "immutable"):
                project_tool.publish_candidate(
                    root,
                    owner="short-drama-write",
                    artifact_id="input",
                    outputs={"输入/source.md": "x"},
                )
            with self.assertRaisesRegex(ValueError, "packaging gate"):
                project_tool.publish_candidate(
                    root,
                    owner="short-drama-write",
                    artifact_id="delivery",
                    outputs={"交付/EP001/manifest.json": "{}"},
                )

    def test_publish_rejects_path_aliases_and_unsafe_episode_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            for relative in (
                "剧集/EP001/storyboard /shots.jsonl",
                "剧集/EP001/storyboard./shots.jsonl",
                "剧集/EP001/CON.json",
                "剧集/EP001/notes\nextra.md",
                "剧集/EP001/a:b.json",
            ):
                with self.subTest(relative=relative):
                    with self.assertRaisesRegex(ValueError, "unsafe project-relative path"):
                        project_tool.publish_candidate(
                            root,
                            owner="short-drama-write",
                            artifact_id="nonportable",
                            outputs={relative: "x"},
                        )

            with self.assertRaises(project_tool.NonPortablePathError):
                project_tool.publish_candidate(
                    root,
                    owner="short-drama-write",
                    artifact_id="aliases",
                    outputs={
                        "剧集/EP001/notes.md": "a",
                        "剧集/EP001/NOTES.md": "b",
                    },
                )

            composed = "项目开发/caf\N{LATIN SMALL LETTER E WITH ACUTE}.md"
            decomposed = "项目开发/cafe\N{COMBINING ACUTE ACCENT}.md"
            with self.assertRaisesRegex(
                project_tool.NonPortablePathError, "portable aliases"
            ):
                project_tool.publish_candidate(
                    root,
                    owner="independent-development-skill",
                    artifact_id="unicode-aliases",
                    outputs={composed: "a", decomposed: "b"},
                )

            with self.assertRaisesRegex(ValueError, "EP001-style"):
                project_tool.publish_candidate(
                    root,
                    owner="short-drama-write",
                    artifact_id="episode",
                    outputs={"剧集/1/screenplay.md": "x"},
                )

    def test_one_output_path_has_one_artifact_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            with self.assertRaisesRegex(ValueError, "already belongs"):
                project_tool.publish_candidate(
                    root,
                    owner="short-drama-write",
                    artifact_id="another",
                    outputs={"剧集/EP001/screenplay.md": "other"},
                )

    def test_legacy_state_is_read_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            target = root / "剧集/EP001/screenplay.md"
            target.parent.mkdir(parents=True)
            target.write_text("legacy", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            state_path = root / ".short-drama/state.json"
            legacy = json.loads(state_path.read_text())
            legacy["schema_version"] = "1.0.0-draft"
            legacy["artifacts"] = {
                "EP001:script": {
                    "owner": "short-drama-write",
                    "candidate_targets": {"剧集/EP001/screenplay.md": digest},
                    "accepted_targets": {"剧集/EP001/screenplay.md": digest},
                    "creator_acceptance": "accepted",
                    "independent_review": "approve",
                }
            }
            project_tool.atomic_json(state_path, legacy)
            before = state_path.read_bytes()
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "approved",
            )
            self.assertEqual(state_path.read_bytes(), before)

    def test_publish_migrates_legacy_state_on_the_next_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            state_path = root / ".short-drama/state.json"
            state = json.loads(state_path.read_text())
            state["schema_version"] = "1.0.0-draft"
            project_tool.atomic_json(state_path, state)
            self.publish_script(root)
            migrated = json.loads(state_path.read_text())
            self.assertEqual(migrated["schema_version"], "2.0")
            self.assertNotIn("active_transaction", migrated)

    def test_legacy_migration_keeps_the_current_candidate_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            target = root / "剧集/EP001/screenplay.md"
            target.parent.mkdir(parents=True)
            target.write_text("new candidate", encoding="utf-8")
            direct_input = root / "输入/current.md"
            direct_input.write_text("current input", encoding="utf-8")
            old_input = root / "输入/old.md"
            old_input.write_text("old input", encoding="utf-8")
            def digest(path: Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()
            state_path = root / ".short-drama/state.json"
            legacy = json.loads(state_path.read_text())
            legacy["schema_version"] = "1.0.0-draft"
            legacy["artifacts"] = {
                "EP001:script": {
                    "owner": "short-drama-write",
                    "candidate_targets": {str(target.relative_to(root)): digest(target)},
                    "accepted_targets": {str(target.relative_to(root)): "0" * 64},
                    "candidate_inputs": {
                        str(direct_input.relative_to(root)): digest(direct_input)
                    },
                    "accepted_inputs": {str(old_input.relative_to(root)): digest(old_input)},
                    "creator_acceptance": "accepted",
                }
            }
            project_tool.atomic_json(state_path, legacy)

            project_tool.record_creator_acceptance(
                root, artifact_id="EP001:script", decision="accepted"
            )
            direct_input.write_text("changed after accepting candidate", encoding="utf-8")
            self.assertEqual(
                project_tool.project_status(root)["artifacts"]["EP001:script"],
                "update_needed",
            )

    def test_package_requires_current_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            with self.assertRaisesRegex(project_tool.PackageBlockedError, "approved"):
                project_tool.build_delivery_package(
                    root,
                    episode="EP001",
                    includes=["剧集/EP001/screenplay.md"],
                )

    def test_package_rejects_cross_episode_includes_and_omissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            project_tool.publish_candidate(
                root,
                owner="short-drama-write",
                artifact_id="EP002:script",
                outputs={"剧集/EP002/screenplay.md": "# 第二集\n"},
            )
            project_tool.record_creator_acceptance(
                root, artifact_id="EP002:script", decision="accepted"
            )
            project_tool.record_review(
                root,
                artifact_id="EP002:script",
                verdict="approve",
                reviewer="reviewer",
            )
            with self.assertRaisesRegex(ValueError, "belong to EP001"):
                project_tool.build_delivery_package(
                    root,
                    episode="EP001",
                    includes=["剧集/EP002/screenplay.md"],
                )

            self.publish_script(root)
            self.approve_script(root)
            with self.assertRaisesRegex(ValueError, "belong to EP001"):
                project_tool.build_delivery_package(
                    root,
                    episode="EP001",
                    includes=["剧集/EP001/screenplay.md"],
                    omissions={"剧集/EP002/notes.md": "not requested"},
                )

    def test_package_writes_the_same_approved_bytes_it_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            approved = b"# first approved version\n"
            self.publish_script(root, text=approved.decode())
            self.approve_script(root)
            source = root / "剧集/EP001/screenplay.md"
            real_sha256_bytes = project_tool.sha256_bytes

            def mutate_after_hash(content: bytes) -> str:
                digest = real_sha256_bytes(content)
                source.write_bytes(b"unapproved race bytes\n")
                return digest

            with mock.patch.object(
                project_tool, "sha256_bytes", side_effect=mutate_after_hash
            ):
                result = project_tool.build_delivery_package(
                    root,
                    episode="EP001",
                    includes=["剧集/EP001/screenplay.md"],
                )
            delivered = root / result["delivery_root"] / "artifacts/剧集/EP001/screenplay.md"
            self.assertEqual(delivered.read_bytes(), approved)

    def test_package_rejects_bytes_changed_after_approval_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root, text="# approved\n")
            self.approve_script(root)
            source = root / "剧集/EP001/screenplay.md"
            real_artifact_state = project_tool._artifact_state

            def mutate_after_check(project_root, record):
                state = real_artifact_state(project_root, record)
                source.write_text("unapproved before snapshot", encoding="utf-8")
                return state

            with mock.patch.object(
                project_tool, "_artifact_state", side_effect=mutate_after_check
            ), self.assertRaisesRegex(
                project_tool.PackageBlockedError, "changed after approval"
            ):
                project_tool.build_delivery_package(
                    root,
                    episode="EP001",
                    includes=["剧集/EP001/screenplay.md"],
                )
            self.assertFalse((root / "交付/EP001").exists())

    def test_package_and_verify_selected_approved_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            result = project_tool.build_delivery_package(
                root,
                episode="EP001",
                includes=["剧集/EP001/screenplay.md"],
            )
            delivery = root / result["delivery_root"]
            self.assertTrue((delivery / "manifest.json").is_file())
            self.assertTrue((delivery / "checksums.sha256").is_file())
            self.assertTrue((delivery / "artifacts/剧集/EP001/screenplay.md").is_file())
            verified = project_tool.verify_delivery_package(root, episode="EP001")
            self.assertEqual(verified, {"episode": "EP001", "status": "verified", "problems": []})

    def test_verify_detects_tamper_and_unlisted_addition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            result = project_tool.build_delivery_package(
                root, episode="EP001", includes=["剧集/EP001/screenplay.md"]
            )
            delivery = root / result["delivery_root"]
            (delivery / "artifacts/剧集/EP001/screenplay.md").write_text("tampered")
            (delivery / "extra.md").write_text("extra")
            verified = project_tool.verify_delivery_package(root, episode="EP001")
            self.assertEqual(verified["status"], "tampered")
            self.assertTrue(any("checksum mismatch" in item for item in verified["problems"]))
            self.assertTrue(any("unexpected delivery file" in item for item in verified["problems"]))

    def test_verify_checks_manifest_file_hashes_even_if_checksums_are_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            result = project_tool.build_delivery_package(
                root, episode="EP001", includes=["剧集/EP001/screenplay.md"]
            )
            delivery = root / result["delivery_root"]
            artifact = delivery / "artifacts/剧集/EP001/screenplay.md"
            artifact.write_text("laundered bytes", encoding="utf-8")
            members = [delivery / "manifest.json", artifact]
            checksums = "".join(
                f"{project_tool.sha256_file(path)}  {path.relative_to(delivery).as_posix()}\n"
                for path in members
            )
            (delivery / "checksums.sha256").write_text(checksums, encoding="utf-8")

            verified = project_tool.verify_delivery_package(root, episode="EP001")
            self.assertEqual(verified["status"], "tampered")
            self.assertTrue(
                any("manifest hash mismatch" in item for item in verified["problems"])
            )

    def test_verify_rejects_a_symlinked_delivery_parent(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            external = Path(directory) / "external-delivery"
            package = external / "EP001"
            package.mkdir(parents=True)
            (package / "checksums.sha256").write_text("", encoding="utf-8")
            (root / "交付").rmdir()
            try:
                (root / "交付").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation is unavailable: {exc}")

            with self.assertRaisesRegex(
                project_tool.ProjectConflictError, "delivery root"
            ):
                project_tool.verify_delivery_package(root, episode="EP001")

    def test_package_replaces_a_previous_package_as_one_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            project_tool.build_delivery_package(
                root, episode="EP001", includes=["剧集/EP001/screenplay.md"]
            )
            self.publish_script(root, text="# 第一集\n第二版\n")
            self.approve_script(root)
            project_tool.build_delivery_package(
                root, episode="EP001", includes=["剧集/EP001/screenplay.md"]
            )
            delivered = root / "交付/EP001/artifacts/剧集/EP001/screenplay.md"
            self.assertIn("第二版", delivered.read_text(encoding="utf-8"))
            self.assertFalse(any((root / "交付").glob(".EP001.*.old")))

    def test_package_records_explicit_omissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root)
            self.approve_script(root)
            project_tool.build_delivery_package(
                root,
                episode="EP001",
                includes=["剧集/EP001/screenplay.md"],
                omissions={"剧集/EP001/notes.md": "not requested"},
            )
            manifest = json.loads((root / "交付/EP001/manifest.json").read_text())
            self.assertEqual(
                manifest["omitted"],
                [{"reason": "not requested", "source": "剧集/EP001/notes.md"}],
            )

    def test_status_never_exposes_hashes_or_creative_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.publish_script(root, text="秘密台词")
            serialized = json.dumps(project_tool.project_status(root), ensure_ascii=False)
            self.assertNotIn("秘密台词", serialized)
            self.assertIsNone(__import__("re").search(r"[0-9a-f]{64}", serialized))

    def test_coordinated_edit_rejects_an_old_version(self) -> None:
        if os.name == "nt":
            self.skipTest("dashboard descriptor contract is POSIX-only")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            target = root / "notes.md"
            target.write_text("one", encoding="utf-8")
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(project_tool.ProjectConflictError, "changed"):
                    with project_tool.coordinated_project_text_edit_at(
                        descriptor, "notes.md", hashlib.sha256(b"old").hexdigest()
                    ):
                        pass
            finally:
                os.close(descriptor)

    def test_cli_runs_publish_accept_review_package_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            source = root / "draft.md"
            source.write_text("# 第一集\n", encoding="utf-8")
            commands = [
                ["publish", str(root), "--owner", "short-drama-write", "--artifact-id", "EP001:script", "--output", "剧集/EP001/screenplay.md=draft.md"],
                ["accept", str(root), "--artifact-id", "EP001:script", "--decision", "accepted"],
                ["review", str(root), "--artifact-id", "EP001:script", "--verdict", "approve"],
                ["package", str(root), "--episode", "EP001", "--include", "剧集/EP001/screenplay.md"],
                ["verify", str(root), "--episode", "EP001"],
            ]
            for command in commands:
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), *command],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)

    def test_project_discovery_and_languages_remain_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            self.assertEqual(project_tool.find_project(root / "剧集"), root.resolve())
            status = project_tool.project_status(root)
            self.assertEqual(status["language"], "zh-CN")
            self.assertEqual(status["prompt_language"], "en")


if __name__ == "__main__":
    unittest.main()
