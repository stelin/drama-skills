# `voice-prompt-specs.jsonl` 填写模板

每行一个候选规格对象，用于接受前预览；示例值不是默认答案。删除不适用字段，不要添加
语音任务、供应商、模型或接口字段。上游引用默认绑定准确的已接受快照；只有与本对象同次
发布的目标才写 `authority:candidate`。对象接受状态由事务生命周期记录，不能靠改状态字样
伪造。

`persistent_anchors` 与 `not_voice_identity` 必须同时写：前者是不可被临场表演覆盖的
保留集，后者是本来就该随场变化、**不得**被写进身份的项。只写前者，下游无从判断某个
特征是被遗漏还是被有意排除。

```json
{
  "spec_id": "VOX-<stable-id>",
  "status": "candidate",
  "purpose": "casting_reference | synthesis_reference | continuity_check",
  "character_ref": {
    "owner": "short-drama-assets",
    "artifact": "设定集/characters.jsonl",
    "hash": "<sha256>",
    "record_id": "CHAR-<id>"
  },
  "source_refs": [
    {
      "owner": "short-drama-assets",
      "artifact": "设定集/characters.jsonl",
      "hash": "<sha256>",
      "record_id": "CHAR-<id>",
      "field": "/voice_direction/persistent_anchors",
      "role": "identity_anchor | language_range | pronunciation | variant_cause"
    }
  ],
  "spoken_language": "<BCP 47 tag from voice_direction.language>",
  "prompt_language": "en",
  "persistent_anchors": [
    {
      "kind": "register | texture | age_impression | rhythm | accent | signature",
      "text": "<one audible, repeatable trait>",
      "counter_example": "<what would be overdoing it>"
    }
  ],
  "distinction": {
    "nearest_character_ref": {
      "owner": "short-drama-assets",
      "artifact": "设定集/characters.jsonl",
      "hash": "<sha256>",
      "record_id": "CHAR-<other-id>"
    },
    "distinguishing_anchor": "<the trait that tells the two apart by ear>"
  },
  "pronunciation": [
    {"term": "<proper noun>", "accepted_reading": "<the single accepted spelling>"}
  ],
  "not_voice_identity": [
    "<scene-local delivery that must never enter identity>"
  ],
  "variant": {
    "variant_id": "VOX-<id>-<variant>",
    "cause_ref": {
      "owner": "short-drama-write",
      "artifact": "剧集/<EP>/screenplay-index.jsonl",
      "hash": "<sha256>",
      "record_id": "BLK-<id>"
    },
    "validity": {"from": "<EP/SC/BLK>", "until": "<EP/SC/BLK>"},
    "delta": ["<anchors changed relative to base; the rest are inherited>"]
  },
  "reference_admission": {
    "reference_ref": null,
    "status": "unverified | creator_described | observed",
    "may_copy": [],
    "must_not_copy": []
  },
  "prompt_text": "<the copyable prompt body, written in prompt_language>",
  "creator_acceptance": {"status": "pending", "decision_ref": null}
}
```

## 字段说明

| 字段 | 为什么存在 |
|---|---|
| `spoken_language` / `prompt_language` | 角色说什么语言，和描述文字用什么语言，是两件事。合成一个字段会让换描述语言变成换角色语言 |
| `persistent_anchors[].counter_example` | 锚点没有上界时会被越执行越夸张；反例给出上界 |
| `distinction` | 单看每条都合理、放在一起分不出人，是本阶段最常见的失败 |
| `pronunciation` | 专名只能有一种已接受读法；两种拼法只会在成品里被听见 |
| `not_voice_identity` | 让「被排除」与「被遗漏」可区分 |
| `variant` | 伪装、年龄跨度与长期变声不改写基础身份，只记带 cause 与有效范围的差异 |
| `reference_admission` | 没有可核对来源的参考断言保持 `unverified`；负面描述不能代替证据 |
| `prompt_text` | 渲染进 `voice-prompts.md` 的正文；Markdown 是缓存，本字段是权威 |
