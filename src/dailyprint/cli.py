"""命令行入口：``dailyprint <子命令>``。"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from . import __version__
from .config import AppConfig, load_config
from .data import build as build_data
from .enrich.audio import build_speech_text, send_audio, send_text, synthesize
from .models import Article, Issue
from .pipeline import build_issue
from .printers import build_printer
from .render import encode, render, test_page, write_preview
from .sources import available_types
from .state import StateStore
from .storage import Store
from .textutil import WIDTH

log = logging.getLogger("dailyprint")


# ---------------------------------------------------------------- 公共参数

def _add_source_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source", help="来源名（见 `dailyprint sources`）")


def _add_render_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--width", type=int, help=f"每行列数（默认 {WIDTH}）")
    p.add_argument("--words", type=int, help="生词条数（默认 8）")
    p.add_argument("--common", type=int, help="视为'已认识'的高频词个数（默认 6000）")
    p.add_argument("--max-words", type=int, help="打印时正文最多保留多少词（默认 900，0=不限）")
    p.add_argument("--keep-promos", action="store_true", help="不过滤推广/CTA 段落")
    p.add_argument("--no-translation", action="store_true", help="不打印中文译文")
    p.add_argument("--no-images", action="store_true", help="不打印正文配图")
    p.add_argument("--no-cover", action="store_true", help="不打印封面图")
    p.add_argument("--no-vocab", action="store_true", help="不印生词表")
    p.add_argument("--no-zh", action="store_true", help="不印中文释义（打印机不支持中文时用）")


def _add_printer_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ip", help="网络打印机 IP")
    p.add_argument("--port", type=int, help="端口（默认 9100）")
    p.add_argument("--queue", help="CUPS 队列名（USB 打印机）")


def _apply_overrides(args: argparse.Namespace, cfg: AppConfig) -> None:
    if getattr(args, "source", None):
        cfg.source = args.source
    render_cfg = cfg.render
    for attr in ("width", "words", "common"):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(render_cfg, attr, value)
    max_words = getattr(args, "max_words", None)
    if max_words is not None:
        render_cfg.max_words = max_words
    if getattr(args, "keep_promos", False):
        render_cfg.filter_promos = False
    if getattr(args, "no_translation", False):
        render_cfg.translation = False
    if getattr(args, "no_images", False):
        render_cfg.images = "off"
    if getattr(args, "no_cover", False):
        cfg.cover.source = "none"
    if getattr(args, "no_vocab", False):
        render_cfg.vocab = False
    if getattr(args, "no_zh", False):
        render_cfg.chinese = False

    audio_voice = getattr(args, "audio_voice", None)
    if audio_voice is not None:
        cfg.audio.voice = audio_voice
    audio_engine = getattr(args, "audio_engine", None)
    if audio_engine is not None:
        cfg.audio.engine = audio_engine
    audio_rate = getattr(args, "audio_rate", None)
    if audio_rate is not None:
        cfg.audio.rate = audio_rate

    if getattr(args, "ip", None):
        cfg.printer.kind, cfg.printer.ip = "network", args.ip
    if getattr(args, "port", None):
        cfg.printer.port = args.port
    if getattr(args, "queue", None):
        cfg.printer.kind, cfg.printer.queue = "cups", args.queue


# ---------------------------------------------------------------- 子命令

def cmd_sources(args: argparse.Namespace, cfg: AppConfig) -> int:
    print("可用来源类型:", ", ".join(available_types()))
    print("已配置来源:")
    for name, spec in sorted(cfg.sources.items()):
        mark = "*" if name == cfg.source else " "
        extra = ", ".join(f"{k}={v}" for k, v in spec.items() if k != "type")
        print(f" {mark} {name:<16} type={spec.get('type')}  {extra}")
    print("\n（* 为默认来源；改 config.toml 的 [defaults] source 可切换）")
    return 0


def cmd_build_data(args: argparse.Namespace, cfg: AppConfig) -> int:
    build_data(cfg.paths, force=args.force, log=lambda m: log.info("%s", m))
    log.info("完成，数据目录: %s", cfg.paths.data)
    return 0


def cmd_fetch(args: argparse.Namespace, cfg: AppConfig) -> int:
    spec = dict(cfg.source_spec(args.source))
    from .sources import build_source

    name = spec.pop("name")
    src = build_source(name, spec)
    store = Store(cfg.paths)
    for article in src.latest(args.count):
        path = store.save_article(article, download_images=args.images)
        log.info("已保存: %s", path)
    return 0


def cmd_preview(args: argparse.Namespace, cfg: AppConfig) -> int:
    issue = build_issue(cfg)
    text = render(
        issue,
        width=cfg.render.width,
        stamp=time.strftime("%Y-%m-%d %H:%M"),
        max_words=cfg.render.max_words,
    )
    log.info("文章: %s  (%s)", issue.article.title, issue.article.date)
    log.info("生词: %d 个", len(issue.vocab))
    if args.out:
        path = write_preview(
            issue,
            text,
            args.out,
            columns=cfg.render.width,
            max_image_height=cfg.render.max_image_height,
            dither=cfg.render.dither,
        )
        log.info("预览: %s", path)
        if path.suffix.lower() in (".png", ".html", ".htm"):
            log.info("打开就能看到图片: open %s", path)
    else:
        print(text)
    return 0


def _run_audio(args: argparse.Namespace, cfg: AppConfig, issue: Issue) -> None:
    """生成并发送语音；任何异常都被吞掉，不影响打印主流程。"""
    try:
        ac = cfg.audio
        if getattr(args, "no_audio", False) or not ac.enabled:
            return
        from .enrich.audio import archive_dir, send_dir

        date = issue.article.date or "unknown"
        send_path = send_dir(ac) / f"{date}.ogg"
        send_path.parent.mkdir(parents=True, exist_ok=True)
        speech = build_speech_text(
            issue,
            include_translation=ac.include_translation,
            max_words=ac.max_words,
        )
        if not speech.strip():
            log.warning("正文为空，跳过语音合成")
            return
        audio_path = synthesize(speech, send_path, cfg=ac)
        if audio_path is None:
            return
        if ac.send:
            caption = f"{issue.article.title} · {date}"
            sent = send_audio(audio_path, channel=ac.channel, target=ac.target, caption=caption)
            if sent:
                try:
                    arc_dir = archive_dir(ac, cfg.paths)
                    arc_dir.mkdir(parents=True, exist_ok=True)
                    arc_path = arc_dir / f"{date}.ogg"
                    if arc_path.resolve() != audio_path.resolve():
                        shutil.copy2(audio_path, arc_path)
                        log.info("语音归档: %s", arc_path)
                except Exception as e:  # noqa: BLE001
                    log.warning("语音归档失败（不影响发送）: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("语音处理失败（不影响打印）: %s", e)


def _article_age_days(article_date: str, today: date) -> int | None:
    """文章日期距 ``today`` 几天；日期缺失或无法解析时返回 None。"""
    try:
        published = date.fromisoformat((article_date or "").strip())
    except ValueError:
        return None
    return (today - published).days


def _notify_stale(
    cfg: AppConfig,
    article: Article,
    state: StateStore,
    *,
    sender: Callable[..., bool] | None = None,
    today: date | None = None,
) -> None:
    """源站断更提醒：文章年龄超过 [notify] stale_days 时发一条 Telegram。

    每个自然日最多一条；任何失败只记警告，绝不影响打印主流程（同 _run_audio 约定）。
    """
    try:
        nc = cfg.notify
        if not nc.enabled:
            return
        today = today or date.today()
        age = _article_age_days(article.date, today)
        if age is None:
            log.debug("文章日期缺失/无法解析，跳过断更检查: %r", article.date)
            return
        if age <= nc.stale_days:
            return
        day = today.isoformat()
        if state.stale_alert_sent_on(day):
            log.info("断更提醒今天已发过，跳过")
            return
        sender = sender or send_text
        channel = nc.channel or cfg.audio.channel
        target = nc.target or cfg.audio.target
        msg = f"源站断更 {age} 天：最新仍是 {article.date}《{article.title}》"
        if sender(msg, channel=channel, target=target):
            state.mark_stale_alert(day)
    except Exception as e:  # noqa: BLE001
        log.warning("断更提醒发送失败（不影响打印）: %s", e)


def cmd_print(args: argparse.Namespace, cfg: AppConfig) -> int:
    issue: Issue = build_issue(cfg)
    state = StateStore.load(cfg.paths.state)
    _notify_stale(cfg, issue.article, state)

    if not getattr(args, "force", False) and state.is_printed(issue.article.url):
        log.info(
            "已印过，跳过: %s (%s)（--force 可强制重印）",
            issue.article.title,
            issue.article.date,
        )
        return 0

    text = render(
        issue,
        width=cfg.render.width,
        stamp=time.strftime("%Y-%m-%d %H:%M"),
        max_words=cfg.render.max_words,
    )
    path = Store(cfg.paths).save_print(issue.article.date or "print", text)
    log.info("文章: %s  (%s)", issue.article.title, issue.article.date)
    log.info("留档: %s", path)
    if args.dry_run:
        log.info("--dry-run：未发送")
        return 0
    printer = build_printer(cfg.printer)
    printer.send(
        encode(
            text,
            chinese=cfg.render.chinese,
            cut=cfg.printer.cut,
            images={img.label: img.path for img in issue.all_images() if img.path},
            max_image_height=cfg.render.max_image_height,
            dither=cfg.render.dither,
        )
    )
    log.info("已发送 -> %r", printer)
    try:
        state.mark_printed(issue.article, path)
    except OSError as e:
        log.warning("台账写入失败（不影响本次打印，下次可能重印）: %s", e)
    _run_audio(args, cfg, issue)
    return 0


def cmd_audio(args: argparse.Namespace, cfg: AppConfig) -> int:
    from .enrich.audio import archive_dir, send_dir

    issue = build_issue(cfg)
    ac = cfg.audio
    if args.voice:
        ac.voice = args.voice
    if args.engine:
        ac.engine = args.engine
    if args.rate:
        ac.rate = args.rate
    if args.say_voice:
        ac.say_voice = args.say_voice
    if args.say_rate is not None:
        ac.say_rate = args.say_rate

    date = issue.article.date or "audio"
    if args.out:
        out_path = Path(args.out)
    elif args.send:
        out_path = send_dir(ac) / f"{date}.ogg"
    else:
        out_path = cfg.paths.audio / f"{date}.ogg"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    speech = build_speech_text(
        issue,
        include_translation=args.include_translation or ac.include_translation,
        max_words=args.max_words if args.max_words is not None else ac.max_words,
    )
    if not speech.strip():
        log.warning("正文为空，跳过语音合成")
        return 0
    audio_path = synthesize(speech, out_path, cfg=ac)
    if audio_path is None:
        return 0
    log.info("语音文件: %s", audio_path)
    should_send = (
        args.send
        if args.send is not None
        else (args.no_send is not True and ac.send)
    )
    if should_send:
        caption = f"{issue.article.title} · {issue.article.date or 'unknown'}"
        sent = send_audio(audio_path, channel=ac.channel, target=ac.target, caption=caption)
        if sent:
            try:
                arc_dir = archive_dir(ac, cfg.paths)
                arc_dir.mkdir(parents=True, exist_ok=True)
                arc_path = arc_dir / f"{date}.ogg"
                if arc_path.resolve() != audio_path.resolve():
                    shutil.copy2(audio_path, arc_path)
                    log.info("语音归档: %s", arc_path)
            except Exception as e:  # noqa: BLE001
                log.warning("语音归档失败（不影响发送）: %s", e)
    return 0


def cmd_test_print(args: argparse.Namespace, cfg: AppConfig) -> int:
    printer = build_printer(cfg.printer)
    text = test_page(cfg.render.width)
    Store(cfg.paths).save_print("test", text)
    printer.send(encode(text, chinese=cfg.render.chinese, cut=cfg.printer.cut))
    log.info("测试页已发送 -> %r", printer)
    return 0


# ---------------------------------------------------------------- 解析器

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailyprint", description="把每日英文文章排成 80mm 小票打印"
    )
    parser.add_argument("--config", help="配置文件路径（默认 ./config.toml）")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--version", action="version", version=f"dailyprint {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="列出可用来源")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("build-data", help="下载并构建词频表与词典")
    p.add_argument("--force", action="store_true", help="重新下载缓存")
    p.set_defaults(func=cmd_build_data)

    p = sub.add_parser("fetch", help="抓取文章并存成 Markdown")
    _add_source_opts(p)
    p.add_argument("--count", type=int, default=1, help="抓几篇（默认 1）")
    p.add_argument("--images", action="store_true", help="同时把图片下载到本地")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("preview", help="排版预览（不打印）")
    _add_source_opts(p)
    _add_render_opts(p)
    p.add_argument(
        "-o",
        "--out",
        help="输出文件；后缀 .txt=纯文本、.png=热敏模拟、.html=网页（后两者带图片）",
    )
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("print", help="抓取 + 排版 + 发送打印机")
    _add_source_opts(p)
    _add_render_opts(p)
    _add_printer_opts(p)
    p.add_argument("--dry-run", action="store_true", help="只排版留档，不发送")
    p.add_argument("--force", action="store_true", help="已印过也强制重印（跳过查重）")
    p.add_argument("--no-audio", action="store_true", help="不生成/发送语音")
    p.add_argument("--audio-voice", help="覆盖 edge-tts 朗读音色（如 en-US-AriaNeural）")
    p.add_argument("--audio-engine", help="覆盖 TTS 引擎（auto | edge | say）")
    p.add_argument("--audio-rate", help="覆盖 edge-tts 语速（如 -10%%、0%%）")
    p.set_defaults(func=cmd_print)

    p = sub.add_parser("audio", help="生成文章语音（可选发送 Telegram）")
    _add_source_opts(p)
    p.add_argument("-o", "--out", help="输出文件路径（默认 prints/audio/YYYY-MM-DD.ogg）")
    p.add_argument("--voice", help="edge-tts 音色（默认 en-US-AriaNeural）")
    p.add_argument("--engine", help="TTS 引擎（auto | edge | say）")
    p.add_argument("--rate", help="edge-tts 语速（默认 -10%%）")
    p.add_argument("--say-voice", help="降级 say 音色（默认 Samantha）")
    p.add_argument("--say-rate", type=int, help="降级 say 语速 wpm（默认 160）")
    p.add_argument("--include-translation", action="store_true", help="附带中文译文")
    p.add_argument("--max-words", type=int, help="最多朗读多少词（0=不限）")
    send_group = p.add_mutually_exclusive_group()
    send_group.add_argument("--send", action="store_true", default=None, help="发送 Telegram")
    send_group.add_argument("--no-send", action="store_true", help="不发送 Telegram")
    p.set_defaults(func=cmd_audio)

    p = sub.add_parser("test-print", help="发送测试页（检查宽度/对齐/切纸）")
    _add_printer_opts(p)
    p.add_argument("--width", type=int)
    p.set_defaults(func=cmd_test_print)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    cfg = load_config(args.config)
    _apply_overrides(args, cfg)
    try:
        return int(args.func(args, cfg))
    except (RuntimeError, ValueError, KeyError) as e:
        log.error("错误: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
