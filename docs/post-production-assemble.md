# 后期顺片（assemble）设计记录：先不开发

- 状态：已定位、暂缓实施；本文只记录结论与接法，不改任何 skill
- 关联：`docs/film-merge-design.md` §8 提到的"没有剪辑与后期层"

## 为什么后期要拆开看

AI 生成片的后期与实拍后期不是一回事：没有素材整理、多机位、同期声对轨这些实拍后期的大头；而剪辑决定
——镜头顺序、每镜时长、台词、配乐进出——本来就写在五文档里，并且已经被 `SHT-16`（集时长账目）、
`VID-13`/`VID-15`（交付分组）、`VID-26`（对白逐字承载）核对过。所以后期分五层，其中三层是机械的：

| 层 | 内容 | 自动化 | 依据 |
|---|---|---|---|
| 顺片 / 粗剪 | 按《分镜.md》顺序与时长拼接 `制作成果/` 片段 | 完全可以 | 顺序与时长是已核对的账目，不需要剪辑判断 |
| 字幕 | 对白字幕轨 | 完全可以，且不需要语音识别 | 剧本对白逐字已知；分轨 TTS 才需要时间戳对齐 |
| 声音底层 | 同轨对白、环境底声、配乐进出 | 大部分可以 | 同轨生成已含对白；配乐意图在《视频提示词.md》时间线音乐章节（`VID-14`） |
| 精剪 / 选条 | 同一镜多次生成里选哪条、切点修帧、转场 | 人做，agent 辅助 | 节奏与情绪权重是创作决定 |
| 调色 / 精混 / 交付 | LUT、肤色保护、混音、交付格式 | 机械部分可自动化 | 渲染队列与格式转换可脚本化，调色本身是人 |

## 三条路线

| 路线 | 适用 | 限制 |
|---|---|---|
| A · 纯脚本 headless：FFmpeg + OpenTimelineIO | 出粗剪看节奏；把时间线交给任何 NLE | 只有硬切与淡入淡出这一档表达力；转场与字幕样式在 NLE 里做 |
| B · 生成剪映草稿：pyJianYingDraft / pyCapCut | 想在剪映里精修 | 剪映 7 以上草稿为加密 JSON，自动导出只支持 6 及以下且限 Windows；macOS 只能生成草稿 |
| C · NLE + MCP：DaVinci Resolve 脚本 API | 电影级调色与混音；agent 做导入、搭时间线、渲染队列 | 脚本 API 覆盖有限；免费版要靠跑在 Resolve 内部的桥接脚本；调色仍是人 |

OpenTimelineIO 的 `.otio` 是 JSON，可再导出 FCPXML（Final Cut）、FCP7 XML（Premiere / Resolve）与 CMX EDL，
一份时间线进任何 NLE；它是三条路线共同的交换层。

## 拟议的 `assemble` 步骤

不新建 skill 目录（`EXPECTED_SKILLS` 是精确集合），挂在核心技能的 `project_tool.py assemble` 下；确定性脚本，
不做创意判断，五文档仍是唯一真相，时间线只是投影。

**输入**

- 《分镜.md》：镜头顺序与 `时长`；
- 《视频提示词.md》：「交付分组」决定哪些片段本来就是一段、时间线音乐章节给配乐进出点；
- 《剧本.md》：对白与 VO/OS 行 → 字幕；
- `剧集/<EP>/制作成果/video/`：片段；
- **选条记录**：同一镜生成多次时，创作者在《分镜.md》该镜下写一行 `- 选用：<项目相对路径>`，脚本只认这一行；
  没有选用行且只有一个候选时取它，多个候选时停下列出——"选哪条"是创作决定，脚本不猜。

**输出**

- `剧集/<EP>/交付/timeline.otio`，以及由它导出的 FCPXML / FCP7 XML / CMX EDL；
- `剧集/<EP>/交付/字幕.srt`（对白按镜头时长与出现顺序分配时间码；同轨对白没有逐字时间戳时按镜头区间均分，
  标为估算）；
- 可选：剪映草稿目录（调 pyJianYingDraft，仅当本机有可用版本）；
- 可选：FFmpeg 粗剪 `rough-cut.mp4`（硬切 + 分组内不切）；
- 全部落在 `交付/`，与 `export` 一样排除私有输入与隐藏运行状态。

**机械核对（都只报告，除第一条外不阻断）**

1. 每个镜头恰好一个被选用的片段文件存在（`structural_invariant`，缺一个就不能顺片）；
2. 片段实际时长与《分镜.md》`时长` 的偏差超过一帧时逐镜报告——生成模型给的片子经常不是整秒；
3. 时间线总时长等于 `SHT-16` 的账目；
4. 交付分组内的成员在时间线上连续且不插入其它镜头。

**规则等级**：顺片本身不产生新的 `structural_invariant`，只复用已登记的账目规则；输出格式与 NLE 选择是
`taste_option`。

## 提效清单（按收益排）

1. 粗剪零手工：几百个片段不用手拖，改一次《分镜.md》重跑一次就是新粗剪；
2. 字幕零 ASR：剧本即字幕；
3. 少剪辑点：同场连续镜头走续接或长容器，本来就少一个切点；
4. 同轨声音：对白随画面生成，只有要换声音演员时才分轨；
5. 抽帧质检：每镜抽首/中/尾三帧拼 contact sheet，作为审查规则允许的"授权观察"形态；
6. 配乐归时间线层：单镜不烧配乐（`VID-14`），整片在 NLE 里一次铺。

## 为什么先不做

- 生成片段还没有真实跑通（沙箱无 key、无 codex），顺片没有输入；
- OpenTimelineIO 是第三方依赖，与"脚本只用标准库"的约束冲突，需要先决定是走可选依赖还是自写最小 OTIO JSON；
- 选条记录的语法要与分镜 owner 商定，避免变成第六份文档。

## 参考项目（名称，不写网址）

pyJianYingDraft / pyCapCut / JianyingDraft.PY（剪映与 CapCut 草稿）；OpenTimelineIO 与 otio-cmx3600-adapter；
ChatOctopus/timeline（FCP、Premiere、Resolve、OTIO 时间线互转）；davinci-resolve-mcp（lordhoell 与 hiteshK03 两个实现）；
6missedcalls/video-editing-skill、OpenMontage、Claude-Code-Video-Toolkit（FFmpeg/Whisper 向的剪辑 skill）；
open-source-cinema 的 Agent-Driven-Editing-2026（"机械的交给 agent，节奏与结构留给人"）。
