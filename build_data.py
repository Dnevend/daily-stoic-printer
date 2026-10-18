#!/usr/bin/env python3
"""
构建本地数据：高频词表 + 英汉词典

用法:
    python3 build_data.py [--force]

产出（均在 data/ 下，已被 .gitignore 忽略）:
    wordfreq.txt  - Google 10k 高频词，用于判断"是否已认识"
    dict.tsv      - word<TAB>中文释义，来自 ECDICT（含常见屈折形式）

首次运行会下载约 63MB 的 ECDICT 词库到 data/ecdict.csv 作为缓存，
之后重跑会直接复用（--force 可强制重新下载）。
"""

from __future__ import annotations

import argparse
import csv
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UA = "daily-stoic-printer/0.1 (build_data)"

WORDFREQ_URL = (
    "https://raw.githubusercontent.com/first20hours/google-10000-english"
    "/master/google-10000-english-usa-no-swears.txt"
)
ECDICT_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"


def download(url: str, dest: Path, force: bool = False) -> Path:
    if dest.exists() and not force and dest.stat().st_size > 0:
        print(f"已存在，跳过下载: {dest.name}")
        return dest
    print(f"下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as f:
        total = 0
        while chunk := resp.read(1 << 20):
            f.write(chunk)
            total += len(chunk)
    tmp.replace(dest)
    print(f"  -> {dest.name} ({total / 1048576:.1f} MB)")
    return dest


def clean_zh(tr: str) -> str:
    tr = tr.replace("\\n", "; ").replace("\n", " ").replace("\r", " ")
    tr = re.sub(r"\s+", " ", tr).strip(" ;,，")
    return tr


def build_dict(csv_path: Path, out_path: Path) -> None:
    head: dict[str, str] = {}
    forms: dict[str, str] = {}
    total = 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            w = (row.get("word") or "").strip().lower()
            tr = (row.get("translation") or "").strip()
            if not w or not tr or not re.fullmatch(r"[a-z][a-z'\-]{0,29}", w):
                continue
            zh = clean_zh(tr)
            if not zh:
                continue
            head[w] = zh[:120]

            # exchange 字段形如 p:watched/d:watched/i:watching/s:watches
            # k == "0" 表示"本词是 v 的屈折形式"，其余表示"v 是本词的某种形式"
            for part in (row.get("exchange") or "").split("/"):
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                v = v.strip().lower()
                if not v:
                    continue
                if k == "0":
                    forms[w] = v
                elif k in ("s", "p", "d", "i", "3", "r", "t"):
                    forms.setdefault(v, w)

    with out_path.open("w", encoding="utf-8") as out:
        for w, zh in head.items():
            out.write(f"{w}\t{zh}\n")
        for form, lemma in forms.items():
            if form in head:
                continue
            zh = head.get(lemma)
            if zh:
                out.write(f"{form}\t{zh}\n")
    print(f"ECDICT 共 {total} 行 -> 词条 {len(head)}；写入 {out_path.name}")


def main() -> int:
    p = argparse.ArgumentParser(description="构建本地词频表和英汉词典")
    p.add_argument("--force", action="store_true", help="重新下载缓存文件")
    args = p.parse_args()

    DATA.mkdir(exist_ok=True)
    download(WORDFREQ_URL, DATA / "wordfreq.txt", args.force)
    csv_path = download(ECDICT_URL, DATA / "ecdict.csv", args.force)
    build_dict(csv_path, DATA / "dict.tsv")
    print("完成。可以用 python3 daily_print.py --preview preview.txt --no-print 看效果。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
