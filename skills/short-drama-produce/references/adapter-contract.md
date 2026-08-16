# Adapter Contract

## Job file

```json
{
  "schema_version": "1.0",
  "job_id": "EP001-SHOT001-image",
  "modality": "image",
  "adapter": "studio-image",
  "prompt": "the complete prompt sent to production",
  "source": "剧集/EP001/storyboard/keyframe-prompts.md",
  "references": ["输入/approved-character-reference.png"],
  "outputs": ["剧集/EP001/制作成果/images/SHOT001.png"],
  "parameters": {"width": 1080, "height": 1920},
  "overwrite": false
}
```

- `modality`: `image`, `video`, or `tts`.
- `source`: optional current project text/spec that owns the prompt.
- `references`: zero to sixteen current project files actually sent to production.
- `outputs`: one to sixteen unique paths rooted at top-level `production/` or
  `剧集|episodes/<EP>/制作成果|production/`; extensions must match the modality.
  A nested directory merely named `production` does not grant write access to
  protected input or delivery trees.
- `parameters`: provider-neutral public settings only. Secret-like keys are rejected.
- `overwrite`: must be explicitly true to replace an existing result.

`prepare` records internal digests of source/reference bytes and returns the exact confirmation phrase. Callers never
calculate those digests. A changed input requires prepare and confirmation again.

## Adapter config

Keep this file outside the project:

```json
{
  "adapters": {
    "studio-image": {
      "command": ["python3", "/opt/studio/image_adapter.py"],
      "timeout_seconds": 600
    }
  }
}
```

`command` is an argv array, never a shell string. Timeout is 1–3600 seconds. Do not put credentials in this file;
let the adapter read its environment or operating-system credential store.

## Adapter stdin

The adapter receives the confirmed job plus:

- `run_id`: unique attempt ID;
- `project_root`: local absolute path to a private run snapshot containing only
  the exact confirmed source/reference bytes. It is not the live project and is
  removed after the attempt.

It may translate provider-neutral parameters into its chosen SDK/API. The suite deliberately does not prescribe a
provider, model name, polling protocol, or upload mechanism.

## Adapter stdout

On success, write one bounded JSON object to stdout:

```json
{
  "outputs": [
    {
      "target": "剧集/EP001/制作成果/images/SHOT001.png",
      "source": "/temporary/adapter/result.png"
    }
  ],
  "provider_job_id": "optional-public-id"
}
```

Targets must appear in exactly the confirmed order. Sources must be local regular files, not symlinks. The tool copies
them into the project, records size/media type/checksum, and never stores adapter stdout/stderr or environment values.

A nonzero exit, timeout, malformed response or mismatched output marks the run failed. Because the adapter may have
submitted paid work before failing locally, confirmation is consumed as soon as execution starts; retry only after a
new creator confirmation.
