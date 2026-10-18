"""命令行入口：``dailyprint <子命令>``。"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .config import AppConfig, load_config
from .data import build as build_data
from .models import Issue
from .pipeline import build_issue
from .printers import build_printer
from .render import encode, render, test_page
from .sources import available_types
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
    if getattr(args, "no_vocab", False):
        render_cfg.vocab = False
    if getattr(args, "no_zh", False):
        render_cfg.chinese = False

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
    text = render(issue, width=cfg.render.width, stamp=time.strftime("%Y-%m-%d %H:%M"))
    log.info("文章: %s  (%s)", issue.article.title, issue.article.date)
    log.info("生词: %d 个", len(issue.vocab))
    if args.out:
        from pathlib import Path

        Path(args.out).expanduser().write_text(text + "\n", encoding="utf-8")
        log.info("预览: %s", args.out)
    else:
        print(text)
    return 0


def cmd_print(args: argparse.Namespace, cfg: AppConfig) -> int:
    issue: Issue = build_issue(cfg)
    text = render(issue, width=cfg.render.width, stamp=time.strftime("%Y-%m-%d %H:%M"))
    path = Store(cfg.paths).save_print(issue.article.date or "print", text)
    log.info("文章: %s  (%s)", issue.article.title, issue.article.date)
    log.info("留档: %s", path)
    if args.dry_run:
        log.info("--dry-run：未发送")
        return 0
    printer = build_printer(cfg.printer)
    printer.send(encode(text, chinese=cfg.render.chinese, cut=cfg.printer.cut))
    log.info("已发送 -> %r", printer)
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
    p.add_argument("-o", "--out", help="输出到文件（默认打印到终端）")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("print", help="抓取 + 排版 + 发送打印机")
    _add_source_opts(p)
    _add_render_opts(p)
    _add_printer_opts(p)
    p.add_argument("--dry-run", action="store_true", help="只排版留档，不发送")
    p.set_defaults(func=cmd_print)

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
