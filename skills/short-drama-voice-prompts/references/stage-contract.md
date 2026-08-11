# 音色提示词阶段契约

## 目录

- [运行时预检](#运行时预检)
- [所有权边界](#所有权边界)
- [制作形态需要什么](#制作形态需要什么)
- [声音参考与证据](#声音参考与证据)
- [本阶段规则](#本阶段规则)

本文件是本技能的自包含契约：预检、所有权、形态输入与规则表都在这里，
不需要读取其他技能的文件。

## 运行时预检

进入本阶段前先完成这套轻量预检。它只检查安装完整性、项目事务状态和已记录的精确引用，
不评价创作内容。

1. **验证安装**：从本技能目录的 `suite-ref.json` 解析到逻辑安装路径中的 core，用当前
   环境可用的 Python 3 解释器运行 core 的 `scripts/suite_verify.py`。验证器沿逻辑安装
   路径逐一检查清单中的技能；混装、缺件、额外可执行文件或 hash 不一致时停止写入，
   也不要退回源码检出目录“借用”通过验证的兄弟技能。
2. **先恢复事务，再读状态**：定位项目根目录后，先运行 core 的 `scripts/project_tool.py`
   的 `recover`，再运行 `status`。`recover` 可重复执行；它报告 blocked 时保持创作者文件
   原样并先处理冲突，不要绕过 WAL、手改状态文件或假定上次写入成功。`status` 中的
   accepted/candidate 指针和阻断项是本阶段工作的当前事实。
3. **只通过公开生命周期写入**：负责人用 `publish` 原子发布候选，并给每个外部结构化引用
   提供精确 input hash。上游接受引用不继承候选状态。创作者接受、独立审查与内容修订是
   不同动作。每次修订后重新运行适用的结构校验，并让下游刷新旧 hash。
4. **读共享 JSON/JSONL 时同时声明读了哪几条记录**：`设定集/characters.jsonl` 是全项目
   共享输入，只按整文件 hash 绑定会让后续任何一次角色增补把此前引用过它的音色提示词
   全部标为 `stale`。发布时补 `--input-record <path>=<record-id>`，此后只有被绑定的
   角色记录变化才会影响本产物。

## 所有权边界

- **本阶段拥有**：`设定集/voice-prompt-specs.jsonl` 与 `设定集/voice-prompts.md`——
  音色描述的措辞与取舍；渲染出的 Markdown 是缓存。
- **本阶段继承**：已接受的角色身份与 `voice_direction`、项目语言与提示词语言、
  已接受的制作形态、创作者授权的声音参考引用。
- **本阶段不越权**：不定义或修改声音身份本身；不写单句台词的表演与配音本；
  不写镜头内的音画实现与混音；不改写角色身份、剧情状态或信息权限；
  不生成音频，也不调用任何语音服务。

分层的理由：`$short-drama-assets` 决定**这个人的声音是什么**，本技能决定
**怎么把它说清楚给别人复制**，`$short-drama-write` 决定**这一句怎么说**。
把三者合并，任何一次单句调整都会变成对角色身份的修改。

## 制作形态需要什么

制作形态决定观众通过什么通道认出这个角色，因而决定音色锚点里哪些真的能被听见。
创作者已接受的制作形态由项目层传入，**本技能不加载形态卡，也不自行选择形态**。

形态决定属于 `craft_default`：创作者说明理由即可覆盖。形态不能创造新的
`structural_invariant`，也不能改写角色身份或已接受发音。

| 主要识别通道 | 值得写的锚点 | 写了也听不出的锚点 |
|---|---|---|
| 真人同期声 | 音区、语速习惯、句尾处理、呼吸位置 | 需要后期才成立的音染 |
| 后期配音 | 音色质感、年龄印象、口音范围、专名发音 | 依赖现场空间的混响特征 |
| 合成或克隆 | 少量强稳定锚点、可重复的节奏特征 | 细微情绪层次与即兴处理 |

形态越依赖合成，锚点就要越少越硬——描述给得越多，复现越不稳定。

## 声音参考与证据

- **参考音频能决定什么要逐条写明**：每份参考的用途、可以照搬什么、不可以照搬什么。
  身份参考不自动带来语速与情绪；情绪参考不自动带来音色与口音。
- **关于参考内容的断言需要证据**：对某份参考里“听得到什么”的断言，必须来自创作者或
  参考权利人的可核对说明，或运行环境获授权后形成的输入参考观察记录，并绑定被检查的
  字节。两者都没有时保持 `unverified`。
- **不写服务参数**：模型名、接口字段、任务 ID、网址、供应商参数都不进规格。它们会让
  规格绑定到某一次具体调用，而规格本该比任何一次调用活得久。

## 本阶段规则

### `VOX`

| ID | Class | Knowledge |
|---|---|---|
| VOX-01 | structural_invariant | Every spec binds an accepted character identity and the exact `voice_direction` fields it projects. |
| VOX-02 | structural_invariant | A spec declares `spoken_language` and `prompt_language` separately; the description language never silently changes what the character speaks. |
| VOX-03 | structural_invariant | Accepted pronunciation of proper nouns appears in exactly one spelling across all specs. |
| VOX-04 | structural_invariant | Specs carry no provider parameter, model name, task field, or URL. |
| VOX-05 | reviewed_invariant | Persistent anchors exclude scene-local delivery: breath under stress, one line's stress, temporary volume, and injury-of-the-week stay out of identity. |
| VOX-06 | reviewed_invariant | Each character's spec names at least one anchor distinguishing it from the nearest other character in the same batch, and names that character. |
| VOX-07 | reviewed_invariant | A claim about reference audio requires a creator or reference-owner description, or an authorized input-reference observation bound to the inspected bytes; otherwise admission stays unverified. |
| VOX-08 | reviewed_invariant | A sustained disguise, age span, or altered voice is recorded as a variant with cause and validity range, not by rewriting the base identity. |
| VOX-09 | craft_default | Fewer, harder anchors beat exhaustive description, and more so the more the target pipeline synthesizes. |
| VOX-10 | taste_option | Timbre taste, accent choice, and casting direction remain creator choices; a reviewer may not block delivery on preference. |

规则分级由高到低：`structural_invariant`（结构缺陷，阻断）、
`reviewed_invariant`（需证据判断）、`craft_default`（常用做法，可覆盖）、
`taste_option`（创作者选择，不作缺陷）。创作者已接受的事实优先于本表。
