# 电影向合并设计：以 drama-skills 为主干吸收 shuohao-skills 与 Chaoge 体验版

- 状态：已实施（Phase 1–4），实施记录见 §9；待本机复验与提交
- 目标读者：本 fork 的维护者
- 范围：只设计，不改代码；每一项都写明来源、落点、规则等级、要不要脚本、与现有规则怎么不冲突

## 0. 一页结论

三个项目不在同一维度上竞争：**drama-skills 是知识库，shuohao-skills 是编译器，Chaoge 体验版是版式规范**。
以 drama-skills 为主干的理由只有一条——电影级的上限由镜头语言与连续性方法论决定，17,094 行工艺文档是三者中
唯一抄不快也写不出来的东西；而另外两者的强项（确定性校验、零 key 出图、资产版式、血缘依赖）规格明确、可移植。

移植的总原则：**只移植方法与不变式，不移植数字配额，不复制任何一方的提示词原文**。所有新增内容归入
drama-skills 既有的四级规则分级（`structural_invariant` / `reviewed_invariant` / `craft_default` / `taste_option`），
落在现有十个 skill 的 `references/` 与 `scripts/` 里，不新增 skill 目录，不建立第二套真相。

移植后 drama-skills 得到的新能力，按价值排序：

| # | 能力 | 来源 | 形态 |
|---|---|---|---|
| 1 | 血缘/派生资产的依赖图、继承边界与解锁顺序 | Chaoge | 知识 + 结构校验 |
| 2 | 方言结构标记逐字对账（H3 `<Picture N>` / `[Shot k] At …`、Seedance 时间戳区间） | shuohao | 结构校验 |
| 3 | creator-first 五文档的时长账目：集时长加总、原生区间、逐字对白覆盖 | shuohao（思路）+ drama 既有规则 | 结构校验 |
| 4 | codex `$imagegen` 零 API key 出图 adapter | shuohao | 生产 adapter |
| 5 | 角色设定板与道具板的可选版式卡（面部基准三视板 / 服装发型核对板 / 3:4 单件档案照） | Chaoge + shuohao 合并 | 知识（craft/taste） |
| 6 | 实拍形态卡补全：摄影系统一致、世界坐标、色彩与声音策略 | Chaoge | 知识（craft） |
| 7 | 观看契约声明：让竖屏短剧的 craft_default 整体让位于电影取向 | 三方皆无 | 知识 + 示例 |
| 8 | 道具尺度档位、道具入选判据、模板化相似度提示 | shuohao | 知识 + 轻量校验 |
| 9 | 全片情绪曲线（可选产物） | Chaoge | 知识（taste） |

## 1. 目标、边界与约束

### 1.1 目标

做**专业级实拍质感的电影**，并且对画面有**精准控制**。精准控制拆成两半：

- 表达精度：脑子里的画面能否无损写到执行端——机位、轴线、焦段意图、光位、起止边界、连续性锁。drama-skills 已经是三者中最强的。
- 执行确定性：写下的东西会不会被下游漂掉、上游改了会不会有人告诉你。这一半 drama-skills 只在 JSONL 旧路径上有校验，creator-first 五文档路径上只有 `creator_markdown_check.py`；shuohao 在这一半上演示了该查什么。

### 1.2 主干不可动摇的约束

这些约束来自 `CONTRIBUTING.md` 与 `tests/`，每一项移植都要过一遍：

1. **知识与做法优先**：新增能力先写成 `references/` 与 `SKILL.md` 步骤；只有智能体不应徒手完成的确定性工作（稳定索引、跨文件结构对账）才写脚本。不要把编辑/创作判断写成规则代码。
2. **规则分级**：所有规范归入四级；**不得把统一的字数、比例、数量配方设为质量门槛**。这一条直接否决 shuohao 的「每切 2–5 秒」「段 ≤ 15 秒」「同框 ≤ 3 人」「爽点间隔 ≤ 3 集」「单句 ≤ 35 字」作为门——它们本来也和电影冲突。
3. **每个 skill 自包含**：脚本不共享库，引用解析块逐份复制；改一个 skill 的改动只落在它自己的目录。
4. **Python 3.9 下限、标准库**：每个脚本声明 `MINIMUM_PYTHON`，`tests/test_shipping_boundaries.py` 核对；确定性脚本不得 import 网络客户端（`provider_adapters.py` 与 Dashboard 是既有例外）。
5. **稳定 ID**：新规则在拥有前缀的 skill 的 `stage-contract.md` 表里登记，前缀不变（`AST`/`IMG`/`SHT`/`VID`/`CON`/`REV`/`STY`/`SCR`）；`knowhow-index.md` 只加路由行，不复制正文。
6. **测试证明行为，不钉死文案**：不得新增「某文档包含某字符串」的断言。
7. **每个脚本发出的诊断代码必须出现在该 skill 的某份 `.md` 里**（`test_every_emitted_code_is_catalogued`）；新脚本必须从 `SKILL.md` 可达（`test_deterministic_validators_are_linked_from_their_owning_skills`）；Markdown 链接与锚点必须可解析；粗体不得以标点收尾后紧接文字。
8. **skill 集合固定**：`tests/test_suite_anatomy.py` 的 `EXPECTED_SKILLS` 与 `tests/test_creator_first_golden.py` 的 `EXPECTED_KNOWHOW` 都是精确集合。新增 reference 文件必须同步更新后者；**不新增 skill 目录**。
9. **示例一律合成改写**；仓库不得包含私有材料、绝对路径、未声明的供应商网址。
10. **五文档是唯一创作真相**：单集主链不落盘 JSON/JSONL、覆盖表、QA 报告。校验读文档、写诊断，不产生第六份文档。

### 1.3 环境说明

本次设计在一个没有 `python3` 的沙箱里完成（只有 `node 24`）。因此：

- 实施阶段凡涉及 Python 的部分，我可以编写脚本与测试，但**必须在创作者本机跑**
  `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v` 与 `ruff check --no-cache .` 才算验收；
- Phase 0 先在本机建立绿色基线，记录 commit。

### 1.4 许可与来源

| 来源 | 许可 | 处理方式 |
|---|---|---|
| shuohao-skills | Apache-2.0，附 NOTICE | 移植**方法与不变式**，用本仓库自己的措辞重写；确需借用的具体做法（codex 调用契约、版本探测、变长参数走 stdin）在对应 reference 末尾注明「学习来源：shuohao-skills」，不写网址（`skills/` 内的网址受声明清单约束） |
| Chaoge AI导演体验版 1.3.0 | 无公开许可，且明确为引流体验包 | 只移植**方法论**（依赖图、解锁顺序、继承配比、视图选择、摄影系统一致），全部重写；**不复制任何提示词模板原文、固定问句与联系方式** |
| drama-skills 上游 | MIT | fork 内改动遵守其 CONTRIBUTING；`maintainers/` 的受保护发布流程对个人 fork 不强制，但规则分级与 CHANGELOG 约定照做 |

## 2. 三方对比

### 2.1 定位与体量

| | drama-skills（主干） | shuohao-skills | Chaoge 体验版 |
|---|---|---|---|
| 一句话 | 工艺方法论库 + 契约校验 | 确定性流水线 + 校验器 + 出图 | 前半程资产版式规范（试用装） |
| 体量 | 10 skill · 134 md / 17,094 行 · 28 py / 16,272 行 · 25 测试文件 / 14,853 行 | 5 skill · 5,950 行 md · 11,823 行 mjs · 5 份 selftest 共 1,170 项断言 + 组装器 92 项 | 7 文件 / 440 行 |
| 真相载体 | 每集五份 Markdown（`剧本/视觉设定/分镜/图片提示词/视频提示词`）+ 稳定 ID | JSON 唯一真相，md/html 由 `render` 派生 | 聊天内流程 |
| 校验 | `creator_markdown_check.py`（跨文档契约）；JSONL 路径另有 SHT-16/17、VID-04/13/15、覆盖、配音本等校验 | outline 14 / art 11 / script 10 / storyboard 17 道门 + characters 若干，全部代码 | 文字验收清单 |
| 出图/出片 | 4 个 stdlib adapter（Seedance / GPT Image 2 / MiniMax H3 / MiniMax Music），需环境凭据；`preview → confirm → run` 硬闸门 | codex `$imagegen` 零 key；角色/场景/道具设定图与分镜图真出 | 只给提示词 |
| 交付 | 五文档 + `制作成果/` + `export` 清单/校验和；本地 Dashboard | 单页离线 HTML 报告（复制按钮、质量门面板、导出 JSON）+ H3 投产包 | 聊天内图 |
| 规则治理 | 四级分级 + 稳定 ID + 冲突优先级 + 所有权分离 | 门 = 代码；配方卡明确「语汇不是法条」 | 硬边界 + 固定问句 |
| 视频模型 | Seedance 2.0/2.5、MiniMax H3 方言；通用路径 | MiniMax H3（对齐指令逐字对账） | 默认 Seedance 2.5（体验版不做视频） |
| 形态/画风 | 6 张形态卡（实拍/二维动态漫/风格化三维/水墨/Q 版/国漫） | `realistic` / `ghibli` 两个预设，整块替换 + 反向词冲突检查 | 只允许实拍写实 |
| 短剧绑定 | **隐性重力**：默认值可覆盖，但示例、题材卡、调度手册全是竖屏语境 | **显式参数**：`maxSegmentSeconds`/`min|maxCutSeconds` 写死在代码，改参数即可 | 无（未到分镜） |
| 维护 | 2026-09-02 v0.6.4，CI 三档 Python | 2026-08-26，仍在更新 | 单版本 1.3.0 |
| 许可 | MIT | Apache-2.0 | 无 |

### 2.2 能力矩阵（谁最优 → 去向）

| 能力 | drama | shuohao | Chaoge | 最优 | 去向 |
|---|:-:|:-:|:-:|---|---|
| 剧作：承诺/引擎/分集/题材卡 | ✅✅ | ✅ 大纲五件套 | — | drama | 保留 |
| 镜头语言：机位/轴线/焦段意图/运镜动机/切点理由 | ✅✅ | ⚪ 手感规则 | — | drama | 保留 |
| 关键帧：单一可冻结瞬间、起终边界分离、尾帧代价 | ✅✅ | ⚪ 主/子分镜图 | — | drama | 保留 |
| 视频提示词：起点—变化—终点、表演弧、摄影机合同、声音时间线 | ✅✅ | ⚪ H3 结构 | — | drama | 保留 |
| 目标模型能力档案 / 方言（H3、Seedance 2.0/2.5） | ✅✅ | ✅ H3 | — | drama | 保留 |
| 参考图控制（REF 槽位、用途封闭词表、控制/不得控制、自动绑定） | ✅✅ | ✅ 挂图纪律 | ⚪ `{{Image N}}` | drama | 保留 |
| 连续性：CON-01 边界、连续性锁、状态变化记录 | ✅✅ | ⚪ 改一切连读三切 | ⚪ 资产级 | drama | 保留 |
| 审查：证据式 finding、四级分级、反模板 | ✅✅ | — | — | drama | 保留 |
| 生产闸门：preview → confirm → run、凭据隔离、审计 | ✅✅ | ⚪ | — | drama | 保留 |
| **跨文档结构校验（creator-first）** | ✅ 契约层 | ✅✅ 账目层 | — | 互补 | **移植账目层** |
| **方言结构标记逐字对账** | ⚪ 文字要求 | ✅✅ | — | shuohao | **移植** |
| **节拍/对白覆盖机械核对** | ⚪ SHT-01 文字 + JSONL 覆盖 | ✅✅ 认领 | — | shuohao | **移植（对白逐字覆盖）** |
| **零 key 出图闭环** | ⚪ 需凭据 | ✅✅ codex | — | shuohao | **移植为第 5 个 adapter** |
| **血缘/派生依赖图 + 解锁门禁** | — | — | ✅✅ | Chaoge | **移植** |
| **角色设定板版式** | — 方法论 | ✅ 面部基准三视板 | ✅ 服装/发型核对板 | 合并 | **移植为版式卡** |
| **道具板版式与尺度** | ⚪ 尺度参照 | ✅ 白底无手 + 尺度档位 | ✅ 3:4 单件档案照 | 合并 | **移植** |
| **实拍摄影系统一致** | ⚪ 形态卡 | — | ✅✅ | Chaoge | **移植进实拍卡** |
| 画风预设整块替换 + 反向词冲突 | ⚪ 形态卡 | ✅ | — | shuohao | 只移植「自相矛盾」审查项 |
| 情绪曲线可视化 | — | — | ✅ | Chaoge | 移植为可选产物 |
| 离线单页 HTML 报告 | ⚪ Dashboard | ✅✅ | — | shuohao | 可选，最后做 |
| 门失败累积 `.gates.jsonl` | — | ⚪ 试验中 | — | — | 不移植 |
| 电影观看契约 | — | ❌ 硬门冲突 | ⚪ 只有前半程 | 无 | **自己写** |

### 2.3 校验方式的本质差异

- drama-skills 的校验是**契约核对**：ID 解析、字段在不在、引用对不对、锁面带没带、模式选没选对。它刻意不查数字配额。
- shuohao 的校验是**账目核对**：秒数加总、区间对账、认领不重不漏、结构标记逐字比对。它把「秒数是下单不是估算」当前提。
- 两者重叠的部分（ID 唯一、引用存在、提示词语言）drama 已有；**缺的是账目层**——而账目层在 drama 的 JSONL 旧路径上其实存在（`storyboard_check.py` 的 SHT-16、`container_check.py` 的 VID-15、`motion_timing_check.py` 的 VID-04），只是没有为 creator-first 五文档实现。所以移植不是引入新规则，而是**把已登记的 structural_invariant 在 Markdown 上实现出来**，再补方言标记对账这一条新规则。

### 2.4 短剧绑定：显式与隐性

shuohao 的短剧约束写死在参数里，改 `params` 即可；drama-skills 的约束是 `craft_default`，声明理由即可覆盖，但它的示例、题材卡、`blocking-playbooks.md` 第 1 节、`production-shot-grammar.md` 的子镜密度行全部在竖屏语境写成。**隐性重力比显式参数更难对付**：配置改了，模型读到的示例还是竖屏的。对策见 4.3 观看契约——不只是覆盖默认值，还要给一套横屏电影示例。

## 3. 差距分析：以电影为标尺，主干缺什么

| 缺口 | 现状 | 后果 | 补法 |
|---|---|---|---|
| 血缘/派生资产 | `identity-vs-variant.md` 只处理同一人物的造型版本；双胞胎/克隆判为不同人物；无跨人物派生 | 家族戏中子女与父母无关联或撞脸；父亲改骨相后无人提醒子女作废 | 4.1-A |
| creator-first 账目 | `creator_markdown_check.py` 不解析 `时长`，不加总，不核对原生区间；对白是否被视频正文承载无机械核对 | 全集装到一起才发现超长；H3 同轨对白漏句 | 4.2-B/C |
| 方言结构标记 | `minimax-h3.md` 要求 `<Picture N>` 与 `顺序` 一致、容器时刻累计，但只是文字要求 | 编号错位接口不报错，模型收到矛盾素材说明 | 4.2-A |
| 出图闭环 | adapter 需 `OPENAI_API_KEY` / `ARK_API_KEY` / `MINIMAX_API_KEY` | 没有 key 就看不到画面，无法迭代「机位高度一米二」是否生效 | 4.2-D |
| 设定板版式 | 三视图列为 `taste_option`，不给版式 | 每次出板版式随机，服装层次与后脑发型最常穿帮 | 4.1-B |
| 实拍摄影系统 | `实拍.md` 讲光与材质词汇，不讲摄影机/胶片/镜头家族/画幅帧率 | 数字机与实体胶片并列这类不一致无人拦 | 4.1-C |
| 观看契约 | `craft_default` 可覆盖，但没有声明落点与示例 | 模型被竖屏示例带偏 | 4.3 |
| 道具尺度 | `prop-plate.md` 说「尺度最好绑定中性参照」，无档位 | 手持道具画成家具 | 4.2-E |

## 4. 移植清单

每项格式：来源 → 落点 → 规则等级 → 脚本 → 冲突处理 → 优先级。

### 4.1 来自 Chaoge

#### 4.1-A 血缘/派生依赖图与解锁顺序（优先级 P0）

- 来源：`character_assets.md` 的有向依赖（血缘亲属、同一人的换装/年龄/受伤/变异、双胞胎/克隆、宿主与变身、绑定装甲/生物）、「两名父母都确认后才解锁」、「只继承 2 至 4 项稳定家族特征……像血亲但不是同一张脸」、「双胞胎或克隆体才允许高度相似」、生产清单的上游依赖与批次列。
- 落点：
  - 新增 `skills/short-drama-assets/references/kinship-and-derivation.md`：派生类型表；`视觉设定.md` 人物条目的可选声明行（语法见附录 B）；继承项必须是**跨造型稳定的骨相/体态锚点**，不得含年龄、发型、服装、伤污等 Look 层内容；派生条目在上游没有已核对参考图之前，其身份板与分镜绑定处于「待上游定稿」；生产顺序按依赖层展开（独立/父母/原形 → 血亲 → 变异/受伤/换装/年龄）。
  - `identity-vs-variant.md` 「容易误判的情况」加一小节指向新文件：双胞胎/克隆仍是不同人物，但可以互为派生来源。
  - `skills/short-drama-image-prompts/references/character-and-look.md` §2 加「派生身份板怎么写」：父/母定稿图各占一个 `REF-` 槽位，`用途：身份`，`控制：` 只写声明的 2–4 项，`不得控制：` 年龄、发型、服装、体型、肤色风霜度、表情。
  - `asset-review-checklist.md` A 段加两条机械项；`rubric-assets-prompts.md` 加语义项。
  - `stage-contract.md`（assets）登记 `AST-14`、`AST-15`；`knowhow-index.md` 加路由行「血缘与派生资产 → `$short-drama-assets`」。
- 规则等级：`AST-14 reviewed_invariant`（继承项 2–4 且为稳定锚点、不继承可变状态；非双胞胎/克隆不得高度相似）；`AST-15 structural_invariant`（`派生自` 解析到存在的人物条目、无环；派生条目的分镜绑定在上游无 `REF-` 前不得声称就绪）。
- 脚本：`creator_markdown_check.py` 新增解析 `派生自：` 行 → 条目存在性 + 环检测；当派生条目被某镜 `视觉依据` 引用且该镜绑定了它的身份 `REF-`，而上游人物在同集没有任何 `用途：身份` 的 `REF-` 时，报「派生上游未定稿」。诊断保持该脚本既有的中文消息风格。
- 冲突处理：不改变 `AST-04`（身份与临时状态分离）；派生声明只在身份层；不新增第六份文档；Chaoge 的「批次表」不落盘，改为完成回报里的「建议生产顺序」段。
- 不移植：H1/H2/H3 变异程度问句（题材特定，写成 kinship 文件里的一句「变异/兽化作为派生形态登记，程度由创作者一次决定」即可）。

#### 4.1-B 角色设定板与道具板版式卡（优先级 P1）

- 来源：Chaoge 16:9 设定板（左侧正面**无头**服装视图 + 背面**完整发型**视图，右侧面部特写；信息区高度上限；禁空白脸/遮罩脸；压低镜面高光）；shuohao 16:9 三区板（左约 34% 半身像为**面部基准**，右上三视图照它画，右下细节条；分区光照——左栏方向光有体积，右栏平光可抠图量比例；`PROPORTIONS ARE CRITICAL`、`the detail studies give way, not the figures`）。
- 落点：新增 `skills/short-drama-image-prompts/references/character-sheet-layouts.md`，三张**可选**版式卡，每张写「解决什么 reuse_job / 版面关系 / 光照分区 / 最常崩的地方 / 排除」：
  1. 面部基准三视板（识别与比例）；
  2. 服装与发型核对板（服装层次、后脑发型、左右锚点——正面无头视图的意义是让模型不为脸让位，背面视图必须保留完整头部）；
  3. 单视图身份板（已有 `production-sheet-recipes.md` 的默认）。
  同时给一条「一图一个长相」的写法：左栏/主视图是基准，其余视图照它画，写进排除项。
- 道具：`prop-plate.md` §3 视图与背景加「3:4 竖构图单件档案照」选项（主体占比、不裁切握持端/刃口/关键文字、不做三视图、无人无手、材质决定高光）与 shuohao 的「白底可抠、反向禁手」并列；`IMG-16` 见 4.2-E。
- 规则等级：`IMG-15 craft_default`（版式从版式卡选用，服务 reuse_job；`IMG-03` 仍是语义不变式）。版面比例数字全部是 `taste_option`，不设门。
- 脚本：无。
- 冲突处理：`production-sheet-recipes.md` 已说「纯白底、无情绪、三视图只是一种项目选择」——版式卡是它的展开，不改它的定位；提示词仍按 `#/format/prompt_language` 写，不固定英文；版式卡里不出现供应商词。
- 不移植：Chaoge 的字号百分比、`{{Image 1}}` 写法、8K 之类质量词；shuohao 的「机器字段永远英文」。

#### 4.1-C 实拍形态卡补全：摄影系统、世界坐标、色彩与声音策略（优先级 P1）

- 来源：Chaoge `creative_baseline.md`（胶片实拍 vs 数字实拍二选一、镜头家族、画幅与帧率、光源/曝光/反差、环境色彩策略、成像纹理、禁用清单、删除「电影感/高级感」空词、1 部主要参考 + 至多 1 部补充且必须翻译成可见参数）；`story_bible.md`（国家/地域/年代到年份或 ≤10 年区间，同步技术、建筑、服装、交通、通讯边界；空间链；状态链与视觉母题）。
- 落点：
  - `skills/short-drama/references/form-cards/实拍.md` 新增三节：「摄影系统一致」「世界坐标」「环境色彩与声音策略」。摄影系统写成 `craft_default`：介质二选一、镜头家族、画幅帧率在项目视觉方向锁定一次；需要胶片感又用数字机时写印片模拟，不写成实体胶片。
  - `look-development.md` 「先写可观察的方向」加「影视参考必须翻译成可见参数」一句与反例。
  - `director-brief-craft.md` 可验收约束型加「世界坐标」条目。
  - `视觉设定.md` 项目视觉方向段的建议字段在 `creator-documents.md` 补一行示例。
- 规则等级：全部 `craft_default` / `taste_option`；形态卡不产生 ID（`production-form-profiles.md` 明文）。
- 脚本：无。
- 冲突处理：`generability.md` 明确实拍不受可生成性约束——但本项目是「实拍质感的生成」，形态仍选实拍卡，同时 `production_profile` 声明生成模型承担画面，让 `VID-21` 生效。实拍卡里加一句说明这个组合合法。

#### 4.1-D 全片情绪曲线（优先级 P3，可选）

- 来源：Chaoge `emotion_curve.md`：8–14 节点（≤16）、0–10 强度、幕区段、最高峰/反转/余震标记、至少 1 个呼吸区、BGM 重点只标推动/反转/连接/积蓄/释放且复用节点编号。
- 落点：`skills/short-drama-develop/references/emotion-curve.md`，作为 `项目开发/` 的可选产物（节点表 Markdown），附一段通用信息图提示词写法；生产走 `$short-drama-produce` 的非 creator image job。
- 规则等级：`STY-25 taste_option`。`contract-and-ownership.md` 已写「情绪曲线不是通用结构门槛」，本项与之一致：只做可视化，不做门。
- 脚本：无。

### 4.2 来自 shuohao-skills

#### 4.2-A 方言结构标记逐字对账（优先级 P0）

- 来源：`novel-storyboard` 的 `h3-structure` 门——对齐指令与 `[Shot k] At mm:ss.mmm` 由分镜秒数推导后逐字比对，「改了秒数忘改提示词，validate 当场拦」。
- 落点：新增 `skills/short-drama-video-prompts/scripts/dialect_check.py`，读 `分镜.md`、`视频提示词.md` 与 `short-drama.json`，按已接受的 `video_prompt_dialect` 核对：
  - `minimax-h3`：full-reference 正文中的 `<Picture N>` / `<Video N>` / `<Audio N>` 编号集合 ⊆ 本镜「输入参考图」同类素材的 `顺序`，且不引用不存在的序号；三段/六段字段齐全且按序；交付分组容器的 `[Shot k] At mm:ss.mmm` 等于成员已接受时长的累计；`<d>[Chinese] …</d>` 内文本在剧本对应场次逐字存在。
  - `seedance-2.5`：`镜头 k [a–b]` 区间连续、不重叠、终点等于镜头/容器时长；`@图片N`/`@视频N` 编号 ⊆ `顺序`；`{角色用中文说：“…”}` 内文本逐字存在。
  - 通用路径：只做 `<Picture N>` 类标签不越界的通用检查。
- 规则等级：`VID-25 structural_invariant`。它是 `VID-24`（REF 槽位与用途）与 `VID-13`（容器算术）的交叉核对，不引入任何新数字标准。
- 脚本：Python 3.9 stdlib，自带引用解析块副本；诊断代码 `VID_DIALECT_PICTURE_INDEX`、`VID_DIALECT_CUT_TIME`、`VID_DIALECT_RANGE`、`VID_DIALECT_FIELD_ORDER`、`VID_DIALECT_DIALOGUE_VERBATIM`，登记在 `minimax-h3.md` / `seedance-2.5.md` 末尾「机械核对」小节；`SKILL.md` 按需知识列表链接脚本。
- 冲突处理：不改 `生成方式` 只有两个值的约定；模式仍由 `用途` 组合读出；脚本只读不写。
- 测试：`tests/test_dialect_check.py`，夹具用合成的三张图 + 六段正文；断言编号错位、时刻漂移、区间缺口各自被捕获，正确样本通过。

#### 4.2-B creator-first 时长账目：集时长加总与原生区间（优先级 P0）

- 来源：shuohao「秒数是下单不是估算」、`segment-cap`、`ep-duration`；drama 已有 `SHT-16`（集时长加总，JSONL 实现）与分镜 SKILL 的「已声明原生时长时每个一镜一生成的镜头都落在区间内」。
- 落点：`creator_markdown_check.py` 新增：
  - 解析每镜 `- 时长：Ns`（允许小数；允许 `待定`）；合计本集；读取 `format.target_seconds_per_episode` 时**只报告**带符号差值（`SHT-16` 明文：差值不是门槛）；无法解析且未写 `待定` 才是错误。
  - 读取 `creator_authority.production_profile.choices.native_duration_seconds`（`status: accepted` 时）：未进「交付分组」的镜头时长必须落在 `[min, max]`；进容器的按容器总时长核对（`VID-13`）。
  - 「交付分组」章节（多镜容器）解析：成员 ID 存在、来源顺序连续、容器时长 = 成员之和、每镜最多进一个容器（`VID-15`）。
- 规则等级：`SHT-16`（既有，补 Markdown 实现）；新增 `SHT-27 structural_invariant`（原生区间）；`VID-13`/`VID-15`（既有，补 Markdown 实现）。
- 脚本：在既有脚本内扩展；诊断沿用中文消息。
- 冲突处理：不设任何跨项目默认秒数；档案未声明时区间检查不生效且不报缺陷（`target-model-profile.md`：未声明不是缺陷）。
- 测试：`tests/test_creator_first_golden.py` 增加合成夹具：缺时长、超区间、容器算错、镜头进两个容器。

#### 4.2-C 逐字对白覆盖（优先级 P1）

- 来源：shuohao `h3-dialogue`（认领节拍的台词逐字进 `<d>` 块）与 `coverage`（节拍恰好一次认领）；drama 已有 `SHT-01`（每段原文由镜头落实或有理由省略）与 `VID-23`（同轨声音的封闭事件集合）。
- 落点：`creator_markdown_check.py` 可选开关 `--dialogue-coverage`：从 `剧本.md` 抽取 `角色（提示）：台词`、`[VO]`、`[OS]` 行，去空白后逐字在某个 `MOTION` 可复制正文（同轨）或 `SHOT` 的 `声音` 字段（不同轨）中出现；否则必须在 `分镜.md` 该场下有一行 `- 省略：「台词」 · 理由` 显式省略。默认不开：静态漫剧可以没有逐镜视频正文。
- 规则等级：`VID-26 structural_invariant`（开关生效时）——它是 `SHT-01` 对白子集的机械实现，不是新规则。
- 不移植：节拍「恰好一次」认领。drama 明确允许一段原文由几镜承担或几段合一镜（`SHT-08` 管重复），creator-first 又不生成 block ID；对白逐字覆盖已足够抓住「漏句」这一最常见事故。

#### 4.2-D codex `$imagegen` 零 key 出图 adapter（优先级 P0）

- 来源：`novel-characters/references/sheet.md` 与 `novel-storyboard/references/frame.md` 的调用契约：版本探测取最高版、`env -u NODE_OPTIONS`、变长参数时 prompt 走 stdin、一图一次调用不批量、显式 `copy to` 目标路径、失败不阻断、不碰需要 key 的 CLI fallback。
- 落点：
  - `skills/short-drama-produce/scripts/provider_adapters.py` 新增 provider `codex-imagegen`（modality `image`，恰好一个输出）：从 stdin 读已确认 job；定位 codex 二进制（`CODEX_BIN` 优先，其次 PATH 与常见安装位置，取版本最高者）；prompt = 可复制正文 + 按 `reference_bindings` 顺序追加的引用契约散文（中文名、用途、控制、不得控制，语言跟 `parameters.prompt_language`）+ 一句「把最终 PNG 复制到当前目录的 `<basename>`」；`-i` 依次挂 `references`；cwd = `output_root`；剥离 `NODE_OPTIONS`；超时；成功后核对文件存在并以契约格式输出 `outputs`；失败只输出白名单错误对象。
  - `references/providers/codex-imagegen.md`：环境要求（本机 codex 登录态）、参数（`size`/画幅只能写进正文的说明）、已知限制（不支持透明背景；一次一图；无法保证画风跨图一致，建议链式参考）、与其它 adapter 的取舍。
  - `SKILL.md` adapter 列表加第 5 项；`README.md` 一句话。
- 规则等级：不涉及规则表；属于生产工具。
- 测试：`tests/test_provider_adapters.py` 加假 codex（脚本写出占位 PNG 并只回文件路径），断言 argv 不含 shell、prompt 从 stdin 传入、`NODE_OPTIONS` 被剥离、输出路径核对、失败输出符合白名单。
- 冲突处理：仍走 `prepare → confirm → run`；不是 Dashboard 按钮；参考图 role 对 codex 无供应商枚举，`reference_bindings[].role` 自由文本但必须非空。

#### 4.2-E 道具尺度档位、入选判据、模板化提示（优先级 P2）

- 尺度档位：`视觉设定.md` 道具条目可写 `- 尺度：手持级|桌面级|家具级`（或项目自定义档位）；写了之后，该道具的 `IMG-` 可复制正文必须含对应短语（英文正文：handheld / tabletop / furniture scale；中文正文：档位原词）。`prop-plate.md` §3 加说明；`IMG-16 structural_invariant`（条件生效）；`creator_markdown_check.py` 实现。
- 入选判据：`prop-and-state.md` §「道具不是名词表」加一句 shuohao 的判据「它坏了、丢了、被换掉，剧情会不会塌」。`craft_default`，无脚本。
- 模板化提示：不同人物身份板可复制正文两两词级相似度过高 → `WARN`（不阻断）。`IMG-17 craft_default`；阈值写在 `short-drama.json#/format` 可选字段，缺省只警告。这是 `SHT-21`「只差标识符的两条提示词是模板」在资产板上的对应；drama 的反模板审查（`REV-05`）负责语义，脚本只负责提醒。

#### 4.2-F 画风自相矛盾（优先级 P3）

- 来源：shuohao `style-match` 门（`realistic` 不得禁 photorealistic，`ghibli` 必须禁）。
- 落点：不引入预设。`review-and-fixtures.md`（image-prompts）§3 结构检查加一条「正文不得同时要求与排除同一表面处理」，`rubric-assets-prompts.md` 加审查问句。`reviewed_invariant`，不写脚本（关键词匹配会误伤）。

### 4.3 三方都没有：电影向改造层（优先级 P0）

#### 4.3-A 观看契约声明

- 落点：新增 `skills/short-drama/references/viewing-contract.md`。契约写在 `视觉设定.md` 的「项目视觉方向」段（语法见附录 A），`project_tool.py init --aspect-ratio 16:9` 已能表达画幅，不改 schema。
- 契约生效后让位的 `craft_default`（逐条点名，不改原文本，只在原处加「观看契约声明为电影长片时本条不生效」的条件句）：
  - `production-shot-grammar.md` 「子镜密度 4–8 秒」行、「地理在动作内部到达」段；
  - `blocking-playbooks.md` §1 竖屏多人调度与交付面遮挡（`SHT-15` 本就要求声明才生效）；
  - `production-shot-grammar.md` 「高度变化在竖屏里比横屏更贵」；
  - `storyboard/SKILL.md` 「竖屏构图优先保证主体和反应可见」。
- 契约新增的默认（`craft_default`，可覆盖）：建立镜头是合法选择而非需要自证的例外；镜头长度只受 `native_duration_seconds` 与叙事约束；长镜优先走多镜容器与续接路由（`delivery-profile.md` 已有）；`delivery_surface` 保持 `unset` 不作为未决项。
- 规则等级：`SHT-26 craft_default`。
- 脚本：无。`creator_markdown_check.py` 不解析契约。

#### 4.3-B 横屏电影示例与工作流

- `examples/creator-first-film/EP001/` 五份合成文档：16:9、实拍形态、Seedance 2.5 档案、一对父女的派生声明、一条连续性锁、一个多镜容器带时间戳、一处显式省略的对白。它必须通过 `creator_markdown_check.py` 与 `dialect_check.py`，并进入 `tests/test_creator_first_golden.py` 作为第二个 golden。
- `docs/film-workflow.md`：仿 `docs/comic-drama-workflow.md` 的结构，从初始化到 codex 出图与 Seedance 2.5 续接。
- `README.md` 加「电影长片」一段与示例链接。

### 4.4 明确不移植的东西

| 项 | 理由 |
|---|---|
| 每切 2–5 秒、段 ≤ 15 秒、同框 ≤ 3 人、爽点间隔 ≤ 3 集、单句 ≤ 35 字、4.5 字/秒 | 数量配额，违反 CONTRIBUTING 第 2 条；与电影冲突；能力由 `native_duration_seconds` 与集时长报告承担 |
| 节拍「恰好一次」认领 | creator-first 不生成 block ID；`SHT-08` 已管重复；对白逐字覆盖足够 |
| JSON 作为真相、`render` 派生 md | 与「五文档唯一落盘」冲突 |
| `.gates.jsonl` 门失败累积 | shuohao 自己标注为试验，长期没人打开就该删 |
| `realistic` / `ghibli` 二元预设 | 六张形态卡已覆盖且更细；预设的「反向词冲突」只保留为审查项 |
| 「机器字段永远英文」 | drama 的提示词语言由项目声明，不固定 |
| `hookBeat` 前 3 拍冷开场、结尾必悬念 | 短剧观看契约专属 |
| Chaoge 的固定问句、永久终止、联系方式、`{{Image N}}`、8K/4K 质量词、字号百分比 | 引流机制与供应商写法，不属于方法 |
| Chaoge 的 P0/P0A 十项固定顺序 | `creative-brief.md` / `story-engine.md` / `occurrence-extraction.md` 已覆盖，只补世界坐标 |
| 新 skill 目录（如 `short-drama-film`） | `EXPECTED_SKILLS` 固定；能力落在现有 skill |
| 单页离线 HTML 报告 | Dashboard 已存在；列为 Phase 5 可选 |

## 5. 新增规则 ID 与诊断代码草案

当前各前缀最大值：`AST-13`、`IMG-14`、`SHT-25`、`VID-24`、`CON-07`、`REV-11`、`STY-24`、`SCR-17`。

| ID | 等级 | 一句话 | 落点 |
|---|---|---|---|
| AST-14 | reviewed_invariant | 派生条目声明 2–4 项跨造型稳定的继承锚点与不继承项；非双胞胎/克隆不得高度相似 | assets/stage-contract |
| AST-15 | structural_invariant | `派生自` 解析到存在的人物条目且无环；上游无已核对身份 `REF-` 时派生条目不得声称就绪 | assets/stage-contract |
| IMG-15 | craft_default | 角色设定板版式从版式卡选用，服务 reuse_job | image-prompts/stage-contract |
| IMG-16 | structural_invariant | 道具条目声明尺度档位时，其 IMG 正文含对应尺度短语 | image-prompts/stage-contract |
| IMG-17 | craft_default | 不同人物身份板正文相似度过高只提示不阻断 | image-prompts/stage-contract |
| SHT-26 | craft_default | 观看契约声明后，竖屏取向的 craft_default 整体让位 | storyboard/stage-contract |
| SHT-27 | structural_invariant | 已接受档案声明原生时长时，投产镜头（或容器）时长落在区间内 | storyboard/stage-contract |
| VID-25 | structural_invariant | 方言结构标记（素材编号、切点时刻、时间戳区间、逐字对白块）与分镜/绑定逐字对账 | video-prompts/stage-contract |
| VID-26 | structural_invariant | 开关生效时，剧本每句对白/VO/OS 逐字被视频正文或分镜声音字段承载，或显式省略 | video-prompts/stage-contract |
| STY-25 | taste_option | 全片情绪曲线为可选产物 | develop/stage-contract |

既有 ID 补 Markdown 实现（不新增 ID）：`SHT-16`（集时长加总）、`VID-13`/`VID-15`（交付分组算术与全集账目）、`SHT-01`（对白子集）。

诊断代码（`dialect_check.py`，须登记在 `minimax-h3.md` / `seedance-2.5.md`）：`VID_DIALECT_PICTURE_INDEX`、`VID_DIALECT_CUT_TIME`、`VID_DIALECT_RANGE`、`VID_DIALECT_FIELD_ORDER`、`VID_DIALECT_DIALOGUE_VERBATIM`、`VID_DIALECT_PROFILE_UNSET`（信息级：档案未声明方言，跳过）。`creator_markdown_check.py` 的扩展沿用中文消息，不引入代码。

## 6. 文件变更清单

### 新增

| 路径 | 内容 |
|---|---|
| `docs/film-merge-design.md` | 本文 |
| `docs/film-workflow.md` | 电影 creator-first 全流程 |
| `examples/creator-first-film/README.md` + `EP001/` 五文档 | 横屏电影合成示例 |
| `skills/short-drama/references/viewing-contract.md` | 观看契约 |
| `skills/short-drama-assets/references/kinship-and-derivation.md` | 血缘/派生 |
| `skills/short-drama-image-prompts/references/character-sheet-layouts.md` | 设定板版式卡 |
| `skills/short-drama-develop/references/emotion-curve.md` | 情绪曲线（可选） |
| `skills/short-drama-video-prompts/scripts/dialect_check.py` | 方言标记对账 |
| `skills/short-drama-produce/references/providers/codex-imagegen.md` | codex adapter 文档 |
| `tests/test_dialect_check.py` | 新脚本测试 |

### 修改

| 路径 | 改动 |
|---|---|
| `skills/short-drama/references/knowhow-index.md` | 路由行：血缘与派生、观看契约、设定板版式、方言标记对账 |
| `skills/short-drama/references/creator-documents.md` | `视觉设定.md` 示例加 `派生自`、`尺度`、项目视觉方向段；`分镜.md` 加「省略」行与「交付分组」章节语法 |
| `skills/short-drama/references/form-cards/实拍.md` | 摄影系统一致、世界坐标、色彩与声音策略 |
| `skills/short-drama/references/look-development.md` | 影视参考翻译成可见参数 |
| `skills/short-drama/scripts/creator_markdown_check.py` | 派生解析/环检测；时长解析/加总报告/原生区间；交付分组算术；尺度短语；相似度警告；`--dialogue-coverage` |
| `skills/short-drama-assets/references/identity-vs-variant.md`、`asset-review-checklist.md`、`stage-contract.md`、`SKILL.md` | 派生入口与规则登记 |
| `skills/short-drama-assets/references/prop-and-state.md` | 入选判据一句 |
| `skills/short-drama-image-prompts/references/character-and-look.md`、`prop-plate.md`、`review-and-fixtures.md`、`stage-contract.md`、`SKILL.md` | 派生身份板、道具档案照与尺度、自相矛盾检查、规则登记 |
| `skills/short-drama-storyboard/references/production-shot-grammar.md`、`blocking-playbooks.md`、`stage-contract.md`、`SKILL.md` | 契约条件句、`SHT-26/27` |
| `skills/short-drama-video-prompts/references/minimax-h3.md`、`seedance-2.5.md`、`stage-contract.md`、`SKILL.md` | 机械核对小节与代码目录、`VID-25/26`、脚本链接 |
| `skills/short-drama-develop/references/director-brief-craft.md`、`stage-contract.md`、`SKILL.md` | 世界坐标、`STY-25`、情绪曲线链接 |
| `skills/short-drama-produce/scripts/provider_adapters.py`、`SKILL.md` | `codex-imagegen` |
| `skills/short-drama-review/references/rubric-assets-prompts.md`、`production-quality-gates.md` | 派生、版式、自相矛盾、方言标记的审查问句 |
| `tests/test_creator_first_golden.py` | `EXPECTED_KNOWHOW` 更新；第二个 golden；新夹具 |
| `tests/test_provider_adapters.py` | 假 codex |
| `CHANGELOG.md` | `[Unreleased]` 按 Added/Changed 归类：`structural_invariant` 新增记 Changed |
| `README.md` / `README_EN.md` | 电影长片段落、第 5 个 adapter |

## 7. 分阶段实施与验收

每阶段一个分支上的若干提交，每个提交只动一个 skill 目录（CONTRIBUTING 的提交约定）。

### Phase 0 · 基线（本机，半天）

- 在 fork 上 `git checkout -b film/merge`。
- 跑全量测试与 `ruff`，记录绿色基线 commit。
- 用 `examples/creator-first/EP001` 跑一次 `creator_markdown_check.py`，确认当前行为。
- 验收：测试全绿；本文提交。

### Phase 1 · 知识层（1–2 天，纯 Markdown）

- 4.1-A 的 `kinship-and-derivation.md` 与各处入口；4.1-B 版式卡与 `prop-plate.md`；4.1-C 实拍卡；4.3-A 观看契约与条件句；4.2-E 的入选判据；4.2-F 审查项；规则表登记全部新 ID；`knowhow-index.md` 路由；`EXPECTED_KNOWHOW` 更新；CHANGELOG。
- 验收：`test_suite_anatomy`（链接、锚点、粗体）、`test_creator_first_golden`、`test_shipping_boundaries` 全绿；人工通读一遍每个新文件能从 `SKILL.md` 按需打开。

### Phase 2 · 结构校验（2–3 天，Python）

- 2a `creator_markdown_check.py`：派生解析/环检测（AST-15）；时长解析、加总报告、原生区间（SHT-16/27）；交付分组算术（VID-13/15）；尺度短语（IMG-16）；相似度警告（IMG-17）；`--dialogue-coverage`（VID-26）。
- 2b `dialect_check.py` + `tests/test_dialect_check.py`（VID-25）。
- 验收：新旧测试全绿；`examples/creator-first/EP001` 仍通过（不得让既有示例变红——新检查要么条件生效，要么示例同步补字段并写进 CHANGELOG 升级说明）；每个新诊断都有一条「击穿」测试与一条「正确样本通过」测试。

### Phase 3 · 出图闭环（1 天）

- `codex-imagegen` adapter、文档、假 codex 测试。
- 验收：`python3 scripts/selftest.py`、`provider_adapters.py --selftest`、`test_provider_adapters` 全绿；本机装有 codex 时手工走一次 `prepare → confirm → run` 生成一张角色板到 `剧集/EP001/制作成果/images/`，再由分镜 owner 绑成 `用途：起始帧` 或 `身份` 的 `REF-`。

### Phase 4 · 电影示例与工作流（1–2 天）

- `examples/creator-first-film/EP001`、`docs/film-workflow.md`、README。
- 验收：示例通过 Phase 2 的全部检查并进入 golden 测试；按 `docs/film-workflow.md` 从零走一遍到视频提示词，记录摩擦。

### Phase 5 · 可选

- 情绪曲线 reference（4.1-D）。
- 离线单页报告：`project_tool.py report <project> --out report.html`，借鉴 shuohao 组装器思路（作用域前缀、脚本代理、图片路径重算），但只渲染五文档与 `制作成果/`，不成为第二真相。

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 沙箱无 python3，脚本写完跑不了 | Phase 0 在本机建基线；Phase 2/3 每个提交都在本机跑测试再合并 |
| 新结构检查让上游既有示例变红 | 所有新检查条件生效（字段存在/档案声明/开关打开）；默认路径行为不变 |
| 与上游 drama-skills 后续版本冲突 | 新内容尽量放在新文件；对既有文件只做增量小节与条件句；定期 `git merge upstream/main` |
| 隐性重力仍把模型带回竖屏 | 横屏示例进 golden；条件句写在原段落处而不是另一份文件里 |
| 移植 Chaoge 内容触及其权利 | 全部重写为方法论；不复制提示词模板、固定问句与联系方式 |
| 血缘检查误伤（同姓、称谓） | 派生只认显式 `派生自` 声明，不从名字推断 |
| 方言对账过严阻断合法写法 | 只核对方言文件已明文规定的固定结构；通用路径只查标签不越界 |

## 附录 A · 观看契约声明语法草案

写在 `视觉设定.md` 的「项目视觉方向」段，一行一项：

```markdown
## 项目视觉方向

- 观看契约：电影长片 · 16:9 · 剧场感 · 慢节奏
- 制作形态：实拍
- 摄影系统：数字实拍 · 大画幅传感器 · 定焦球面镜头家族 · 24fps · 需要胶片感时写印片模拟
- 世界坐标：中国东北 · 1998–2003 · 无智能手机 · 固定电话与 BP 机 · 燃煤供暖
```

契约值是封闭词表的组合：`电影长片 | 竖屏短剧 | 横屏剧集 | 静态漫剧`，画幅按 `format.aspect_ratio`，其余为项目自定义标签。声明「电影长片」时 4.3-A 列出的 craft_default 让位。

## 附录 B · 派生（血缘）声明语法草案

写在 `视觉设定.md` 人物条目里，与识别锚点并列：

```markdown
## 人物 · 林小满

- 识别锚点：……
- 派生自：人物「林正国」、人物「周慧」（继承：眉弓走向、鼻梁宽度、下颌角；不继承：年龄、发型、服装、体型、皮肤状态、表情）
- 派生关系：血缘子女
- 派生状态：待上游定稿
```

- `派生自` 只认 `人物「…」`，可多个，用 `、` 分隔；机械核对条目存在与无环。
- `继承` 2–4 项，必须是跨造型稳定的骨相/体态锚点；`不继承` 至少列出年龄与 Look 层内容。
- `派生关系` 取 `血缘子女 | 血缘同辈 | 年龄阶段 | 变异形态 | 双胞胎/克隆 | 宿主与变身`；只有 `双胞胎/克隆` 允许高度相似。
- `派生状态` 由创作者维护：`待上游定稿 | 上游已定稿`；机械核对只在「上游人物本集没有任何 `用途：身份` 的 `REF-`，而派生条目已被某镜绑定身份图」时报错。
- 图片提示词侧：派生身份板的 `参考：` 用上游定稿图各占一个 `REF-`（`用途：身份`；`控制：` 只写声明的继承项；`不得控制：` 逐字带上不继承项）。

## 附录 C · `codex-imagegen` adapter 契约草案

adapter 配置（项目外）：

```json
{"adapters": {"codex-imagegen": {"command": ["python3", "/absolute/path/provider_adapters.py", "codex-imagegen"], "timeout_seconds": 900}}}
```

- 环境：本机 codex 登录态；可选 `CODEX_BIN` 指定二进制；不读取任何 API key。
- 输入：已确认 image job，恰好一个 `.png` 输出；`references` 0–16 张。
- 行为：定位版本最高的 codex；`argv = [codex, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "-i", ref1, "-i", ref2, …]`；prompt 经 stdin；cwd 为 `output_root`；环境剥离 `NODE_OPTIONS`；prompt 末尾要求把最终 PNG 复制到 `output_root/<目标文件名>` 并只回文件路径；结束后核对文件存在且为常规文件。
- 输出：契约 `outputs[{target, source}]`；失败输出白名单错误对象（`category` 取 `timeout | provider_error | missing_output`）。
- 限制：不支持透明背景；画幅只能写进正文；一次一图；跨图画风一致性靠链式参考（把第一张成图绑成 `用途：风格` 的 `REF-`）。

## 附录 D · 方言结构标记对账规则草案

MiniMax H3（`video_prompt_dialect: minimax-h3`）：

1. 本镜「输入参考图」按 `顺序` 排出图片序列；正文中出现的每个 `<Picture N>` 满足 `1 ≤ N ≤ 图片数`；出现 `<Video N>` / `<Audio N>` 时同理按各自类别计数。
2. Base/首帧/首尾帧为三段、full-reference 为六段，字段名齐全且顺序固定；单镜也有 `[Shot 1]`。
3. 交付分组容器：第 k 个成员（k ≥ 2）的 `[Shot k] At mm:ss.mmm,` 中的时刻等于前 k−1 个成员已接受时长之和（保留三位小数）。
4. 每个 `<d>[<语言>] …</d>` 内文本去空白后逐字存在于本镜来源场次的 `剧本.md` 对白/VO/OS 行中。

Seedance 2.5（`video_prompt_dialect: seedance-2.5`）：

1. 多镜正文的 `镜头 k [a–b]` 区间按 k 递增、`a` 等于上一段 `b`、首段 `a = 0:00`、末段 `b` 等于镜头或容器已接受时长。
2. `@图片N` / `@视频N` / `@音频N` 的 N 不超过同类素材数。
3. `{角色用中文说：“…”}` 内文本逐字存在于来源场次。

通用路径：只检查形如 `<Picture N>` / `@图片N` 的标签不引用不存在的序号；其余不做断言。档案未声明方言时输出信息级 `VID_DIALECT_PROFILE_UNSET` 并退出 0。

## 9. 实施记录（2026-09-03）

按上文 Phase 1–4 实施完成；Phase 5（情绪曲线已作为可选 reference 落地，离线单页报告未做）。

| 阶段 | 落地 | 验证 |
|---|---|---|
| Phase 1 知识层 | 新增 `kinship-and-derivation.md`、`character-sheet-layouts.md`、`viewing-contract.md`、`emotion-curve.md`；实拍卡、`prop-plate.md`、`creator-documents.md`、`knowhow-index.md`、四份 `stage-contract.md`、审查 rubric、CHANGELOG 增量修改 | 仓库自己的 Markdown 规则（链接、锚点、粗体收尾）复刻检查通过；`test_creator_first_golden` 的知识清单与规则目录断言已更新 |
| Phase 2 结构校验 | `creator_markdown_check.py`：派生解析/环/就绪、时长账目（只报告）、原生区间、交付分组算术、尺度短语、相似度警告、`--dialogue-coverage`；新增 `dialect_check.py`（H3 / Seedance 2.5 结构标记逐字对账） | `tests/test_creator_first_film.py`（26 项）、`tests/test_dialect_check.py`（17 项）与既有 `test_creator_first_golden`、`test_confirmed_production` 全绿 |
| Phase 3 出图闭环 | `provider_adapters.py` 新增 `codex-imagegen`（版本探测、stdin 提示词、剥离 `NODE_OPTIONS`、白名单错误），`providers/codex-imagegen.md`，SKILL/README | `tests/test_provider_adapters.py` 新增假 codex 夹具三项；`--selftest` 通过；真机 `prepare → confirm → run` 待创作者本机手工走一次 |
| Phase 3b Seedream 出图 | `provider_adapters.py` 新增 `seedream`（火山方舟 `/images/generations`，与 Seedance 共用 `ARK_API_KEY`，`SEEDREAM_MODEL` 显式、尺寸显式、`b64_json` 单图、参考图 base64 内联、上限与 `output_format` 字段由部署声明），`providers/seedream.md`，SKILL/README/CHANGELOG，`tests/test_shipping_boundaries.py` URL 白名单 | `tests/test_provider_adapters.py` 新增 `SeedreamTests` 四项（契约、拒绝、离线运行、安全失败）；`--selftest` 通过；真机出图待创作者本机走一次 |
| Phase 4 示例与工作流 | `examples/creator-first-film/`（《冻河》第一本：契约、派生、尺度、锁、省略、交付分组、Seedance 时间戳）、`docs/film-workflow.md`、README 段落 | 两条机械核对 CLI 对示例均返回 `OK`；示例进入 `FilmExampleTests` |

沙箱里通过 `uv` 找到了 Python 3.12，所以上表的测试都在沙箱实跑过；仍需创作者在本机做的三件事：
在本机解释器（含 3.9 下限）跑一遍全量 `unittest discover` 与仓库配置的 `ruff check`；装有 codex 时用
`codex-imagegen` 真出一张角色板；在 `film/merge` 分支上按 skill 目录拆提交。

未移植项与 §4.4 一致。已知取舍：派生就绪判断按 `REF-` 中文名称是否含条目名称匹配图片归属（与分镜给参考图
起名的习惯一致，但同名前缀会误判）；身份板相似度只做词级 Jaccard 提示；对白覆盖用启发式识别剧本对白行
（说话人 ≤ 12 字、可带括注），未复用 `screenplay_index.py` 的完整语法。
