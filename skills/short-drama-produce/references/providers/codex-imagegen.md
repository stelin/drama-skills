# codex-imagegen adapter

Adapter command:

```json
{"command": ["python3", "/absolute/path/provider_adapters.py", "codex-imagegen"], "timeout_seconds": 900}
```

它不读取任何 API key。图片由本机 codex CLI 的内置图像生成工具产出，用的是本机的 codex 登录态
与订阅额度；`preview → confirm → run` 的闸门、job 指纹、审计记录与其它 adapter 完全一样。

Required environment: none. Optional:

- `CODEX_BIN`：显式指定 codex 可执行文件；不指定时依次查 `PATH` 与常见安装位置（`~/.npm-global/bin`、
  `~/.local/bin`、`/opt/homebrew/bin`、`/usr/local/bin`），**取版本号最高的那个**——旧版本会直接拒绝内置
  图像工具，而且报错与出图无关。
- `CODEX_TIMEOUT_SECONDS`：单次生成超时，1–3600，默认 900。

The job must have modality `image` and exactly one output whose extension is `png`、`jpg`、`jpeg` 或 `webp`；
`references` 0–16 张图片。Supported public parameters are `width` plus `height`, or `size`, and `quality`
（`auto` / `low` / `medium` / `high`）；它们只会写进指令散文（`Canvas: 1920x1080.`），因为内置工具按指令
取尺寸，没有参数字段。

## 调用契约

- `argv = [codex, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "-i", <参考图 1>, "-i", <参考图 2>, …]`，
  工作目录是生产工具给出的私有 `output_root`；
- 提示词经 **stdin** 传入：`-i` 是变长参数，会把位置参数当成自己的值吃掉；
- 环境剥离 `NODE_OPTIONS`：codex 自己是 Node CLI，会继承父进程里已经失效的 `--require` 预加载并在启动阶段崩溃；
- 提示词开头要求 codex 把最终选定的图片复制到工作目录的 `result.<ext>` 并只回复路径；adapter 之后核对该文件
  是常规文件、非空、字节签名与目标扩展名一致，再按契约返回 `outputs`；
- 一次调用一张图，绝不批量；每张参考图的中文名、`用途` 译成的 role、允许控制与不得控制范围按
  `reference_bindings` 顺序附在提示词末尾（语言跟随 `parameters.prompt_language`）。

失败时只输出白名单错误对象：`codex_missing`（找不到二进制）、`codex_unavailable`（无法启动）、
`request_timeout`（超时，可重试）、`codex_exit_<n>`（非零退出）、`missing_output` / `invalid_image_data`
（没有写出可用图片）。codex 的 stdout/stderr 不会进入运行记录。

## 已知限制

- 不支持透明背景；要抠图就在提示词里要一块平整的纯色底，后期再去。
- 画布只能写进正文，没有精确的尺寸保证；要严格分辨率用 GPT Image 2 adapter。
- 跨图画风一致性不由本 adapter 保证：把第一张成图绑成 `用途：风格` 的 `REF-` 再出后面几张。
- 没有 codex 登录态时整条路径不可用，adapter 会以 `codex_missing` 或 `codex_exit_<n>` 失败，不会静默降级到
  其它供应商。

学习来源：shuohao-skills 的 codex `$imagegen` 调用契约（版本探测、变长参数走 stdin、剥离 `NODE_OPTIONS`、
一图一次调用），按本套件的 adapter 契约重写。
