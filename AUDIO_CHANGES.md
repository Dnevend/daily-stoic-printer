# 文章语音功能改动说明

## 改动内容

1. **新增 `src/dailyprint/enrich/audio.py`**
   - `build_speech_text(issue, include_translation=False, max_words=0)`：纯函数，构造朗读文本。
   - `synthesize(text, out_path, voice="Samantha")`：调用 macOS `/usr/bin/say` 合成语音；有 ffmpeg 时转 OGG/Opus，否则保留 AIFF/WAV。
   - `send_audio(path, channel, target, caption)`：调用 `/opt/homebrew/bin/openclaw message send` 发送语音；调用前前置 `/opt/homebrew/bin` 到 PATH，避免 launchd 干净环境找不到 `node`。

2. **配置扩展 `src/dailyprint/config.py`**
   - 新增 `[audio]` 段：`enabled`、`voice`、`include_translation`、`max_words`、`send`、`channel`、`target`、`out_dir`。
   - 新增 `Paths.audio` 属性，默认 `prints/audio/`。

3. **CLI 扩展 `src/dailyprint/cli.py`**
   - `print` 子命令默认生成并发送语音；加 `--no-audio`、`--audio-voice`。
   - 新增 `audio` 子命令：只生成/可选发送，便于手动验证。
   - `cmd_print` 末尾调用 `_run_audio`，整个调用包在 `try/except` 里，**失败不影响打印返回码**。

4. **示例配置与文档**
   - `config.example.toml` 增加 `[audio]` 示例。
   - `README.md` 增加「文章语音」章节与命令说明。

5. **测试 `tests/test_audio.py`**
   - 覆盖 `build_speech_text` 纯函数。
   - 覆盖 `say` / `openclaw` 缺失时的降级行为。
   - 覆盖 `_run_audio` 异常被吞掉，不影响主流程。

## 开关方式

- 关闭语音：`config.toml` 中 `[audio].enabled = false`，或 `dailyprint print --no-audio`。
- 只生成不发送：`dailyprint audio --no-send -o out.ogg`。
- 手动发送：`dailyprint audio --send`。

## 验证结果

- 环境：`/opt/homebrew/bin/uv venv && /opt/homebrew/bin/uv pip install -e ".[dev,images]"` ✅
- 语法检查：`.venv/bin/python -m py_compile` 覆盖改动文件 ✅
- 测试：`.venv/bin/pytest` —— **107 passed**（原 97 + 新增 10）✅
-  lint：`.venv/bin/ruff check .` —— 干净 ✅
- 端到端：`dailyprint -v audio --send -o /Users/dnevend/.openclaw/workspace/daily-audio-e2e.ogg` 成功把 OGG/Opus 语音发送到 Telegram chat `1419937886` ✅
- 负向测试：`_run_audio` 在 `synthesize` 抛异常时仍不抛异常，打印主流程不受影响（单测覆盖）✅

## 遗留风险

- `openclaw` 对本地媒体路径有访问策略；测试发现 `/tmp` 和项目目录被拒绝，需把文件放在 `~/.openclaw/workspace` 或 openclaw 允许的路径内。默认 `prints/audio/` 在部分 openclaw 配置下可能被拒绝，届时可调整 `[audio].out_dir`。
- `say` 是 macOS 专属，代码运行在其他系统上会直接跳过并记 warning。
- launchd 环境下若 `PATH` 未包含 `/opt/homebrew/bin`，已显式前置该路径；若 openclaw 本身被装在其他位置，需改 `[audio]` 暂不提供覆盖，当前写死 `/opt/homebrew/bin/openclaw`。
