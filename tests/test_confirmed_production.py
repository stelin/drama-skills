import importlib.util
import json
from unittest import mock
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SUITE = Path(__file__).resolve().parents[1]
CORE_SCRIPT = SUITE / "skills/short-drama/scripts/project_tool.py"
PRODUCTION_SCRIPT = SUITE / "skills/short-drama-produce/scripts/production_tool.py"
FIXTURE_ADAPTER = SUITE / "skills/short-drama-produce/scripts/fixture_adapter.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_tool = load_module("production_core", CORE_SCRIPT)
production_tool = load_module("confirmed_production", PRODUCTION_SCRIPT)


class ConfirmedProductionTests(unittest.TestCase):
    def make_project(self, directory: str) -> Path:
        root = Path(directory) / "project"
        project_tool.initialize_project(
            root,
            title="投产测试",
            language="zh-CN",
            aspect_ratio="9:16",
            suite_root=SUITE / "skills/short-drama",
        )
        source = root / "剧集/EP001/prompts/current.md"
        source.parent.mkdir(parents=True)
        source.write_text("当前提示词来源\n", encoding="utf-8")
        reference = root / "输入/reference.png"
        reference.write_bytes(b"reference")
        return root

    def write_job(
        self,
        root: Path,
        *,
        modality: str = "image",
        job_id: str = "EP001-SHOT001",
        prompt: str = "一名角色站在雨夜门口",
        output: str | None = None,
        overwrite: bool = False,
        parameters: dict | None = None,
    ) -> Path:
        extensions = {"image": "png", "video": "mp4", "tts": "wav"}
        output = output or (
            f"剧集/EP001/制作成果/{modality}/{job_id}.{extensions[modality]}"
        )
        path = root / "job.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "job_id": job_id,
                    "modality": modality,
                    "adapter": "fixture",
                    "prompt": prompt,
                    "source": "剧集/EP001/prompts/current.md",
                    "references": ["输入/reference.png"],
                    "outputs": [output],
                    "parameters": parameters or {"count": 1},
                    "overwrite": overwrite,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def adapter_config(self, directory: str, *, fail: bool = False) -> Path:
        command = [sys.executable, str(FIXTURE_ADAPTER)]
        if fail:
            command.append("--fail")
        path = Path(directory) / "adapters.json"
        path.write_text(
            json.dumps(
                {
                    "adapters": {
                        "fixture": {
                            "command": command,
                            "timeout_seconds": 30,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return path

    def prepare_and_confirm(self, root: Path, job: Path) -> dict:
        preview = production_tool.prepare_job(root, job)
        production_tool.confirm_job(
            root,
            job_id=preview["job_id"],
            confirmation=preview["confirmation"],
        )
        return preview

    def test_prepare_only_returns_a_complete_preview_and_creates_no_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            preview = production_tool.prepare_job(root, job)

            self.assertEqual(preview["state"], "needs_confirmation")
            self.assertEqual(preview["count"], 1)
            self.assertEqual(preview["prompt"], "一名角色站在雨夜门口")
            self.assertEqual(preview["adapter"], "fixture")
            self.assertTrue(preview["confirmation"].startswith("CONFIRM EP001-SHOT001 "))
            self.assertFalse((root / preview["outputs"][0]).exists())
            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "needs_confirmation",
            )

    def test_run_requires_the_exact_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            config = self.adapter_config(directory)
            preview = production_tool.prepare_job(root, job)

            with self.assertRaises(production_tool.ConfirmationRequiredError):
                production_tool.run_job(
                    root, job_id="EP001-SHOT001", adapter_config=config
                )
            with self.assertRaises(production_tool.ConfirmationRequiredError):
                production_tool.confirm_job(
                    root,
                    job_id="EP001-SHOT001",
                    confirmation="yes, generate it",
                )

            production_tool.confirm_job(
                root,
                job_id="EP001-SHOT001",
                confirmation=preview["confirmation"],
            )
            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "confirmed",
            )

    def test_changed_job_invalidates_a_previous_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root, prompt="版本一")
            preview = self.prepare_and_confirm(root, job)
            self.write_job(root, prompt="版本二")
            changed = production_tool.prepare_job(root, job)

            self.assertNotEqual(preview["confirmation"], changed["confirmation"])
            with self.assertRaises(production_tool.ConfirmationRequiredError):
                production_tool.run_job(
                    root,
                    job_id="EP001-SHOT001",
                    adapter_config=self.adapter_config(directory),
                )

    def test_changed_input_requires_prepare_and_confirmation_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            self.prepare_and_confirm(root, job)
            (root / "剧集/EP001/prompts/current.md").write_text(
                "提示词来源已改\n", encoding="utf-8"
            )

            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "needs_reconfirmation",
            )
            with self.assertRaises(production_tool.ConfirmationRequiredError):
                production_tool.run_job(
                    root,
                    job_id="EP001-SHOT001",
                    adapter_config=self.adapter_config(directory),
                )

    def test_fixture_executes_image_video_and_tts_jobs(self) -> None:
        signatures = {
            "image": b"\x89PNG",
            "video": b"\x00\x00\x00\x18ftypisom",
            "tts": b"RIFF",
        }
        for modality, signature in signatures.items():
            with self.subTest(modality=modality), tempfile.TemporaryDirectory() as directory:
                root = self.make_project(directory)
                job_id = f"EP001-{modality}"
                job = self.write_job(root, modality=modality, job_id=job_id)
                preview = self.prepare_and_confirm(root, job)
                result = production_tool.run_job(
                    root,
                    job_id=job_id,
                    adapter_config=self.adapter_config(directory),
                )

                target = root / preview["outputs"][0]
                self.assertTrue(target.read_bytes().startswith(signature))
                self.assertEqual(result["state"], "succeeded")
                self.assertEqual(result["outputs"][0]["path"], preview["outputs"][0])
                self.assertGreater(result["outputs"][0]["bytes"], 0)
                status = production_tool.job_status(root, job_id=job_id)
                self.assertEqual(status["state"], "succeeded")
                self.assertNotIn("command", json.dumps(status))

    def test_failed_started_adapter_consumes_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            self.prepare_and_confirm(root, job)
            config = self.adapter_config(directory, fail=True)

            with self.assertRaisesRegex(production_tool.AdapterError, "code 7"):
                production_tool.run_job(
                    root, job_id="EP001-SHOT001", adapter_config=config
                )
            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "failed",
            )
            with self.assertRaises(production_tool.ConfirmationRequiredError):
                production_tool.run_job(
                    root, job_id="EP001-SHOT001", adapter_config=config
                )

    def test_existing_output_requires_explicit_overwrite_without_consuming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            preview = self.prepare_and_confirm(root, job)
            target = root / preview["outputs"][0]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"existing")

            with self.assertRaisesRegex(FileExistsError, "overwrite is false"):
                production_tool.run_job(
                    root,
                    job_id="EP001-SHOT001",
                    adapter_config=self.adapter_config(directory),
                )
            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "confirmed",
            )

    def test_adapter_reads_an_immutable_confirmed_input_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            self.prepare_and_confirm(root, job)
            original = (root / "剧集/EP001/prompts/current.md").read_bytes()

            def inspect_snapshot(command, timeout, payload, cwd):
                snapshot = Path(payload["project_root"])
                self.assertNotEqual(snapshot, root)
                (root / "剧集/EP001/prompts/current.md").write_bytes(
                    b"CHANGED AFTER CHECK"
                )
                source = snapshot / "剧集/EP001/prompts/current.md"
                self.assertEqual(source.read_bytes(), original)
                output = Path(directory) / "snapshot-result.png"
                output.write_bytes(source.read_bytes())
                return {
                    "outputs": [
                        {"target": payload["outputs"][0], "source": str(output)}
                    ]
                }

            with mock.patch.object(
                production_tool, "_run_adapter", side_effect=inspect_snapshot
            ):
                result = production_tool.run_job(
                    root,
                    job_id="EP001-SHOT001",
                    adapter_config=self.adapter_config(directory),
                )
            self.assertEqual(result["state"], "succeeded")
            self.assertEqual(
                (root / result["outputs"][0]["path"]).read_bytes(), original
            )

    def test_output_created_during_adapter_run_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            preview = self.prepare_and_confirm(root, job)
            target = root / preview["outputs"][0]

            def create_target_during_run(command, timeout, payload, cwd):
                source = Path(directory) / "adapter-result.png"
                source.write_bytes(b"generated")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"CONCURRENT FILE")
                return {
                    "outputs": [
                        {"target": payload["outputs"][0], "source": str(source)}
                    ]
                }

            with mock.patch.object(
                production_tool, "_run_adapter", side_effect=create_target_during_run
            ), self.assertRaisesRegex(FileExistsError, "appeared"):
                production_tool.run_job(
                    root,
                    job_id="EP001-SHOT001",
                    adapter_config=self.adapter_config(directory),
                )
            self.assertEqual(target.read_bytes(), b"CONCURRENT FILE")

    def test_job_rejects_secrets_wrong_extensions_and_unsafe_outputs(self) -> None:
        cases = (
            ({"api_key": "not-allowed"}, None, "credentials"),
            ({}, "剧集/EP001/制作成果/image/result.mp4", "extension"),
            ({}, "剧集/EP001/result.png", "production"),
            ({}, "输入/production/stolen.png", "production"),
            ({}, "交付/production/result.png", "production"),
            ({}, "../result.png", "unsafe"),
        )
        for parameters, output, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = self.make_project(directory)
                job = self.write_job(root, parameters=parameters, output=output)
                with self.assertRaisesRegex(ValueError, message):
                    production_tool.prepare_job(root, job)

    def test_adapter_config_must_be_external_and_use_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            self.prepare_and_confirm(root, job)
            inside = root / "adapter.json"
            inside.write_text(
                json.dumps(
                    {
                        "adapters": {
                            "fixture": {
                                "command": f"{sys.executable} {FIXTURE_ADAPTER}",
                                "timeout_seconds": 30,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside"):
                production_tool.run_job(
                    root, job_id="EP001-SHOT001", adapter_config=inside
                )

            outside = Path(directory) / "bad-config.json"
            outside.write_bytes(inside.read_bytes())
            with self.assertRaisesRegex(ValueError, "string list"):
                production_tool.run_job(
                    root, job_id="EP001-SHOT001", adapter_config=outside
                )
            self.assertEqual(
                production_tool.job_status(root, job_id="EP001-SHOT001")["state"],
                "confirmed",
            )

    def test_cli_runs_prepare_confirm_execute_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_project(directory)
            job = self.write_job(root)
            config = self.adapter_config(directory)

            prepared = subprocess.run(
                [sys.executable, str(PRODUCTION_SCRIPT), "prepare", str(root), "--job", str(job)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            preview = json.loads(prepared.stdout)
            confirmed = subprocess.run(
                [
                    sys.executable,
                    str(PRODUCTION_SCRIPT),
                    "confirm",
                    str(root),
                    "--job-id",
                    preview["job_id"],
                    "--confirmation",
                    preview["confirmation"],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            executed = subprocess.run(
                [
                    sys.executable,
                    str(PRODUCTION_SCRIPT),
                    "run",
                    str(root),
                    "--job-id",
                    preview["job_id"],
                    "--adapter-config",
                    str(config),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(json.loads(executed.stdout)["state"], "succeeded")
            status = subprocess.run(
                [
                    sys.executable,
                    str(PRODUCTION_SCRIPT),
                    "status",
                    str(root),
                    "--job-id",
                    preview["job_id"],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
