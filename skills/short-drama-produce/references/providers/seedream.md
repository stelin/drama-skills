# Seedream adapter

Adapter command:

```json
{"command": ["python3", "/absolute/path/provider_adapters.py", "seedream"], "timeout_seconds": 600}
```

Required environment:

- `ARK_API_KEY`: Volcengine Ark API key, the same key the Seedance adapter reads.
- `SEEDREAM_MODEL`: the exact enabled model/endpoint ID, such as the Seedream 5.0 ID the Ark console shows for the
  account. There is intentionally no model default; the adapter never assumes a Seedream release.

Optional environment:

- `SEEDREAM_BASE_URL` (default `https://ark.cn-beijing.volces.com/api/v3`, must remain HTTPS)
- `SEEDREAM_MAX_REFERENCES`: input pictures the configured model accepts, `1`–`14`. The default is `10`, the lowest
  published profile (Seedream 4.0); set `14` for Seedream 4.5 and 5.0.
- `SEEDREAM_OUTPUT_FORMAT_FIELD`: `send` (default) or `omit`. Seedream 5.0 documents `output_format`; a deployment on
  an earlier release omits the field and writes `.jpg` outputs, because those releases return JPEG.

The job must have modality `image` and exactly one `.png`, `.jpg` or `.jpeg` output. The adapter sends JSON to
`POST /images/generations` with `response_format: b64_json`, `sequential_image_generation: disabled` and
`stream: false`, so one job is always one picture and nothing is fetched from a provider URL afterwards. The single
returned `b64_json` image is decoded, checked against the media type the output extension claims, and written to a
private temporary file.

Supported public parameters are `width` plus `height` (compiled to `size` as `WxH`), or `size` as one of `1K`, `2K`,
`3K`, `4K` or an explicit `WxH`, and `watermark` (boolean, default `false`). A size is mandatory: Ark would otherwise
fall back to a square default, and a sheet or keyframe has a canvas the creator chose. An explicit pixel size must keep
its aspect ratio within 1:16–16:1 and its pixel count within 921,600–16,777,216, the union of the published Seedream
envelopes; the configured model still decides inside that range (Seedream 5.0 lite tops out at `3K`, for example).
`seed`, group generation and web search are not exposed.

References: zero to `SEEDREAM_MAX_REFERENCES` PNG/JPEG project files, each at most 10MB, sent inline as
`data:<mime>;base64,<...>` entries of `image` in binding order (one picture as a bare string, several as a list), which
the contract lists alongside a public URL. Seedream has no per-picture role field, so what each reference may and may
not control travels in the reference contract the compiler appends to the prompt in `parameters.prompt_language`,
exactly as for GPT Image 2. Each file's bytes must match the media type its extension claims.

Protocol reference: [Volcengine image generation API](https://www.volcengine.com/docs/82379/1541523).
