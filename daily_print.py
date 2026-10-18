#!/usr/bin/env python3
"""
Daily Stoic 每日打印（80mm 热敏小票）

流程: 抓最新一篇每日邮件 -> 排版成 80mm 小票 -> 发送到打印机

用法:
    # 只生成预览，不打印
    python3 daily_print.py --preview preview.txt --no-print

    # 网络打印机（推荐，免驱动，直接发 ESC/POS 到 9100 端口）
    python3 daily_print.py --ip 192.168.1.50

    # 已通过 CUPS 配置好的队列（USB 打印机的用法）
    python3 daily_print.py --queue XP-80T

    # 打一张测试页（对齐、宽度、切纸自检）
    python3 daily_print.py --ip 192.168.1.50 --test

也可把参数写进 config.json:
    { "ip": "192.168.1.50", "port": 9100, "width": 48, "words": 8 }
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import fetch_latest as fs
import receipt

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = ROOT / "config.json"
PRINTS = ROOT / "prints"


# ---------------------------------------------------------------- 配置

def load_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"! config.json 解析失败: {e}")
    return {}


def load_wordlist() -> list[str]:
    path = DATA / "wordfreq.txt"
    if not path.exists():
        print("! 缺少 data/wordfreq.txt，跳过生词表")
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def load_dict() -> dict[str, str]:
    path = DATA / "dict.tsv"
    if not path.exists():
        print("! 缺少 data/dict.tsv（先跑 build_data.py），生词将没有中文释义")
        return {}
    dic: dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            w, zh = ln.split("\t", 1)
            dic[w] = zh
    return dic


# ---------------------------------------------------------------- 取文章

def latest_article() -> dict:
    sitemap = fs.newest_post_sitemap()
    for url in fs.recent_urls(sitemap):
        page = fs.get_text(url)
        if fs.EMAIL_CAT not in page:
            continue  # 播客/长文
        return {
            "url": url,
            "title": fs.parse_meta(page, "og:title") or "(untitled)",
            "date": (fs.parse_meta(page, "article:published_time") or "")[:10],
            "body": fs.html_to_md(fs.extract_content(page)),
        }
    raise RuntimeError("最近的候选中没找到每日邮件文章（可能还没发布）")


# ---------------------------------------------------------------- 发送

def send_lan(ip: str, port: int, data: bytes, timeout: float = 5.0) -> None:
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.sendall(data)


def send_cups(queue: str, data: bytes) -> None:
    proc = subprocess.run(
        ["lp", "-d", queue, "-o", "raw"],
        input=data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"lp 失败: {proc.stderr.decode().strip()}")
    sys.stdout.write(proc.stdout.decode())


# ---------------------------------------------------------------- 主流程

def main() -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(description="打印最新一篇 Daily Stoic 到 80mm 热敏机")
    p.add_argument("--ip", default=cfg.get("ip"), help="网络打印机 IP")
    p.add_argument("--port", type=int, default=cfg.get("port", 9100))
    p.add_argument("--queue", default=cfg.get("queue"), help="CUPS 队列名（USB 打印机）")
    p.add_argument("--width", type=int, default=cfg.get("width", receipt.WIDTH))
    p.add_argument("--words", type=int, default=cfg.get("words", 8), help="生词表条数")
    p.add_argument("--common", type=int, default=cfg.get("common", 6000), help="视为'已认识'的高频词个数")
    p.add_argument("--no-vocab", action="store_true", help="不附生词表")
    p.add_argument("--no-zh", action="store_true", help="不印中文释义（打印机不支持中文时用）")
    p.add_argument("--preview", metavar="FILE", help="把排版结果写到文件（不打印）")
    p.add_argument("--no-print", action="store_true", help="只排版，不发送")
    p.add_argument("--test", action="store_true", help="发送测试页")
    args = p.parse_args()
    chinese = bool(cfg.get("chinese", True)) and not args.no_zh

    # ---- 组装内容
    if args.test:
        text = receipt.test_page(args.width)
        name = "test"
    else:
        art = latest_article()
        print(f"文章: {art['title']}  ({art['date']})")
        body = receipt.md_to_plain(art["body"])
        vocab = []
        if not args.no_vocab:
            vocab = receipt.find_vocab(body, load_wordlist(), known=args.common, limit=args.words)
            print(f"生词: {len(vocab)} 个")
        if vocab and chinese:
            dic = load_dict()
            for v in vocab:
                v["zh"] = receipt.lookup_zh(dic, v["word"])
        text = receipt.render(
            title=receipt.to_ascii(art["title"]),
            date=art["date"],
            body=body,
            url=art["url"],
            vocab=vocab,
            stamp=time.strftime("%Y-%m-%d %H:%M"),
            width=args.width,
        )
        name = art["date"] or time.strftime("%Y-%m-%d")

    # ---- 留档 + 预览
    PRINTS.mkdir(exist_ok=True)
    (PRINTS / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
    if args.preview:
        Path(args.preview).expanduser().write_text(text + "\n", encoding="utf-8")
        print(f"预览: {args.preview}")

    # ---- 发送
    if args.no_print:
        print("已跳过打印（--no-print）")
        return 0
    if not args.ip and not args.queue:
        print("没有指定打印机：加 --ip <IP>（网络）或 --queue <队列名>（USB），")
        print("或先写 config.json。文本已留档在 prints/。")
        return 1
    data = receipt.to_escpos(text, chinese=chinese)
    if args.ip:
        print(f"发送到 {args.ip}:{args.port} ...")
        send_lan(args.ip, args.port, data)
        print("完成。")
    else:
        print(f"发送到 CUPS 队列 {args.queue} ...")
        send_cups(args.queue, data)
        print("完成。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"错误: {e}")
        raise SystemExit(1)
