#!/usr/bin/env python3
"""Prepare and execute explicitly confirmed short-drama media jobs.

The suite does not embed provider clients. A configured external adapter receives
one bounded JSON job on stdin and returns local output files on stdout. The
adapter is launched without a shell and only after a confirmation bound to the
exact job and current project inputs.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "short-drama-produce needs Python {}.{} or newer".format(*MINIMUM_PYTHON)
    )

PROJECT_FILE = "short-drama.json"
PRODUCTION_ROOT = Path(".short-drama/production")
JOB_SCHEMA = "1.0"
JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
MAX_JOB_BYTES = 256 * 1024
MAX_ADAPTER_RESPONSE_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 200 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 3600
ALLOWED_JOB_KEYS = {
    "schema_version",
    "job_id",
    "modality",
    "adapter",
    "prompt",
    "source",
    "references",
    "outputs",
    "parameters",
    "overwrite",
}
SECRET_KEYS = {
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "access_token",
    "api_key",
    "apikey",
}
MEDIA_EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".webp"},
    "video": {".mp4", ".mov", ".webm"},
    "tts": {".wav", ".mp3", ".m4a", ".aac", ".flac", ".opus"},
}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".opus": "audio/ogg",
}


class ConfirmationRequiredError(RuntimeError):
    """The exact current job has not been explicitly confirmed."""


class AdapterError(RuntimeError):
    """A configured media adapter failed or broke its output contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def find_project(start: Path) -> Path:
    candidate = start.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / PROJECT_FILE).is_file():
            return directory
    raise FileNotFoundError(f"no {PROJECT_FILE} found from {start}")


def _relative_path(value: object, *, output: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("project paths must be strings")
    raw = value.replace("\\", "/")
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe project-relative path: {value}")
    if pure.parts[0].casefold() == ".short-drama" or pure.name.casefold() == PROJECT_FILE:
        raise ValueError(f"operational project path is not allowed: {value}")
    if output:
        parts = pure.parts
        top_level_production = len(parts) >= 2 and parts[0].casefold() == "production"
        episode_production = (
            len(parts) >= 4
            and parts[0] in {"剧集", "episodes"}
            and re.fullmatch(r"EP\d{3,}", parts[1], re.IGNORECASE) is not None
            and parts[2] in {"制作成果", "production"}
        )
        if not top_level_production and not episode_production:
            raise ValueError(
                "media outputs must use top-level production/ or "
                "剧集|episodes/<EP>/制作成果|production/"
            )
    return pure.as_posix()


def _project_file(root: Path, relative: str, *, create_parent: bool = False) -> Path:
    target = root / relative
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        if current.exists() and (current.is_symlink() or not current.is_dir()):
            raise ValueError(f"unsafe project directory: {part}")
        if create_parent and not current.exists():
            current.mkdir()
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise ValueError(f"unsafe project file: {relative}")
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError(f"path escapes project root: {relative}")
    return target


def _is_link_or_reparse(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


@contextlib.contextmanager
def _open_project_input(root: Path, relative: str) -> Iterator[BinaryIO]:
    """Open one regular project input without following path components on POSIX."""
    parts = PurePosixPath(relative).parts
    if not parts:
        raise ValueError("job input path is empty")
    if os.name != "nt" and os.open in os.supports_dir_fd:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(root, directory_flags)
        file_fd: int | None = None
        try:
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    directory_flags | nofollow,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(
                parts[-1], os.O_RDONLY | nofollow, dir_fd=directory_fd
            )
            details = os.fstat(file_fd)
            if not stat.S_ISREG(details.st_mode):
                raise ValueError(f"job input is not a regular file: {relative}")
            with os.fdopen(file_fd, "rb", closefd=True) as handle:
                file_fd = None
                yield handle
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"job input is missing: {relative}") from exc
        except OSError as exc:
            raise ValueError(f"unsafe job input path: {relative}") from exc
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory_fd)
        return

    path = root
    for part in parts:
        path /= part
        try:
            details = path.lstat()
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"job input is missing: {relative}") from exc
        if _is_link_or_reparse(details):
            raise ValueError(f"unsafe job input path: {relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"job input escapes project root: {relative}")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"job input is not a regular file: {relative}")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError(f"job input changed while opening: {relative}")
        yield handle


def _hash_project_file(root: Path, relative: str) -> str:
    digest = hashlib.sha256()
    size = 0
    with _open_project_input(root, relative) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_INPUT_BYTES:
                raise ValueError(f"job input exceeds the size limit: {relative}")
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_inputs(
    root: Path, job: Mapping[str, Any], snapshot_root: Path
) -> None:
    inputs = job.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ConfirmationRequiredError("stored job inputs are invalid")
    total = 0
    for relative_value, expected_value in inputs.items():
        relative = _relative_path(relative_value)
        if not isinstance(expected_value, str) or re.fullmatch(
            r"[0-9a-f]{64}", expected_value
        ) is None:
            raise ConfirmationRequiredError("stored job input hash is invalid")
        target = snapshot_root.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        try:
            with _open_project_input(root, relative) as incoming, target.open(
                "xb"
            ) as outgoing:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_INPUT_BYTES or total > MAX_TOTAL_INPUT_BYTES:
                        raise ConfirmationRequiredError(
                            "job inputs exceed the production size limit"
                        )
                    digest.update(chunk)
                    outgoing.write(chunk)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ConfirmationRequiredError(
                "job inputs changed; prepare and confirm again"
            ) from exc
        if digest.hexdigest() != expected_value:
            raise ConfirmationRequiredError(
                "job inputs changed; prepare and confirm again"
            )


def _canonical(document: object) -> bytes:
    return json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    _atomic_bytes(path, _canonical(document) + b"\n")


@contextlib.contextmanager
def _project_lock(root: Path) -> Iterator[None]:
    lock_path = root / ".short-drama/production.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            locking = getattr(msvcrt, "locking")
            lock = getattr(msvcrt, "LK_LOCK")
            unlock = getattr(msvcrt, "LK_UNLCK")
            locking(handle.fileno(), lock, 1)
            try:
                yield
            finally:
                handle.seek(0)
                locking(handle.fileno(), unlock, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _job_key(job_id: str) -> str:
    return sha256_bytes(job_id.encode("utf-8"))[:24]


def _job_path(root: Path, job_id: str) -> Path:
    return root / PRODUCTION_ROOT / "jobs" / f"{_job_key(job_id)}.json"


def _confirmation_path(root: Path, job_id: str) -> Path:
    return root / PRODUCTION_ROOT / "confirmations" / f"{_job_key(job_id)}.json"


def _run_directory(root: Path, job_id: str) -> Path:
    return root / PRODUCTION_ROOT / "runs" / _job_key(job_id)


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in SECRET_KEYS or _contains_secret_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret_key(child) for child in value)
    return False


def _string_list(value: object, *, label: str, limit: int = 32) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string list")
    if len(value) > limit:
        raise ValueError(f"{label} has too many entries")
    return list(value)


def _normalize_job(root: Path, raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) - ALLOWED_JOB_KEYS:
        raise ValueError("job contains unsupported fields")
    if raw.get("schema_version", JOB_SCHEMA) != JOB_SCHEMA:
        raise ValueError("unsupported job schema")
    job_id = raw.get("job_id")
    if not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None:
        raise ValueError("job_id must be a portable 1-80 character identifier")
    modality = raw.get("modality")
    if modality not in MEDIA_EXTENSIONS:
        raise ValueError("modality must be image, video, or tts")
    adapter = raw.get("adapter")
    if not isinstance(adapter, str) or JOB_ID_RE.fullmatch(adapter) is None:
        raise ValueError("adapter must be a portable profile name")
    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
        raise ValueError("prompt must be non-empty and at most 100000 characters")
    source_raw = raw.get("source")
    source = _relative_path(source_raw) if source_raw is not None else None
    references = [
        _relative_path(path)
        for path in _string_list(raw.get("references", []), label="references", limit=16)
    ]
    outputs = [
        _relative_path(path, output=True)
        for path in _string_list(raw.get("outputs"), label="outputs", limit=16)
    ]
    if not outputs or len(set(outputs)) != len(outputs):
        raise ValueError("outputs must contain unique target paths")
    for output_path in outputs:
        if PurePosixPath(output_path).suffix.casefold() not in MEDIA_EXTENSIONS[str(modality)]:
            raise ValueError(f"output extension does not match {modality}: {output_path}")
        _project_file(root, output_path)
    parameters = raw.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be an object")
    if _contains_secret_key(parameters):
        raise ValueError("job parameters must not contain credentials or secrets")
    if len(_canonical(parameters)) > 64 * 1024:
        raise ValueError("job parameters are too large")
    input_paths = ([source] if source is not None else []) + references
    if len(set(input_paths)) != len(input_paths):
        raise ValueError("source and references must be unique")
    input_hashes = {path: _hash_project_file(root, path) for path in input_paths}
    execution = {
        "schema_version": JOB_SCHEMA,
        "job_id": job_id,
        "modality": modality,
        "adapter": adapter,
        "prompt": prompt,
        "source": source,
        "references": references,
        "outputs": outputs,
        "parameters": dict(parameters),
        "overwrite": raw.get("overwrite", False),
        "inputs": input_hashes,
    }
    if not isinstance(execution["overwrite"], bool):
        raise ValueError("overwrite must be a boolean")
    execution["fingerprint"] = sha256_bytes(_canonical(execution))
    execution["prepared_at"] = utc_now()
    return execution


def prepare_job(root: Path, job_file: Path) -> dict[str, Any]:
    root = find_project(root)
    if job_file.stat().st_size > MAX_JOB_BYTES:
        raise ValueError("job file is too large")
    raw = json.loads(job_file.read_text(encoding="utf-8"))
    job = _normalize_job(root, raw)
    with _project_lock(root):
        running = _latest_run(root, str(job["job_id"]))
        if running and running.get("status") == "running":
            raise RuntimeError("this job is already running")
        _atomic_json(_job_path(root, str(job["job_id"])), job)
        try:
            _confirmation_path(root, str(job["job_id"])).unlink()
        except FileNotFoundError:
            pass
    return _preview(job)


def _read_job(root: Path, job_id: str) -> dict[str, Any]:
    if JOB_ID_RE.fullmatch(job_id) is None:
        raise ValueError("invalid job_id")
    path = _job_path(root, job_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("job_id") != job_id:
        raise ValueError("stored job is invalid")
    return document


def _preview(job: Mapping[str, Any]) -> dict[str, Any]:
    confirmation = f"CONFIRM {job['job_id']} {str(job['fingerprint'])[:12]}"
    return {
        "job_id": job["job_id"],
        "modality": job["modality"],
        "adapter": job["adapter"],
        "count": len(job["outputs"]),
        "prompt": job["prompt"],
        "source": job["source"],
        "references": job["references"],
        "outputs": job["outputs"],
        "parameters": job["parameters"],
        "overwrite": job["overwrite"],
        "confirmation": confirmation,
        "state": "needs_confirmation",
    }


def confirm_job(root: Path, *, job_id: str, confirmation: str) -> dict[str, Any]:
    root = find_project(root)
    with _project_lock(root):
        job = _read_job(root, job_id)
        expected = _preview(job)["confirmation"]
        if confirmation != expected:
            raise ConfirmationRequiredError("confirmation does not match the exact current job")
        receipt = {
            "schema_version": JOB_SCHEMA,
            "job_id": job_id,
            "fingerprint": job["fingerprint"],
            "confirmed_at": utc_now(),
            "consumed_at": None,
            "run_id": None,
        }
        _atomic_json(_confirmation_path(root, job_id), receipt)
    return {"job_id": job_id, "state": "confirmed"}


def _inputs_current(root: Path, job: Mapping[str, Any]) -> bool:
    inputs = job.get("inputs")
    if not isinstance(inputs, Mapping):
        return False
    try:
        return all(_hash_project_file(root, str(path)) == digest for path, digest in inputs.items())
    except (FileNotFoundError, OSError, ValueError):
        return False


def _load_adapter(config_path: Path, profile: str, root: Path) -> tuple[list[str], int]:
    resolved = config_path.expanduser().resolve()
    if resolved.is_relative_to(root):
        raise ValueError("adapter config must live outside the project")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    adapters = document.get("adapters") if isinstance(document, Mapping) else None
    selected = adapters.get(profile) if isinstance(adapters, Mapping) else None
    if not isinstance(selected, Mapping) or set(selected) - {"command", "timeout_seconds"}:
        raise ValueError(f"adapter profile is missing or invalid: {profile}")
    command = _string_list(selected.get("command"), label="adapter command", limit=32)
    if not command or any(not part for part in command):
        raise ValueError("adapter command must be a non-empty argv list")
    timeout = selected.get("timeout_seconds", 300)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"adapter timeout must be 1-{MAX_TIMEOUT_SECONDS} seconds")
    return command, timeout


def _run_adapter(command: list[str], timeout: int, payload: Mapping[str, Any], root: Path) -> dict[str, Any]:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            completed = subprocess.run(
                command,
                input=_canonical(payload),
                stdout=stdout,
                stderr=stderr,
                cwd=root,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError("adapter timed out; confirmation was consumed") from exc
        except OSError as exc:
            raise AdapterError("adapter could not be started; confirmation was consumed") from exc
        if completed.returncode != 0:
            raise AdapterError(f"adapter exited with code {completed.returncode}; confirmation was consumed")
        size = stdout.tell()
        if size > MAX_ADAPTER_RESPONSE_BYTES:
            raise AdapterError("adapter response is too large; confirmation was consumed")
        stdout.seek(0)
        try:
            response = json.loads(stdout.read().decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AdapterError("adapter returned invalid JSON; confirmation was consumed") from exc
    if not isinstance(response, dict):
        raise AdapterError("adapter response must be an object; confirmation was consumed")
    return response


def _validate_adapter_outputs(job: Mapping[str, Any], response: Mapping[str, Any]) -> list[tuple[str, Path]]:
    entries = response.get("outputs")
    if not isinstance(entries, list) or not all(isinstance(entry, Mapping) for entry in entries):
        raise AdapterError("adapter outputs are invalid; confirmation was consumed")
    result: list[tuple[str, Path]] = []
    for entry in entries:
        if set(entry) != {"target", "source"}:
            raise AdapterError("adapter output fields are invalid; confirmation was consumed")
        target = entry.get("target")
        source = entry.get("source")
        if not isinstance(target, str) or not isinstance(source, str):
            raise AdapterError("adapter output paths are invalid; confirmation was consumed")
        path = Path(source)
        try:
            details = path.lstat()
        except OSError as exc:
            raise AdapterError("adapter output file is missing; confirmation was consumed") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise AdapterError("adapter output file is unsafe; confirmation was consumed")
        if details.st_size > MAX_OUTPUT_BYTES:
            raise AdapterError("adapter output file is too large; confirmation was consumed")
        result.append((target, path))
    expected = list(job["outputs"])
    if [target for target, _ in result] != expected:
        raise AdapterError("adapter outputs do not match the confirmed targets; confirmation was consumed")
    return result


def _copy_output(source: Path, target: Path, *, overwrite: bool) -> tuple[str, int]:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        try:
            before = source.lstat()
        except OSError as exc:
            raise AdapterError(
                "adapter output file is missing; confirmation was consumed"
            ) from exc
        if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
            raise AdapterError("adapter output file is unsafe; confirmation was consumed")
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            os.close(descriptor)
            raise AdapterError("adapter output changed while opening; confirmation was consumed")
        with os.fdopen(descriptor, "rb", closefd=True) as incoming, temporary.open(
            "xb"
        ) as outgoing:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                size += len(chunk)
                if size > MAX_OUTPUT_BYTES:
                    raise AdapterError("adapter output exceeded the size limit")
                digest.update(chunk)
                outgoing.write(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"output appeared while production was running: {target.name}"
                ) from exc
            temporary.unlink()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return digest.hexdigest(), size


def _latest_run(root: Path, job_id: str) -> dict[str, Any] | None:
    directory = _run_directory(root, job_id)
    if not directory.is_dir():
        return None
    paths = sorted(directory.glob("*.json"))
    if not paths:
        return None
    value = json.loads(paths[-1].read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _write_run(root: Path, job_id: str, run: Mapping[str, Any]) -> None:
    _atomic_json(_run_directory(root, job_id) / f"{run['run_id']}.json", run)


def run_job(root: Path, *, job_id: str, adapter_config: Path) -> dict[str, Any]:
    root = find_project(root)
    with tempfile.TemporaryDirectory(prefix="short-drama-inputs-") as directory:
        snapshot_root = Path(directory)
        with _project_lock(root):
            job = _read_job(root, job_id)
            command, timeout = _load_adapter(adapter_config, str(job["adapter"]), root)
            receipt_path = _confirmation_path(root, job_id)
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise ConfirmationRequiredError("job needs explicit confirmation") from exc
            if (
                not isinstance(receipt, dict)
                or receipt.get("fingerprint") != job.get("fingerprint")
                or receipt.get("consumed_at") is not None
            ):
                raise ConfirmationRequiredError("job needs a new explicit confirmation")
            for output in job["outputs"]:
                target = _project_file(root, output)
                if target.exists() and not job["overwrite"]:
                    raise FileExistsError(f"output exists and overwrite is false: {output}")
            _snapshot_inputs(root, job, snapshot_root)
            run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
            receipt["consumed_at"] = utc_now()
            receipt["run_id"] = run_id
            _atomic_json(receipt_path, receipt)
            run = {
                "schema_version": JOB_SCHEMA,
                "run_id": run_id,
                "job_id": job_id,
                "fingerprint": job["fingerprint"],
                "modality": job["modality"],
                "adapter": job["adapter"],
                "status": "running",
                "started_at": utc_now(),
                "finished_at": None,
                "outputs": [],
            }
            _write_run(root, job_id, run)

        payload = {key: job[key] for key in ALLOWED_JOB_KEYS if key in job}
        payload.update({"run_id": run_id, "project_root": str(snapshot_root)})
        try:
            response = _run_adapter(command, timeout, payload, root)
            adapter_outputs = _validate_adapter_outputs(job, response)
            written: list[dict[str, Any]] = []
            with _project_lock(root):
                for target_name, source in adapter_outputs:
                    target = _project_file(root, target_name, create_parent=True)
                    digest, size = _copy_output(
                        source, target, overwrite=bool(job["overwrite"])
                    )
                    written.append(
                        {
                            "path": target_name,
                            "media_type": MEDIA_TYPES[PurePosixPath(target_name).suffix.casefold()],
                            "bytes": size,
                            "sha256": digest,
                        }
                    )
                run["status"] = "succeeded"
                run["finished_at"] = utc_now()
                run["outputs"] = written
                provider_job_id = response.get("provider_job_id")
                if isinstance(provider_job_id, str) and len(provider_job_id) <= 200:
                    run["provider_job_id"] = provider_job_id
                _write_run(root, job_id, run)
        except Exception:
            with _project_lock(root):
                run["status"] = "failed"
                run["finished_at"] = utc_now()
                _write_run(root, job_id, run)
            raise
    return {
        "job_id": job_id,
        "run_id": run_id,
        "state": "succeeded",
        "outputs": run["outputs"],
    }


def job_status(root: Path, *, job_id: str) -> dict[str, Any]:
    root = find_project(root)
    job = _read_job(root, job_id)
    latest = _latest_run(root, job_id)
    if not _inputs_current(root, job):
        state = "needs_reconfirmation"
    else:
        try:
            receipt = json.loads(_confirmation_path(root, job_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            receipt = None
        if latest and latest.get("status") == "running":
            state = "running"
        elif latest and latest.get("status") in {"succeeded", "failed"}:
            state = str(latest["status"])
        elif isinstance(receipt, Mapping) and receipt.get("consumed_at") is None:
            state = "confirmed"
        else:
            state = "needs_confirmation"
    return {
        "job_id": job_id,
        "modality": job["modality"],
        "adapter": job["adapter"],
        "outputs": job["outputs"],
        "state": state,
        "latest_run": latest,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run confirmed short-drama media jobs.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Validate and preview a media job.")
    prepare.add_argument("project")
    prepare.add_argument("--job", required=True)
    confirm = commands.add_parser("confirm", help="Confirm the exact prepared job.")
    confirm.add_argument("project")
    confirm.add_argument("--job-id", required=True)
    confirm.add_argument("--confirmation", required=True)
    run = commands.add_parser("run", help="Execute a confirmed job through an adapter.")
    run.add_argument("project")
    run.add_argument("--job-id", required=True)
    run.add_argument("--adapter-config", required=True)
    status = commands.add_parser("status", help="Show one media job state.")
    status.add_argument("project")
    status.add_argument("--job-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_job(Path(args.project), Path(args.job))
        elif args.command == "confirm":
            result = confirm_job(
                Path(args.project), job_id=args.job_id, confirmation=args.confirmation
            )
        elif args.command == "run":
            result = run_job(
                Path(args.project),
                job_id=args.job_id,
                adapter_config=Path(args.adapter_config),
            )
        else:
            result = job_status(Path(args.project), job_id=args.job_id)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
