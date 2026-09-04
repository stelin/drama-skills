# Codex 桌面端操作手册：从一本小说到出图出片

本篇面向 **Codex 桌面 app**（macOS / Windows），假设你手上已经有一部写好的小说，要把它做成横屏电影或竖屏短剧。
命令级细节（安装脚本、每条校验的读法、adapter 契约）在 [Codex 操作步骤](codex-usage-guide.md) 里，本篇不重复，
只写桌面端怎么操作、以及从小说到成片每一步"说什么、得到什么、看什么"。

桌面 app 与 CLI 共用同一份登录态、同一份 `~/.codex/config.toml`、同一套技能目录和同一份项目 `AGENTS.md`，
所以 CLI 指南里的每一句请求在桌面端原样可用；不同的只有线程、审批和环境变量三件事。app 的界面文案随版本变化，
下文的按钮名以你当前版本为准。

## 目录

- [1. 桌面端准备](#1-桌面端准备)
- [2. 把小说放进项目](#2-把小说放进项目)
- [3. 原著分析：值不值得拆、怎么拆](#3-原著分析值不值得拆怎么拆)
- [4. 故事开发：改编契约与分集地图](#4-故事开发改编契约与分集地图)
- [5. 生产档案：先定目标视频模型](#5-生产档案先定目标视频模型)
- [6. 创作剧本](#6-创作剧本)
- [7. 视觉设定 → 图片提示词 → 分镜 → 视频提示词](#7-视觉设定--图片提示词--分镜--视频提示词)
- [8. 机械核对](#8-机械核对)
- [9. 生产：出图、出视频](#9-生产出图出视频)
- [10. 审查与导出](#10-审查与导出)
- [11. 桌面端的线程编排](#11-桌面端的线程编排)
- [12. 常见问题](#12-常见问题)

## 1. 桌面端准备

### 1.1 安装技能

技能安装与 CLI 完全相同：clone 仓库后在仓库根目录跑一次 [Codex 操作步骤 §1](codex-usage-guide.md#1-安装与验证) 的软链
脚本（同时链到 `~/.agents/skills` 与 `~/.codex/skills`）。桌面 app 不需要另装。

验证：在 app 里新建一个线程，输入 `/skills`，列表里应有十个 `short-drama*`；再输入 `$short-drama`，
应弹出技能补全。没有就检查软链目标、重启 app。

### 1.2 打开项目而不是仓库

app 里"打开文件夹"选**项目目录**（例如 `~/drama/dong-he`），不是 drama-skills 仓库。技能靠用户级目录发现，
与打开的文件夹无关；打开项目目录的好处是线程里的 `@` 文件引用、diff 视图和 `AGENTS.md` 都指向创作文件。

第一次用某个项目时先把它建出来（第 2 节），再在 app 里打开。

### 1.3 线程：选"本地"

新建线程时选**本地**（在项目目录直接工作），不要选 worktree。原因：出图出片的结果、`.short-drama/` 里的生产确认与
运行记录、`制作成果/` 里的媒体都是项目内文件状态，worktree 副本里产生的东西要手工合并回去，媒体还不进 git。

云端任务也不用于生产步骤：云端没有本机 codex 登录态（`codex-imagegen` 用不了）、没有你的 API key、默认无网络。
写剧本、拆资产这类纯文本步骤可以放云端，但改动要同步回本地再跑校验。

### 1.4 审批与沙箱

默认审批模式即可：读文件、改 `剧集/` 下的 Markdown 都在项目内，app 会自动放行或弹一次确认。需要额外批准的只有
两处——`run` 生产步骤要联网（Seedream / Seedance / MiniMax）或启动子进程（`codex-imagegen` 会再起一个 `codex exec`），
以及 Dashboard 的本地服务。弹窗时看清命令再批准；不要为了省事把整个线程切成"完全访问"。

### 1.5 环境变量：桌面 app 看不到你的 shell

从 Dock 启动的 app 不会读 `~/.zshrc` 里的 `export`。所以 `ARK_API_KEY`、`SEEDREAM_MODEL`、`SEEDANCE_MODEL`
这些变量在 app 内的线程里多半是空的。三种处理，任选其一：

| 做法 | 适用 |
|---|---|
| `prepare`、`confirm` 在 app 线程里做，`run` 换到普通终端执行 | 最稳；job 已确认，换终端不影响确认 |
| macOS 用 `launchctl setenv ARK_API_KEY …` 后重启 app | 想全程留在 app 里 |
| 只用 `codex-imagegen` 出图 | 不需要任何 key，只要 app 的登录态 |

任何情况下都不要把 key 写进项目、`AGENTS.md` 或 adapter 配置——adapter 只从进程环境读凭据。

## 2. 把小说放进项目

### 2.1 初始化

在 app 里新建线程，先打开你准备放项目的父目录（或直接在线程里给绝对路径），一句话说清题材、画幅、语言、集数与时长：

```text
$short-drama 初始化一个横屏电影项目《冻河》，16:9，中文提示词，1 本，单本目标 65 秒
```

竖屏短剧则是 `9:16`、集数与单集目标秒数照实说。技能会跑 `project_tool.py init`，得到：

```text
dong-he/
├── short-drama.json      ← 画幅、语言、目标时长、生产档案
├── 输入/                  ← 小说、参考图、参考音频放这里（只读、不交付）
├── 剧集/                  ← 每集五份 Markdown
├── 创作者决策/            ← 已接受的决定
└── 项目开发/              ← 原著分析与开发产物（分析后才出现）
```

然后在 app 里"打开文件夹"选 `dong-he`。

### 2.2 放入小说

把小说文件复制到 `输入/`，例如 `输入/冻河.txt`。三个检查：

- **UTF-8 纯文本**优先；`.docx`/`.epub` 先另存为 txt，索引脚本按原始字节定位，不解析富文本；
- 章节标题独立成行（`第一章 …` / `第12章 …` / `第三回 …`）。没有章节标题也能做，但索引会是空表，
  需要和技能一起手写边界；
- 文件放好后**不要再改**：改了就要重建索引，旧的分析引用会全部失效。

### 2.3 写一份 AGENTS.md

放在项目根目录，app 里每个线程都会读。照 [Codex 操作步骤 §4](codex-usage-guide.md#4-给项目写一份-agentsmd) 的模板，
外加两行原著相关的约定：

```markdown
- 原著：输入/冻河.txt（UTF-8，第N章 分章）；分析产物在 项目开发/source-analysis/，不把原文成段抄进任何文档
- 改编边界：结局与父女关系不可改；配角可合并；开篇位置由我决定
```

## 3. 原著分析：值不值得拆、怎么拆

由 `$short-drama-novel-analyze` 负责，全部产物落在 `项目开发/source-analysis/`。它只读小说、只写分析，
不写剧本、不建资产。短篇或中篇（几万字以内）可以跳过全量拆解，直接进第 4 节把小说当材料交给开发技能。

### 3.1 建索引（S0）

```text
$short-drama-novel-analyze 给 输入/冻河.txt 建章节索引，先告诉我索引有没有问题
```

技能会跑：

```bash
python3 <技能目录>/skills/short-drama-novel-analyze/scripts/novel_index.py index 输入/冻河.txt \
  --out 项目开发/source-analysis/_work/_index.next.json
python3 <技能目录>/skills/short-drama-novel-analyze/scripts/novel_index.py verify \
  项目开发/source-analysis/_work/_index.next.json 输入/冻河.txt
```

看三处：`problems` 必须为空（跳号、重号、正文极少的章、无法解析的章号都会列出来）；`chapter_unit`
应当是你的分章单位（章/回/节）；`long_heading_lines_skipped` 明显偏大说明标题太长被当成了正文。
没问题时技能把索引发布为 `项目开发/source-analysis/_index.json`，它是后面所有引用的唯一切片真源。

### 3.2 快评（S1）：这里会停下来问你

```text
$short-drama-novel-analyze 快评 输入/冻河.txt，先告诉我值不值得全量拆
```

脚本等距抽 12 章（首尾必取，可复现），技能据此写 `triage.md`：故事框架、`screen_ready / needs_carrier / prose_only`
三类比例、开篇替换点、制作负担量级、三处最大改编风险、分集候选量级。第一行是覆盖率，所有结论限于抽样。

**停靠**：技能给出全量拆解的预计耗时，问你继续与否。回复 `继续，全量拆` 或 `够了，直接进开发`。
一开始就想一次跑完，请求里加"一次跑完，不用停"。

### 3.3 逐章提取与聚合（S2–S5）

```text
$short-drama-novel-analyze 继续：全量逐章提取，然后聚合出剧情单元、人物与分集候选
```

技能按批（每批 5–8 章）提取每章的戏剧功能到 `chapters/ch-<N>-extract.md`，跑完覆盖率：

```bash
python3 <技能目录>/skills/short-drama-novel-analyze/scripts/novel_index.py coverage \
  项目开发/source-analysis/_index.json 项目开发/source-analysis/chapters
```

`missing` 非空就补跑；`unmatched_files` 非空是文件名写歪了，改名不重跑。覆盖率不足不进聚合。之后依次得到：

| 产物 | 内容 | 你要看什么 |
|---|---|---|
| `story-units.md` | 有始有终的剧情单元：进入状态、冲突、代价、出去状态 | 单元边界是否和你对这本书的理解一致 |
| `rhythm-and-emotion.md` | 关键信息推进、情绪铺垫→释放→余波、跨章伏笔 | 你最在意的几处情绪点有没有被识别 |
| `characters.md`、`world.md` | 人物归并（带 `unresolved`）与世界规则 | 别名合并有没有错并 |
| `adaptation-value.md` | 哪些单元能直接成立、哪些要换载体、哪些是纯文字快感；开头回填快评被推翻的判断 | 被判成 `prose_only` 的段落你是否同意 |
| `episode-candidates.jsonl` | 按局部戏剧结果切的候选集，带来源 span 与未决项 | 这只是候选，第 4 节才定 |

长书在桌面端的好处：可以开一个线程专跑 S2，同时在另一个线程读 `triage.md`；但两个线程不要同时写
`source-analysis/`。中断了就说 `从 _progress.md 的断点续跑`。

## 4. 故事开发：改编契约与分集地图

由 `$short-drama-develop` 负责，产物在 `项目开发/`：`creative-brief.md`（改编契约）、`story-engine.md`、
`adaptation-map.jsonl`、`episode-map.jsonl`，需要时再加 `director-brief.md` 与情绪曲线。

### 4.1 立改编契约

```text
$short-drama-develop 基于 项目开发/source-analysis/ 的分析立改编契约：结局与父女关系不可改，
配角可合并，开篇从第 7 章仓库夜戏切入；先列不可改承诺、可换载体、可删冗余和未决歧义让我确认
```

技能会先把四类摆出来让你确认，再写 `creative-brief.md`。未决歧义（原文自相矛盾、授权不清）它不会替你定案。
要求它**不复制原文**：`adaptation-map.jsonl` 只记 locator、span、去引用的功能摘要与去向。

### 4.2 故事引擎与分集地图

```text
$short-drama-develop 建故事引擎并做分集地图：1 本 65 秒电影（或：12 集，每集 90 秒竖屏）；
每集记录进入状态、当集追求、阻力、转折、结果、信息释放与交接事实
```

看 `episode-map.jsonl` 的每一行：相邻集能不能精确交接、每集是否先兑现一部分承诺再留下具体的决定或危险。
集数、钩子类型、高潮位置是你的决定；技能不会用固定情节点配方替你填。

### 4.3 电影长片才有的两样

- **导演阐述** `director-brief.md`：`$short-drama-develop 写导演阐述：摄影系统一致、世界坐标、环境色彩与声音策略`。
  它只是候选，接受后由 `$short-drama` 提升到项目权威（`visual_direction`），开发技能不直接改配置。
- **全片情绪曲线**：`$short-drama-develop 给全片画一页情绪曲线`。可选产物，不是分集契约的一部分。

到这里为止都是文字层，随时可以回来改；但一旦第 6 节开始写剧本，改契约就要同步看下游影响。

## 5. 生产档案：先定目标视频模型

写剧本之前就把目标视频模型写进 `production_profile`，否则分镜时长区间与视频提示词方言要重猜：

```text
本项目按 Seedance 2.5 写视频提示词，先把它写进 production_profile
```

技能按对应方言文件开头的推荐档案走三步（发布决策 → 接受 → 设为权威），完成后：

```bash
python3 <技能目录>/skills/short-drama/scripts/project_tool.py status ./dong-he
```

`video_model_profile` 里应出现 `seedance-2.5` 与 `native_duration_seconds` 4–30。选 Seedance 2.0 则是 4–15 秒、
无时间戳；选 MiniMax H3 是英文正文。**出图模型不在档案里**：图片提示词是模型中立的，出图时在 job 里选 adapter
（`codex-imagegen` / `seedream` / `gpt-image-2`），见第 9 节。

## 6. 创作剧本

由 `$short-drama-write` 负责，产物是 `剧集/EP001/剧本.md`，也是后面四份文档的唯一上游。

### 6.1 写第一集

有分集地图时直接点集：

```text
$short-drama-write 按 项目开发/episode-map.jsonl 写完 EP001《冻河》第一本；
进入状态、当集追求、转折与交接事实以地图为准，对白不要抄原著原句
```

没做第 3–4 节（短篇直写）时，把材料说清楚即可：

```text
$short-drama-write 从 输入/冻河.txt 第 5–9 章改写 EP001：下岗司机林正国在封冻的江面上拉煤，女儿开口要学费，
夜里传呼机把他叫去供销社仓库，他把车钥匙放在轮胎上换工钱；65 秒，结局不改
```

### 6.2 交稿时看什么

- 场景标题 `## EP001-SC001 外 · 江边冰面 · 日`；对白 `角色（提示）：台词`；生产标签 `[VO]`、`[OS]`、`[SFX]`、
  `[画面文字]`、`[连续性]`、`[转场]`；
- 每场有可见变化：信息、权力、关系、情绪、物理状态或风险至少一样变了，没变的场应该被删或合并；
- 结尾完成本集的戏剧功能，不强求"又发生一件事"；
- 原著里的内心独白有没有变成可见行为——这是小说改编最常见的洞；
- 目标时长：`$short-drama-write 估一下 EP001 的时长` 会给可数事实（台词字数、动作段），估算是参考不是门禁。

### 6.3 修订与续写

- 定点修订：`$short-drama-write 只改 EP001-SC003 的对白，去掉解释性台词，其余不动`；
- 去 AI 味：`$short-drama-write 给 EP001 做一次去模板感润色，保留我的用词`；
- 下一集：`$short-drama-write 续写 EP002`，技能会读 EP001 的退出状态与地图的交接事实。

剧本被下游引用之后再改，改完要回跑第 8 节的校验——分镜引用的场景 ID、对白逐字承载都会受影响。

## 7. 视觉设定 → 图片提示词 → 分镜 → 视频提示词

四步各一句话，写法、产物与检查点在 [Codex 操作步骤 §5](codex-usage-guide.md#5-逐阶段创作) 逐条列过，这里只给顺序
与小说改编特有的注意点：

| 步 | 请求 | 产物 | 小说改编要多说一句 |
|---|---|---|---|
| 视觉设定 | `$short-drama-assets 从 EP001 拆完人物、地点、道具和本集状态；观看契约电影长片，实拍` | `视觉设定.md` | 人物只从**剧本出现证据**建，不从 `characters.md` 直接搬；子女写 `派生自` |
| 图片提示词 | `$short-drama-image-prompts 为 EP001 写角色板、场景板、道具板` | `图片提示词.md` | 原著的外貌描写要翻成可见参数，不抄原句；派生条目 `参考：` 先写待上游定稿 |
| 分镜 | `$short-drama-storyboard 完成 EP001 正式分镜与冻结关键帧；暂无参考图，按待补处理，不改文生视频` | `分镜.md` | 电影契约下建立镜头、固定机位等待是常规选项；每镜时长落在档案区间 |
| 视频提示词 | `$short-drama-video-prompts 按 Seedance 2.5 把 EP001 逐镜写成视频提示词；我明确选择文生视频` | `视频提示词.md` | 图生视频要先出图再绑 `REF-`（第 9 节），顺序反过来 |

在桌面端，这四步可以放在同一个线程里连续说，也可以图片提示词与分镜各开一个线程并行——它们只读剧本与视觉设定，
互不写对方的文件；但视频提示词要等分镜完成。

## 8. 机械核对

改完任何一份文档都跑，只读不写：

```bash
python3 <技能目录>/skills/short-drama/scripts/creator_markdown_check.py 剧集/EP001 --project-root . --dialogue-coverage
python3 <技能目录>/skills/short-drama-video-prompts/scripts/dialect_check.py 剧集/EP001 --project-root .
```

两条都印 `OK:` 才往下走。每一行的含义与处理见 [Codex 操作步骤 §6](codex-usage-guide.md#6-机械核对)。
在 app 里最省事的写法：`把上面两条校验的输出修掉，不改剧情`。把这两条写进 `AGENTS.md`，线程会自己在改完后跑。

## 9. 生产：出图、出视频

永远三步：`prepare` 预览 → 你看过预览后明确确认 → `run`。adapter 配置放项目外（`~/drama-adapters.json`，
形状见 [Codex 操作步骤 §7.1](codex-usage-guide.md#71-adapter-配置放在项目外)）。

### 9.1 选出图 adapter

| adapter | 需要什么 | 适合 | 限制 |
|---|---|---|---|
| `codex-imagegen` | 只要 app/CLI 的 codex 登录态 | 没有 key、先看画面 | 不能精确指定分辨率、无透明背景、每图一次 `codex exec` |
| `seedream` | `ARK_API_KEY` + `SEEDREAM_MODEL`（Seedream 5.0 的型号 ID，lite 与 pro 各有 ID，以火山方舟控制台为准） | 多参考图身份板、要精确画幅 | 必须在 job 里写 `size`；输出 `.png`/`.jpg`；参考图 ≤ 10MB、张数 ≤ `SEEDREAM_MAX_REFERENCES`（5.0 设 `14`） |
| `gpt-image-2` | `OPENAI_API_KEY` | 已有 OpenAI 账号 | 无参考图走 generation，有参考图走 edit |

Seedream 的 `size` 写法：电影 16:9 用 `"size": "2560x1440"`；3:4 单件档案照用 `"1728x2304"`；1:1 用 `"2048x2048"`；
或者只写 `"2K"` 让模型按提示词里的画幅决定。太小的像素（例如 640×480）会在本地就被拒绝。

### 9.2 出一张角色板（桌面端流程）

在线程里：

```text
$short-drama-produce 预览 EP001 的 IMG-LINZHENGGUO-SHEET 图片任务，adapter 用 seedream，size 2560x1440；等我确认后再执行
```

技能写临时 job 并跑 `prepare`，把预览贴回线程：数量、可复制正文、参考图槽位、参数、输出路径与 adapter。看清楚之后
回复"确认"，技能跑 `confirm`。然后 `run`：

- 在 app 里跑：批准联网/子进程的弹窗即可，前提是线程能看到 `ARK_API_KEY`（第 1.5 节）；
- 或者换到终端：

```bash
python3 <技能目录>/skills/short-drama-produce/scripts/production_tool.py run ./dong-he \
  --job-id EP001-IMG-LINZHENGGUO --adapter-config ~/drama-adapters.json
```

产出落在 `剧集/EP001/制作成果/images/`。提示词、参数、参考图任一变化都会让确认失效，重来 `prepare`。

### 9.3 派生资产的顺序

父母先出图 → 定稿图绑成 `用途：身份` 的 `REF-` → 把子女条目的 `派生状态` 改成 `上游已定稿` → 再出子女身份板
（Seedream 多参考图在这里最有用：父母两张定稿图一起进 `image`）。反过来做，校验器会报 `派生上游未定稿`。

### 9.4 把图绑回文档，再出视频

```text
$short-drama-storyboard EP001 的角色图和场景图已在 剧集/EP001/制作成果/images/ 下，按可见人物、地点、道具绑成带用途的 REF，缺哪张列出来
$short-drama-video-prompts 按 Seedance 2.5 把 EP001 的视频提示词改成图生视频，起始帧用各镜绑定的 REF
$short-drama-produce 预览 EP001 的 MOTION-EP001-001 视频任务，adapter 用 seedance；等我确认后再执行
```

Seedance 的 `run` 要联网并轮询任务，放终端跑最稳。续接段要等上一段实际视频与尾帧存在才能提交。

## 10. 审查与导出

```text
$short-drama-review 审查 EP001 的剧本、分镜与视频提示词，结论写进 审查/EP001-审查.md
```

审查只写问题、影响与修订要求；改完再点名复审。全部完成后导出到项目外：

```bash
python3 <技能目录>/skills/short-drama/scripts/project_tool.py export ./dong-he --out ../dong-he-delivery
```

导出包含五份文档与 `制作成果/`，附清单与校验和，排除 `输入/`（你的小说不会被带出去）、`交付/` 与 `.short-drama/`。

## 11. 桌面端的线程编排

| 线程 | 内容 | 备注 |
|---|---|---|
| `分析` | 第 3 节全部 | 长书跑 S2 时可能很久，单独一个线程别被别的对话打断 |
| `开发` | 第 4–5 节 | 契约确认要你来回几轮，留在同一线程里上下文最完整 |
| `EP001 文本` | 第 6–8 节 | 一集一个线程；写 EP002 时新开，让它自己读 EP001 的退出状态 |
| `EP001 出图` | 第 9.1–9.3 节 | 可与 `EP002 文本` 并行；不要与同一集的文本线程同时改文档 |
| `EP001 出片` | 第 9.4 节 | 等出图与绑定完成后开 |

三条原则：一个线程只改一集的文档；两个线程不同时写同一份文件；生产确认在哪个线程 `prepare`，就在哪个线程确认。
Automations（定时任务）适合每天跑第 8 节的两条校验并把结果贴回来，不要把 `run` 放进去——生产必须有你看过预览之后的本次确认。

## 12. 常见问题

| 现象 | 处理 |
|---|---|
| `/skills` 里没有 `short-drama*` | 软链没建成或装错目录；`ls -l ~/.agents/skills ~/.codex/skills`，重启 app |
| 线程说找不到 `ARK_API_KEY` | 第 1.5 节：`run` 换终端，或 `launchctl setenv` 后重启 app |
| 索引 `problems` 里一堆"正文极少的章" | 多半是目录残留或卷首页；让技能跳过或手写边界 |
| 快评说"值得拆"但你不同意 | 快评是可被推翻的假设；直接说"跳过全量，按我的判断进开发" |
| `adaptation-map.jsonl` 里出现原文整句 | 要求技能改成 locator + 功能摘要；输入不能被带进开发层 |
| 剧本对白全是原著原句 | 让写作技能"对白重写为可表演的争取/回避，不抄原句"，小说对白通常不可直接上口 |
| 分镜仍按竖屏节奏切 | 《视觉设定.md》「项目视觉方向」缺 `观看契约：电影长片` |
| `seedream` 报 `missing_model` | 没设 `SEEDREAM_MODEL`；`invalid_request` 多半是 job 没写 `size` 或输出不是 `.png/.jpg` |
| 想换视频模型 | 项目级：改 `production_profile` 并按新方言重写《视频提示词.md》；换出图模型只是换 adapter 名 |
| worktree 线程里出的图找不到 | 在 worktree 副本里；把媒体拷回主目录，以后线程选"本地" |

样例项目：[《冻河》第一本](../examples/creator-first-film/)（横屏电影，含全部五份文档）。
