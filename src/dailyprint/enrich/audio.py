"""文章语音合成与 Telegram 发送（可选，失败不阻断主流程）。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import Issue
from ..textutil import truncate_words

log = logging.getLogger("dailyprint")

SAY = "/usr/bin/say"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
OPENCLAW = "/opt/homebrew/bin/openclaw"


def build_speech_text(
    issue: Issue, *, include_translation: bool = False, max_words: int = 0
) -> str:
    """构造要朗读的纯文本。默认只读英文正文；max_words <= 0 表示不限制。"""
    text, _ = truncate_words(issue.article.text or "", max_words)
    parts = [text]
    if include_translation and issue.translation:
        parts.append("\n\nTranslation.\n" + issue.translation)
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _run(cmd: list[str], timeout: float, env: dict[str, str] | None = None) -> tuple[int, str, str]:
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


def synthesize(
    text: str,
    out_path: Path,
    voice: str = "Samantha",
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

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    ) as text_file:
        text_file.write(text)
        text_path = Path(text_file.name)

    aiff_path = out_path.with_suffix(".aiff")
    try:
        rc, _, err = _run([say, "-v", voice, "-f", str(text_path), "-o", str(aiff_path)], 120)
        if rc != 0:
            log.warning("say 合成失败 (rc=%s): %s", rc, err.strip())
            return None

        if shutil.which(ffmpeg) and Path(ffmpeg).exists():
            opus_path = out_path.with_suffix(".ogg")
            rc, _, err = _run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(aiff_path),
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "32k",
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    str(opus_path),
                ],
                60,
            )
            if rc == 0:
                try:
                    aiff_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return opus_path
            log.warning("ffmpeg 转码失败 (rc=%s): %s；保留 AIFF", rc, err.strip())
        else:
            log.warning("ffmpeg 不存在，直接发送 AIFF: %s", ffmpeg)

        return aiff_path
    finally:
        try:
            text_path.unlink(missing_ok=True)
        except OSError:
            pass


def send_audio(
    path: Path,
    channel: str,
    target: str,
    caption: str,
    openclaw: str | None = None,
    timeout: float = 30,
) -> bool:
    """通过 OpenClaw 发送语音文件；任何异常都只返回 False。"""
    openclaw = openclaw or OPENCLAW
    if not Path(openclaw).exists():
        log.warning("openclaw 不存在，跳过发送: %s", openclaw)
        return False

    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")

    cmd = [
        openclaw,
        "message",
        "send",
        "--channel",
        channel,
        "-t",
        target,
        "--media",
        str(path.resolve()),
        "-m",
        caption,
    ]
    try:
        rc, out, err = _run(cmd, timeout, env=env)
        if rc == 0:
            log.info("已发送语音: %s", path)
            return True
        log.warning("openclaw 发送失败 (rc=%s): %s", rc, (err or out).strip())
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("openclaw 发送异常: %s", e)
        return False
