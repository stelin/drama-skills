# 项目命令

从 `short-drama` 技能安装目录运行，不依赖当前工作目录：

```text
python3 <core>/scripts/project_tool.py init <project> --title <title>
python3 <core>/scripts/project_tool.py status <project>
python3 <core>/scripts/project_tool.py publish <project> --owner short-drama-write --artifact-id EP001:script --output 剧集/EP001/screenplay.md=_work/screenplay.next.md --input 项目开发/episode-map.jsonl
python3 <core>/scripts/project_tool.py accept <project> --artifact-id EP001:script --decision accepted [--note <note>]
python3 <core>/scripts/project_tool.py review <project> --artifact-id EP001:script --verdict approve [--reviewer <label>] [--note <note>]
python3 <core>/scripts/project_tool.py package <project> --episode EP001 --include 剧集/EP001/screenplay.md [--omit <path>=<reason>]
python3 <core>/scripts/project_tool.py verify <project> --episode EP001
```

## 发布

`publish --output <target>=<source>` 可重复。source 必须是项目内安全的 UTF-8 Markdown、
JSON 或 JSONL；命令先验证全部 source，再逐文件用临时文件和原子替换发布。每个 artifact 的
output 路径只能有一个 owner。

`--input <path>` 只声明该产物实际读取的直接项目文件。工具内部保存当前摘要，用于之后判断
`update_needed`；调用者不计算、不粘贴 hash，也不声明传递依赖。若 A 直接读 B，就声明 B；
B 又读 C 不会让 A 自动过期，只有 A 下次实际重建时才读取当前 B。

默认只允许发布到标准阶段目录。`输入/**`、`.short-drama/**`、`交付/**` 和任何
`short-drama.json` 都不可作为 publish 目标。分集目录使用 `EP001` 形式。未登记的临时路径
必须显式加 `--allow-unregistered-path`。

单次发布不会提供跨多个文件的事务或恢复日志。进程中断最多留下未被采用的临时文件；已完成
的每个目标都是完整文件。再次运行同一发布即可继续。

## 接受与复核

发布后状态是 `needs_confirmation`。创作者决定当前版本：

```text
... accept <project> --artifact-id <id> --decision accepted
... accept <project> --artifact-id <id> --decision rejected --note <reason>
```

接受不要求单独证据文件或 target hash。输出或直接输入已变化时命令拒绝沿用旧决定。

接受后可记录复核：

```text
... review <project> --artifact-id <id> --verdict approve --reviewer 同事复核
... review <project> --artifact-id <id> --verdict revise --note <bounded-fix>
```

`approve_with_notes` 也计为通过；`provisional` 保持未批准。reviewer 是创作质量实践，
不是 CLI 身份认证协议：有独立上下文时使用，没有时诚实填写自检标签。

重新 `publish` 会清除该 artifact 的旧接受与复核。`status` 在读取时检查当前输出和直接输入，
只报告 `update_needed`，不修改状态文件，也不传播或保存“下游闭包”。

## 打包与复核

`package` 要求每个 `--include` 都属于本集并且当前为 `approved`。它把所选文本/JSON 复制到
`交付/<EP>/artifacts/`，写入 manifest 与 checksums，并记录 `--omit` 的理由。再次打包用新目录
原子替换旧包。

`verify` 重新计算交付文件校验和，并报告缺失、篡改或未登记新增文件。校验和只服务于准确交付，
不参与创作状态或依赖传播。

## Dashboard 启动

```text
python3 <core>/scripts/dashboard_server.py --workspace <workspace> --port 0 --open
```

`--host` 只接受回环主机。服务拒绝符号链接和路径越界，使用每次启动独立的本机会话。
Dashboard 是展示与有限文本编辑层，不承担生成、接受、复核或打包编排。保存使用当前文件版本
做冲突检查；项目文件已被其他工具修改时返回冲突，不覆盖新内容。
