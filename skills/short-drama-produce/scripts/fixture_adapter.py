#!/usr/bin/env python3
"""Offline adapter fixture for image, video, and TTS production tests."""

from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import tempfile
import wave
from pathlib import Path

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "short-drama-produce fixture needs Python {}.{} or newer".format(
            *MINIMUM_PYTHON
        )
    )

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()
    job = json.load(sys.stdin)
    if args.fail:
        return 7
    directory = Path(tempfile.mkdtemp(prefix="short-drama-fixture-"))
    outputs = []
    for index, target in enumerate(job["outputs"]):
        suffix = Path(target).suffix.lower()
        path = directory / f"output-{index}{suffix}"
        if job["modality"] == "image":
            path.write_bytes(PNG)
        elif job["modality"] == "video":
            path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 24)
        else:
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(struct.pack("<h", 0) * 80)
        outputs.append({"target": target, "source": str(path)})
    json.dump({"outputs": outputs, "provider_job_id": "fixture-local"}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
