# 文章语音功能改动说明

## 本次改动（edge-tts 神经音色 + say 兜底）

1. **TTS 引擎升级**
   - 默认优先使用 `uvx edge-tts` 神经音色（默认 `en-US-AriaNeural`），通过 `edge-tts --voice ... --file ... --write-media ... --rate=-10%` 生成 mp3。
   - 失败（`uvx` 不存在 / `edge-tts` 报错 / 联网失败）时**自动降级**到 macOS `/usr/bin/say`（音色 `Samantha`，语速 160 wpm）。
   - `engine = "say"` 时直接走 say；`engine = "edge"` 时不降级。

2. **`src/dailyprint/enrich/audio.py`**
   - 新增 `synthesize_edge(text, out_path, voice, rate)`：调用 `uvx edge-tts` → ffmpeg 转 OGG/Opus。
   - 原 `synthesize` 拆分为 `synthesize_say(text, out_path, voice, rate_wpm)`，支持 `--rate` 放慢语速。
   - 新 `synthesize(text, out_path, cfg)`：按 `cfg.engine` 选择；`auto` 时先 edge 后 say。
   - 新增 `send_dir(cfg)` / `archive_dir(cfg, paths)`：
     - 发送文件默认写到 OpenClaw 允许目录：`~/.openclaw/workspace/.openclaw/tmp/dailyprint-audio/`
     - 归档目录默认 `prints/audio/`
   - 保留 `build_speech_text` 纯函数不变。

3. **`src/dailyprint/config.py`**
   - `[audio]` 扩展：`engine`、`voice`、`rate`、`say_voice`、`say_rate`、`send_dir`、`archive_dir`；保留 `out_dir` 兼容上一版（等价于 `archive_dir`）。

4. **`src/dailyprint/cli.py`**
   - `print` 子命令增加 `--audio-engine`、`--audio-rate`。
   - `audio` 子命令增加 `--engine`、`--rate`、`--say-voice`、`--say-rate`。
   - `_run_audio` / `cmd_audio` 发送前先把文件放到 `send_dir`，发送成功后再归档到 `archive_dir`；归档失败不影响发送。

5. **示例配置与文档**
   - `config.example.toml` 更新 `[audio]` 示例。
   - `README.md` 更新「文章语音」章节与命令一览。

6. **测试 `tests/test_audio.py`**
   - 覆盖 `build_speech_text` 纯函数。
   - 覆盖 edge/say 缺失时的降级行为。
   - 覆盖引擎选择逻辑（`edge`、`say`、`auto` 降级）。
   - 覆盖 `_run_audio` 异常被吞掉，不影响主流程。
   - 覆盖 `send_dir` / `archive_dir` 与 `out_dir` 兼容。

## 开关方式

- 关闭语音：`config.toml` 中 `[audio].enabled = false`，或 `dailyprint print --no-audio`。
- 只用 say：`dailyprint print --audio-engine say` 或 `dailyprint audio --engine say`。
- 切换 edge 音色：`dailyprint print --audio-voice en-US-JennyNeural`。
- 调整语速：`dailyprint audio --rate "-20%"`。
- 只生成不发送：`dailyprint audio --no-send -o out.ogg`。
- 手动发送：`dailyprint audio --send`。

## 验证结果

- 环境：`.venv` 已存在；`.venv/bin/python -m py_compile src/dailyprint/enrich/audio.py src/dailyprint/cli.py src/dailyprint/config.py tests/test_audio.py` ✅
- 测试：`.venv/bin/pytest` —— **114 passed**（原 107 + 新增 7）✅
- lint：`.venv/bin/ruff check .` —— 干净 ✅
- 端到端：
  - 命令：`.venv/bin/dailyprint -v audio --send`
  - 输出：`edge-tts 合成完成: /Users/dnevend/.openclaw/workspace/.openclaw/tmp/dailyprint-audio/2026-10-17.ogg (en-US-AriaNeural, -10%)`，随后 `已发送语音`
  - 音色：`en-US-AriaNeural`，语速：`-10%`，格式：OGG/Opus
  - 目标：Telegram chat `1419937886` ✅
- 负向测试：
  - 模拟 edge-tts 不可用：`.venv/bin/dailyprint -v audio --send --engine auto --voice NonexistentVoiceNeural`
    - edge-tts 报错 `Invalid voice 'NonexistentVoiceNeural'`，自动降级到 say，仍然 `已发送语音` ✅
  - say 也失败仍不阻断：`dailyprint audio --engine edge --voice BadVoice` 返回 `exit=0`（单测 `test_run_audio_swallows_exception` 同步覆盖）✅

## 遗留风险

- `edge-tts` 需要联网下载语音；断网 / 微软服务不可用时会降级到 say，音色质量会下降。
- `uvx` 首次调用可能需下载 `edge-tts` 包（已缓存于 `~/.cache/uv`），极端网络差时可能超时；已把超时设到 180 秒。
- `say` 仍是 macOS 专属，非 macOS 环境会跳过并记 warning。
- 发送用目录基于当前 OpenClaw 允许路径；若 OpenClaw 配置变更，需同步调整 `[audio].send_dir`。
