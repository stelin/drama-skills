---
name: short-drama-produce
description: 在创作者明确确认后，执行短剧项目的图片、视频或 TTS/配音生产任务，并把结果与精简运行记录落回项目。用户说“生成这张图/这段视频/这句配音”“开始跑图/跑视频/合成语音”“把已确认提示词送去生产”，或要求批量执行已确认媒体任务时使用；不负责创作提示词、镜头、台词或声音身份，也绝不把预览、继续、预算说明或既有接受状态当作本次付费生产确认。
license: MIT
---

# 确认后生产

本技能只负责把已经写好的生产规格安全送到运行环境配置的 adapter。图片提示词仍归
`$short-drama-image-prompts`，视频提示词归 `$short-drama-video-prompts`，台词与录音表归
`$short-drama-write`，声音身份归 `$short-drama-assets`。

## 硬闸门

每次生产都必须经过以下四步，顺序不可合并：

1. 建立一个有边界的 job：一种 modality、明确数量、完整 prompt/spec、参考文件、参数、输出路径和 adapter profile。
2. 运行 `prepare`，把返回的完整预览展示给创作者，尤其是数量、prompt、references、outputs、
   overwrite 与 adapter。
3. 等创作者在**看到这份预览之后**明确确认。只有明确同意这项当前任务，才运行 `confirm`；
   “继续”“都做完”“预算没问题”、上游内容已接受或之前确认过另一版，都不算本次生产确认。
4. 运行 `run`。它会在启动 adapter 前消费一次确认；成功或失败后再次执行都必须重新确认，
   防止失败重试意外产生第二笔费用。

job、prompt、参数、输出路径或直接输入任一变化，旧确认立即失效。不得代替创作者填写确认。
当前已确认 job 是本轮唯一工作单元；运行结束后回报结果并交还控制权，不自动准备下一批或启动审查。

## 命令

先把待执行任务写成 JSON；格式和 adapter 契约见
[adapter-contract.md](references/adapter-contract.md)。命令由
[production_tool.py](scripts/production_tool.py) 提供，然后运行：

```text
python3 <本技能目录>/scripts/production_tool.py prepare <project> --job <job.json>
python3 <本技能目录>/scripts/production_tool.py confirm <project> --job-id <id> --confirmation "CONFIRM <id> <code>"
python3 <本技能目录>/scripts/production_tool.py run <project> --job-id <id> --adapter-config <outside-project-config.json>
python3 <本技能目录>/scripts/production_tool.py status <project> --job-id <id>
```

`prepare` 只验证并预览，不生产。`confirm` 只保存与当前 job 指纹绑定的一次性确认。
`run` 才启动 adapter。

## 输入选择

- **image**：读取当前图片 prompt/spec、必要参考图和明确的输出尺寸/数量。
- **video**：读取当前 motion spec、对应 shot/keyframe、必要首尾帧和时长/画幅。
- **tts**：读取当前录音表中的原句、说话人/声音参考和本句表演要求；不得在生产 job 中改词。

一个 job 不混合 modality。大批量工作拆成创作者能看清数量和成本边界的小 job；不为方便把整季
隐式塞进一次确认。

## Adapter 边界

adapter 配置必须在项目外，只包含 argv 命令和超时；凭据由 adapter 自己从进程环境或系统凭据
存储读取。项目 job、确认记录、运行记录和 Dashboard 都不得保存密钥。

脚本以 JSON stdin 调用 argv 数组，不使用 shell，不拼接命令。adapter 返回本地临时文件；工具只
接受与已确认 targets 完全一致的结果，并把完整文件原子复制到项目的 `production/制作成果`
目录。套件不写死供应商、模型或即将变化的 API。

仓库自带 `fixture_adapter.py` 只用于离线测试，不代表真实生成质量或默认生产 adapter。

## 结果与复核

成功后回报实际输出路径、媒体类型和运行状态；不要把“adapter 返回成功”写成质量结论。
如需质量复核，报告可把已有结果另行交给 `$short-drama-review`；不要在生产调用中自动启动复核。
Dashboard 只负责展示这些文件和运行摘要，不提供 adapter 设置或生产按钮。
