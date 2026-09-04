# Creator-first 电影长片示例

《冻河》第一本展示一个横屏电影项目在默认工作流里的全部创作表面：项目配置 `short-drama.json` 加一集五份
Markdown，没有创作阶段 JSON/JSONL、索引、指纹、QA 或隐藏投影。它与 [《让你管账号》](../creator-first/EP001/)
的差别只在观看契约与由此让位的默认：

- `short-drama.json`：16:9、中文提示词、目标 65 秒、已接受的 Seedance 2.5 生产档案（原生区间 4–30 秒、同轨声音）；
- [`剧集/EP001/视觉设定.md`](剧集/EP001/视觉设定.md)：「项目视觉方向」声明观看契约为电影长片，实拍形态卡的摄影系统、
  世界坐标与环境色彩写在同一段；林小满是 `派生自` 林正国与周慧的派生条目（`派生状态：待上游定稿`）；车钥匙
  声明 `尺度：手持级`；小满的棉袄有一把连续性锁；
- [`剧集/EP001/分镜.md`](剧集/EP001/分镜.md)：第一个镜头之前有「省略的对白」一节；建立镜头与固定机位等待按电影契约
  作为常规选项，镜头时长 5–12 秒；
- [`剧集/EP001/视频提示词.md`](剧集/EP001/视频提示词.md)：Seedance 2.5 中文正文、花括号逐字对白、`镜头 k [a–b]`
  时间戳；末尾「交付分组」把平房一场的三个镜头装进一个 22 秒容器，容器自己的正文用四级标题；
- [`剧集/EP001/图片提示词.md`](剧集/EP001/图片提示词.md)：三种设定板版式各用了一次，道具板是 3:4 单件档案照。

本例未提供或生成图片，全部镜头明确选择文生视频；派生条目因此停在「待上游定稿」，正是 `AST-15` 要求的顺序。
两条机械核对都应通过：

```bash
python3 skills/short-drama/scripts/creator_markdown_check.py examples/creator-first-film/剧集/EP001 \
  --project-root examples/creator-first-film --dialogue-coverage
python3 skills/short-drama-video-prompts/scripts/dialect_check.py examples/creator-first-film/剧集/EP001 \
  --project-root examples/creator-first-film
```

这是创作效果样例，不是格式 schema；具体约束以各 owner skill 与 creator-first 文档契约为准。
