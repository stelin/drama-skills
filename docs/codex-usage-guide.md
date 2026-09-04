# 在 Codex 里使用本套件：从安装到成片的操作步骤

面向第一次上手的创作者。全文以 Codex CLI 为准；Claude Code 只有两处不同：调用写法 `$short-drama` 改成
`/short-drama`，项目说明文件 `AGENTS.md` 改成 `CLAUDE.md`。流程本身见
[电影长片全流程](film-workflow.md) 与 [漫剧全流程](comic-drama-workflow.md)，本文只讲"手要怎么动"。

## 目录

- [0. 前置条件](#0-前置条件)
- [1. 安装与验证](#1-安装与验证)
- [2. 新建项目](#2-新建项目)
- [3. 写生产档案：目标模型](#3-写生产档案目标模型)
- [4. 给项目写一份 AGENTS.md](#4-给项目写一份-agentsmd)
- [5. 逐阶段创作](#5-逐阶段创作)
- [6. 机械核对](#6-机械核对)
- [7. 生产：预览、确认、执行](#7-生产预览确认执行)
- [8. 派生资产的出图顺序](#8-派生资产的出图顺序)
- [9. 审查与导出](#9-审查与导出)
- [10. 常见问题](#10-常见问题)

## 0. 前置条件

| 项 | 要求 | 检查方法 |
|---|---|---|
| Codex CLI | 已安装并登录 | `codex --version`；在任意目录跑 `codex` 能进入会话 |
| Python | 3.9 或更新，只用标准库 | `python3 --version`；macOS 自带的即可 |
| 本仓库 | 已 clone 到本机 | `git clone` 后进入目录，`ls skills` 能看到十个技能目录 |
| 出图 | 走 `codex-imagegen` 时不需要任何 API key，只要上面的 codex 登录态 | — |
| 出视频 | Seedance 2.5 需要 `ARK_API_KEY` 与 `SEEDANCE_MODEL`；MiniMax H3 需要 `MINIMAX_API_KEY` 与模型配置 | 见 `skills/short-drama-produce/references/providers/` |

Codex 的技能目录是 `${CODEX_HOME:-$HOME/.codex}/skills`；项目级说明文件是 `AGENTS.md`（Codex 每次会话都会读）。

## 1. 安装与验证

在仓库根目录执行（软链而不是复制：以后 `git pull` 立刻生效）：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
for skill in skills/*; do
  ln -sfn "$PWD/$skill" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")"
done
ls -l "${CODEX_HOME:-$HOME/.codex}/skills"
```

三步验证：

1. 每个技能的离线自检：`python3 skills/short-drama/scripts/selftest.py`（其余技能同样有 `scripts/selftest.py`；只在安装、升级或排障时跑）。
2. 重启 Codex 会话，输入 `$short-drama`，应能看到技能被识别（Codex 读取每个技能目录里的 `agents/openai.yaml`）。
3. 用示例跑一次两条校验，确认 Python 与路径都正常：

```bash
python3 skills/short-drama/scripts/creator_markdown_check.py examples/creator-first-film/剧集/EP001 \
  --project-root examples/creator-first-film --dialogue-coverage
python3 skills/short-drama-video-prompts/scripts/dialect_check.py examples/creator-first-film/剧集/EP001 \
  --project-root examples/creator-first-film
```

两条都应打印 `OK:`。

## 2. 新建项目

在你放项目的目录打开 Codex，用自然语言说清画幅、语言、集数与目标时长：

```text
$short-drama 初始化一个横屏电影项目《冻河》，16:9，中文提示词，1 本，单本目标 65 秒
```

技能会替你运行（也可以自己敲）：

```bash
python3 <技能目录>/skills/short-drama/scripts/project_tool.py init ./dong-he --title "冻河" \
  --language zh-CN --prompt-language zh-CN --aspect-ratio 16:9 --episode-count 1 --target-seconds 65
```

得到的目录只有配置与空目录，不预建任何文档：

```text
dong-he/
├── short-drama.json      ← 项目配置（画幅、语言、目标时长、生产档案）
├── 输入/                  ← 你提供的原著、参考图、参考音频
├── 剧集/                  ← 每集五份 Markdown 写在 剧集/EP001/ 下
├── 创作者决策/            ← 已接受的决定记录
└── 审查/                  ← 点名审查时才有
```

`short-drama.json` 里 `target_seconds_per_episode` 是计划不是门槛：校验器只报告差值。

## 3. 写生产档案：目标模型

会话里点名模型不落档案，下一轮就会退回通用路径。所以第一件事就是把它写进 `production_profile`：

```text
本项目按 Seedance 2.5 写视频提示词，先把它写进 production_profile
```

技能会按 `skills/short-drama-video-prompts/references/seedance-2.5.md` 开头的推荐档案走三步
（发布决策记录 → 接受 → 设为权威），完成后用 `status` 复核：

```bash
python3 <技能目录>/skills/short-drama/scripts/project_tool.py status ./dong-he
```

看到 `video_model_profile` 里有 `seedance-2.5`、`native_duration_seconds` 为 4–30 秒即可。这一步决定了三件
事：视频正文语言、每镜时长的合法区间、以及 `dialect_check.py` 按哪套方言对账。

## 4. 给项目写一份 AGENTS.md

放在项目根目录，Codex 每次会话都读。它替你省掉每次重复交代的四件事，也把"改完就校验"的约定固定下来：

```markdown
# 冻河 · 项目约定

- 观看契约：电影长片 · 16:9 · 剧场感 · 慢节奏；制作形态：实拍质感（由 Seedance 2.5 承担画面）
- 目标视频模型：Seedance 2.5（已写进 production_profile）；提示词语言：中文
- 参考图目录：输入/参考图/；本镜起始帧在 剧集/<EP>/制作成果/images/
- 没有参考图时：默认等图，不改成文生视频；除非我明确说"走文生视频"
- 每次改完 剧集/<EP>/ 下任一文档，跑：
  python3 <技能目录>/skills/short-drama/scripts/creator_markdown_check.py 剧集/<EP> --project-root . --dialogue-coverage
  python3 <技能目录>/skills/short-drama-video-prompts/scripts/dialect_check.py 剧集/<EP> --project-root .
- 一句话请求的四件事：做哪一集的哪一阶段、目标视频模型、参考图在哪里或还没有、没有图时等图还是明确走文生视频
```

把 `<技能目录>` 换成仓库的实际路径。

## 5. 逐阶段创作

每一步都是一句话请求；技能自动续跑内部批次，只在三处停下：范围完成、真实创作分叉、即将调用外部生产。
产物永远是 `剧集/EP001/` 下的五份 Markdown。

### 5.1 剧本

```text
$short-drama-write 写完 EP001《冻河》第一本：下岗司机林正国在封冻的江面上拉煤，女儿开口要学费，
夜里传呼机把他叫去供销社仓库，他把车钥匙放在轮胎上换工钱
```

产物：`剧集/EP001/剧本.md`。场景标题写成 `## EP001-SC001 外 · 江边冰面 · 日`，对白写成 `角色（提示）：台词`。

### 5.2 视觉设定（含观看契约与派生）

```text
$short-drama-assets 从 EP001 拆完人物、地点、道具和本集状态。观看契约是电影长片，制作形态实拍；
林小满是林正国与周慧的女儿，写成派生条目；车钥匙写尺度；小满的棉袄上一把连续性锁
```

产物：`剧集/EP001/视觉设定.md`。检查四处是否写对：

- 文件开头「项目视觉方向」段有 `- 观看契约：电影长片 · 16:9 · …`；
- 派生条目有三行：`派生自：人物「…」（继承：…；不继承：…）`、`派生关系`、`派生状态：待上游定稿`；
- 道具条目有 `- 尺度：手持级`；
- 连续性锁一行写全：`连续性锁：LOCK-…《中文名》（镜头：…；图片提示词项：…）· 锁面：…`。

写法样例直接看 `examples/creator-first-film/剧集/EP001/视觉设定.md`。

### 5.3 图片提示词

```text
$short-drama-image-prompts 为 EP001 写角色板、场景板、道具板；林正国用服装发型核对板，
林小满用面部基准三视板，车钥匙用 3:4 单件档案照
```

产物：`剧集/EP001/图片提示词.md`，每项一个 `## IMG-… · 中文名` 与 `### 可复制提示词`。派生条目（林小满）的
`参考：` 此时写"无外部参考；待上游定稿后改为父母定稿图的 REF 槽位"，不虚构图片。

### 5.4 分镜

```text
$short-drama-storyboard 完成 EP001 的正式分镜和每镜冻结关键帧；目标模型 Seedance 2.5 已在档案里；
暂时没有参考图，先按待补处理，不改成文生视频
```

产物：`剧集/EP001/分镜.md`。每镜有 `时长`、`起点 → 唯一动作 → 终点`、`图片提示词项`、`输入参考图`、`视觉依据`
与 `### 冻结关键帧提示词`。确实不由镜头承载的对白，写在第一个镜头之前的 `## 省略的对白` 一节。

### 5.5 视频提示词

```text
$short-drama-video-prompts 按 Seedance 2.5 把 EP001 分镜逐镜写成视频提示词；平房一场三镜装一个交付分组。
这一集没有参考图，我明确选择文生视频
```

产物：`剧集/EP001/视频提示词.md`。多镜容器写在文档末尾 `## 交付分组` 下，容器自己的正文用 `#### 可复制提示词`。

图生视频的正确顺序反过来：先出图（第 7、8 节），再回到分镜把图绑成 `REF-`，最后才写视频提示词。

## 6. 机械核对

改完任何一份文档都跑，只读不写：

```bash
python3 <技能目录>/skills/short-drama/scripts/creator_markdown_check.py 剧集/EP001 --project-root . --dialogue-coverage
python3 <技能目录>/skills/short-drama-video-prompts/scripts/dialect_check.py 剧集/EP001 --project-root .
```

怎么读输出：

| 行 | 含义 | 要不要动手 |
|---|---|---|
| `OK: 剧集/EP001` | 跨文档契约成立 | 不用 |
| `INFO 本集 8 镜时长合计 65s；目标 65s，差 +0s` | 时长账目，只报告 | 差值大就回内容层合并或拆分，不按数字均匀砍 |
| `WARN IMG-A 与 IMG-B 的可复制正文词级相似度 0.83 ≥ 0.75` | 两条身份板可能只差标识符 | 看一眼区分锚点在不在 |
| `ERROR: SHOT-EP001-004: 派生上游未定稿：…` | 子女在父母定稿图之前被绑了身份图 | 先出父母的图，见第 8 节 |
| `ERROR: SHOT-EP001-002: 时长 20s 不在已接受档案的原生区间 [4, 30] 内` | 镜头长过一次生成上限 | 拆镜或进交付分组 |
| `ERROR: GROUP-EP001-A: 容器时长 22s 不等于成员时长之和 21s` | 分组算术错 | 改《分镜.md》的时长，再改容器 |
| `ERROR: 剧本.md: 对白「…」未被任何视频正文或分镜声音字段承载` | 漏了一句台词 | 补进视频正文，或在「省略的对白」显式省略 |
| `ERROR VID_DIALECT_RANGE GROUP-EP001-A: 镜头 2 的起点 0:07 不等于上一段终点` | 时间戳改了秒数忘改正文 | 按成员时长重算 |
| `INFO VID_DIALECT_PROFILE_UNSET: …` | 档案没声明方言，跳过对账 | 回第 3 节 |

把 Codex 拉进来看结果最省事：`把上面两条校验的输出修掉，不改剧情`。

## 7. 生产：预览、确认、执行

生产永远三步，顺序不能合并：`prepare` 预览 → 你看过预览后明确确认 → `run`。

### 7.1 adapter 配置（放在项目外）

```json
{
  "adapters": {
    "codex-imagegen": {
      "command": ["python3", "/absolute/path/skills/short-drama-produce/scripts/provider_adapters.py", "codex-imagegen"],
      "timeout_seconds": 900
    },
    "seedance": {
      "command": ["python3", "/absolute/path/skills/short-drama-produce/scripts/provider_adapters.py", "seedance"],
      "timeout_seconds": 3600
    }
  }
}
```

存成例如 `~/drama-adapters.json`；凭据不写在这里，Seedance 从环境变量 `ARK_API_KEY`、`SEEDANCE_MODEL` 读，
`codex-imagegen` 只用本机 codex 登录态。

### 7.2 出一张角色板

```text
$short-drama-produce 预览 EP001 的 IMG-LINZHENGGUO-SHEET 图片任务，adapter 用 codex-imagegen；等我确认后再执行
```

技能会写一个临时 job（形状见 `skills/short-drama-produce/references/adapter-contract.md`）并跑：

```bash
python3 <技能目录>/skills/short-drama-produce/scripts/production_tool.py prepare ./dong-he --job /tmp/job-linzhengguo.json
```

预览会列出数量、可复制正文、参考图槽位、参数、输出路径与 adapter。看清楚之后：

```bash
python3 <技能目录>/skills/short-drama-produce/scripts/production_tool.py confirm ./dong-he \
  --job-id EP001-IMG-LINZHENGGUO --confirmation "CONFIRM EP001-IMG-LINZHENGGUO <预览里给出的代码>"
python3 <技能目录>/skills/short-drama-produce/scripts/production_tool.py run ./dong-he \
  --job-id EP001-IMG-LINZHENGGUO --adapter-config ~/drama-adapters.json
```

产出落在 `剧集/EP001/制作成果/images/`。任何提示词、参数或输入变化都会让确认失效，重来一遍 `prepare`。

**在 Codex 会话里跑 `run` 的注意事项**：`codex-imagegen` 会启动第二个 `codex exec` 进程出图。Codex 的沙箱若拒绝
子进程或写入，就把 `run` 这一步放到普通终端执行——job 已经 `prepare` 与 `confirm` 过，换终端不影响确认。

### 7.3 把图绑回文档

图出来后不会自动回填。请分镜 owner 绑定：

```text
$short-drama-storyboard EP001 的角色图和场景图已经在 剧集/EP001/制作成果/images/ 下，
按可见人物、地点、道具把它们绑成带用途的 REF，缺哪张列出来
```

之后视频提示词才能写成图生视频。

### 7.4 出视频

```text
$short-drama-produce 预览 EP001 的 MOTION-EP001-001 视频任务，adapter 用 seedance；等我确认后再执行
```

同样三步。连续段（Seedance `extend`）要等上一段实际视频与实际尾帧都存在才能提交，技能会把没就绪的段标成
"待续接、不可提交"。

## 8. 派生资产的出图顺序

家族戏最容易返工的地方，顺序只有一种：

1. 父母（没有 `派生自` 的条目）先出图：`IMG-LINZHENGGUO-SHEET`、`IMG-ZHOUHUI-SHEET`；
2. 把两张定稿图绑成 `用途：身份` 的 `REF-`（图片提示词里派生条目的 `参考：`，或某镜的「输入参考图」）；
3. 把《视觉设定.md》里林小满的 `派生状态` 改为 `上游已定稿`；
4. 再出林小满的身份板：`参考：` 用父母的 `REF-`，`控制：` 只写继承项，`不得控制：` 逐字带上不继承项。

反过来做，`creator_markdown_check.py` 会报 `派生上游未定稿`——这不是它多管闲事，是子女的脸只能从父母的脸来。

## 9. 审查与导出

```text
$short-drama-review 审查 EP001 的剧本、分镜与视频提示词，结论写进 审查/EP001-审查.md
```

审查只写问题、影响与修订要求，不替你改文档；改完再点名复审。交付：

```bash
python3 <技能目录>/skills/short-drama/scripts/project_tool.py export ./dong-he --out ../dong-he-delivery
```

它复制每集五份文档与 `制作成果/`，附清单与校验和，排除 `输入/`、凭据与隐藏运行状态。后期顺片（时间线、字幕、
粗剪）暂未实现，路线见 [后期顺片设计记录](post-production-assemble.md)。

## 10. 常见问题

| 现象 | 原因与处理 |
|---|---|
| `$short-drama` 不被识别 | 软链没建成或 Codex 没重启；`ls -l ~/.codex/skills` 看目标是否指向仓库 |
| `python3: command not found` | macOS 用自带的 `python3`；Windows 用 `py -3` |
| 技能每次都重新问目标模型 | 会话里的点名没落档案，回第 3 节 |
| 分镜仍按竖屏节奏切、首镜不给空景 | 《视觉设定.md》「项目视觉方向」缺 `观看契约：电影长片` |
| 视频提示词被写成文生视频 | 没有说"明确走文生视频"时技能应等图；检查「输入参考图」是不是被写成了普通「无」 |
| `codex-imagegen` 失败 `codex_missing` | 找不到 codex 二进制；用 `CODEX_BIN` 指定，或确认 `codex --version` 可用 |
| `codex_exit_1` | 多半是登录态过期或沙箱拒绝写文件；在普通终端跑一次 `codex --version` 与 `run` |
| 手持道具被画成家具尺寸 | 道具条目写 `尺度`，正文带尺度短语；`IMG-16` 会拦漏掉的那条 |
| 想改剪映或 Resolve 精修 | 见 [后期顺片设计记录](post-production-assemble.md) 的三条路线 |

样例项目：[《冻河》第一本](../examples/creator-first-film/)（横屏电影）与 [《让你管账号》EP001](../examples/creator-first/EP001/)（竖屏漫剧）。
