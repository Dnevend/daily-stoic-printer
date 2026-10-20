"""文章语音合成与 Telegram 发送（可选，失败不阻断主流程）。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..models import Issue
from ..textutil import truncate_words

if TYPE_CHECKING:
    from ..config import AudioConfig

log = logging.getLogger("dailyprint")

SAY = "/usr/bin/say"
UVX = "/opt/homebrew/bin/uvx"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
OPENCLAW = "/opt/homebrew/bin/openclaw"

EDGE_VOICE_DEFAULT = "en-US-AriaNeural"
EDGE_RATE_DEFAULT = "-10%"
SAY_VOICE_DEFAULT = "Samantha"
SAY_RATE_DEFAULT = 160


def _default_send_dir() -> Path:
    """OpenClaw 允许的本地媒体根目录下的音频临时目录。"""
    return Path.home() / ".openclaw" / "workspace" / ".openclaw" / "tmp" / "dailyprint-audio"


def send_dir(cfg: AudioConfig) -> Path:
    """发送用音频目录；空配置时使用 OpenClaw 允许目录下的默认路径。"""
    if cfg.send_dir:
        return Path(cfg.send_dir).expanduser().resolve()
    return _default_send_dir().resolve()


def archive_dir(cfg: AudioConfig, paths) -> Path:
    """归档用音频目录；空配置时使用项目 prints/audio。"""
    if cfg.archive_dir:
        return Path(cfg.archive_dir).expanduser().resolve()
    # 兼容上一版 out_dir 命名
    if cfg.out_dir:
        return Path(cfg.out_dir).expanduser().resolve()
    return paths.audio.resolve()


def build_speech_text(
    issue: Issue, *, include_translation: bool = False, max_words: int = 0
) -> str:
    """构造要朗读的纯文本。默认只读英文正文；max_words <= 0 表示不限制。"""
    text, _ = truncate_words(issue.article.text or "", max_words)
    parts = [text]
    if include_translation and issue.translation:
        parts.append("\n\nTranslation.\n" + issue.translation)
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _env_with_path() -> dict[str, str]:
    """返回附带必要 PATH/HOME 的环境变量副本，供 uvx/openclaw 等外部命令使用。"""
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    if "HOME" not in env:
        env["HOME"] = str(Path.home())
    return env


def _run(
    cmd: list[str], timeout: float, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "").decode() if isinstance(e.stdout, bytes) else e.stdout or ""
        err = (e.stderr or "").decode() if isinstance(e.stderr, bytes) else e.stderr or ""
        return -1, out, err


def _write_text_temp(text: str) -> Path:
    """把长文本写入临时文件并返回路径（调用方负责删除）。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    ) as text_file:
        text_file.write(text)
        return Path(text_file.name)


def _convert_to_opus(source: Path, out_path: Path, ffmpeg: str) -> Path | None:
    """用 ffmpeg 把 source 音频转成 OGG/Opus；成功返回 out_path，否则返回 None。"""
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(out_path),
        ],
        60,
    )
    if rc == 0:
        return out_path
    log.warning("ffmpeg 转码失败 (rc=%s): %s", rc, err.strip())
    return None


def _edge_tts_available(uvx: str) -> bool:
    """检查 uvx 是否存在；不检查 edge-tts 包（运行时由 uvx 自动拉取/缓存）。"""
    return shutil.which(uvx) is not None and Path(uvx).exists()


def synthesize_edge(
    text: str,
    out_path: Path,
    voice: str = EDGE_VOICE_DEFAULT,
    rate: str = EDGE_RATE_DEFAULT,
    *,
    uvx: str | None = None,
    ffmpeg: str | None = None,
) -> Path | None:
    """用 ``uvx edge-tts`` 合成神经语音；有 ffmpeg 时转 OGG/Opus，否则保留 mp3。"""
    uvx = uvx or UVX
    ffmpeg = ffmpeg or FFMPEG
    if not _edge_tts_available(uvx):
        log.warning("uvx 不存在，无法使用 edge-tts: %s", uvx)
        return None

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text_path = _write_text_temp(text)
    mp3_path = out_path.with_suffix(".mp3")
    env = _env_with_path()
    try:
        rc, _, err = _run(
            [
                uvx,
                "edge-tts",
                "--voice",
                voice,
                "--file",
                str(text_path),
                "--write-media",
                str(mp3_path),
                f"--rate={rate}",
            ],
            180,
            env=env,
        )
        if rc != 0:
            log.warning("edge-tts 合成失败 (rc=%s): %s", rc, err.strip())
            return None

        if shutil.which(ffmpeg) and Path(ffmpeg).exists():
            opus_path = out_path.with_suffix(".ogg")
            converted = _convert_to_opus(mp3_path, opus_path, ffmpeg)
            if converted:
                try:
                    mp3_path.unlink(missing_ok=True)
                except OSError:
                    pass
                log.info("edge-tts 合成完成: %s (%s, %s)", converted, voice, rate)
                return converted
            log.warning("edge-tts 已生成 mp3，但 ffmpeg 转码失败；保留 mp3")
        else:
            log.warning("ffmpeg 不存在，直接发送 mp3: %s", ffmpeg)

        log.info("edge-tts 合成完成: %s (%s, %s)", mp3_path, voice, rate)
        return mp3_path
    finally:
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass


def synthesize_say(
    text: str,
    out_path: Path,
    voice: str = SAY_VOICE_DEFAULT,
    rate_wpm: int = SAY_RATE_DEFAULT,
    *,
    say: str | None = None,
    ffmpeg: str | None = None,
) -> Path | None:
    """用 macOS ``say`` 合成语音；有 ffmpeg 时转 OGG/Opus，否则保留 AIFF。"""
    say = say or SAY
    ffmpeg = ffmpeg or FFMPEG
    if not Path(say).exists():
        log.warning("say 不存在，跳过语音合成: %s", say)
        return None

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text_path = _write_text_temp(text)
    aiff_path = out_path.with_suffix(".aiff")
    try:
        cmd = [say, "-v", voice, "-f", str(text_path), "-o", str(aiff_path)]
        if rate_wpm > 0:
            cmd += ["--rate", str(rate_wpm)]
        rc, _, err = _run(cmd, 120)
        if rc != 0:
            log.warning("say 合成失败 (rc=%s): %s", rc, err.strip())
            return None

        if shutil.which(ffmpeg) and Path(ffmpeg).exists():
            opus_path = out_path.with_suffix(".ogg")
            converted = _convert_to_opus(aiff_path, opus_path, ffmpeg)
            if converted:
                try:
                    aiff_path.unlink(missing_ok=True)
                except OSError:
                    pass
                log.info("say 合成完成: %s (%s, %s wpm)", converted, voice, rate_wpm)
                return converted
            log.warning("say 已生成 aiff，但 ffmpeg 转码失败；保留 aiff")
        else:
            log.warning("ffmpeg 不存在，直接发送 AIFF: %s", ffmpeg)

        log.info("say 合成完成: %s (%s, %s wpm)", aiff_path, voice, rate_wpm)
        return aiff_path
    finally:
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass


def synthesize(
    text: str,
    out_path: Path,
    cfg: AudioConfig,
) -> Path | None:
    """按配置选择 TTS 引擎；``auto`` 时优先 edge-tts，失败自动降级到 say。"""
    engine = cfg.engine.lower()

    if engine in ("auto", "edge"):
        result = synthesize_edge(
            text,
            out_path,
            voice=cfg.voice,
            rate=cfg.rate,
        )
        if result is not None:
            return result
        if engine == "edge":
            return None
        log.warning("edge-tts 不可用，降级到 say")

    return synthesize_say(
        text,
        out_path,
        voice=cfg.say_voice,
        rate_wpm=cfg.say_rate,
    )


def _openclaw_send(
    args: list[str],
    *,
    openclaw: str | None = None,
    timeout: float = 30,
    ok_message: str = "已发送",
) -> bool:
    """调 ``openclaw message send``；openclaw 缺失或任何异常都只返回 False。"""
    openclaw = openclaw or OPENCLAW
    if not Path(openclaw).exists():
        log.warning("openclaw 不存在，跳过发送: %s", openclaw)
        return False

    env = _env_with_path()

    cmd = [openclaw, "message", "send", *args]
    try:
        rc, out, err = _run(cmd, timeout, env=env)
        if rc == 0:
            log.info("%s", ok_message)
            return True
        log.warning("openclaw 发送失败 (rc=%s): %s", rc, (err or out).strip())
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("openclaw 发送异常: %s", e)
        return False


def send_text(
    text: str,
    channel: str,
    target: str,
    openclaw: str | None = None,
    timeout: float = 30,
) -> bool:
    """通过 OpenClaw 发送纯文本消息；任何异常都只返回 False。"""
    return _openclaw_send(
        ["--channel", channel, "-t", target, "-m", text],
        openclaw=openclaw,
        timeout=timeout,
        ok_message="已发送文本消息",
    )


def send_audio(
    path: Path,
    channel: str,
    target: str,
    caption: str,
    openclaw: str | None = None,
    timeout: float = 30,
) -> bool:
    """通过 OpenClaw 发送语音文件；任何异常都只返回 False。"""
    return _openclaw_send(
        ["--channel", channel, "-t", target, "--media", str(path.resolve()), "-m", caption],
        openclaw=openclaw,
        timeout=timeout,
        ok_message=f"已发送语音: {path}",
    )
