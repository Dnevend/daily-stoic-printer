"""下载并构建本地数据：

- ``data/wordfreq.txt``  Google 10k 高频词（判断"是否已认识"）
- ``data/dict.tsv``      ECDICT 英汉词典（含常见屈折形式）

数据文件不入库（见 .gitignore），首次使用时现取现建。
"""

from __future__ import annotations

import csv
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path

from ..config import Paths

UA = "dailyprint/0.1 (+https://github.com/Dnevend/daily-stoic-printer)"
WORDFREQ_URL = (
    "https://raw.githubusercontent.com/first20hours/google-10000-english"
    "/master/google-10000-english-usa-no-swears.txt"
)
ECDICT_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"

_WORD_RE = re.compile(r"[a-z][a-z'\-]{0,29}")
_MESSY_SUFFIX = ("s", "p", "d", "i", "3", "r", "t")


def download(url: str, dest: Path, *, force: bool = False, log: Callable = print) -> Path:
    if dest.exists() and not force and dest.stat().st_size > 0:
        log(f"已存在，跳过下载: {dest.name}")
        return dest
    log(f"下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as f:
        total = 0
        while chunk := resp.read(1 << 20):
            f.write(chunk)
            total += len(chunk)
    tmp.replace(dest)
    log(f"  -> {dest.name} ({total / 1048576:.1f} MB)")
    return dest


def clean_zh(tr: str) -> str:
    tr = tr.replace("\\n", "; ").replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", tr).strip(" ;,，")


def build_dictionary(csv_path: Path, out_path: Path, *, log: Callable = print) -> dict:
    head: dict[str, str] = {}
    forms: dict[str, str] = {}
    total = 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            word = (row.get("word") or "").strip().lower()
            translation = (row.get("translation") or "").strip()
            if not word or not translation or not _WORD_RE.fullmatch(word):
                continue
            gloss = clean_zh(translation)
            if not gloss:
                continue
            head[word] = gloss[:120]

            # exchange 形如 p:watched/d:watched/i:watching/s:watches
            # k == "0" 表示"本词是 v 的屈折形式"，其余表示"v 是本词的某种形式"
            for part in (row.get("exchange") or "").split("/"):
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                v = v.strip().lower()
                if not v:
                    continue
                if k == "0":
                    forms[word] = v
                elif k in _MESSY_SUFFIX:
                    forms.setdefault(v, word)

    with out_path.open("w", encoding="utf-8") as out:
        for word, gloss in head.items():
            out.write(f"{word}\t{gloss}\n")
        for form, lemma in forms.items():
            if form in head:
                continue
            gloss = head.get(lemma)
            if gloss:
                out.write(f"{form}\t{gloss}\n")
    log(f"ECDICT 共 {total} 行 -> 词条 {len(head)}；写入 {out_path.name}")
    return {"rows": total, "entries": len(head)}


def build(paths: Paths, *, force: bool = False, log: Callable = print) -> dict:
    paths.data.mkdir(parents=True, exist_ok=True)
    download(WORDFREQ_URL, paths.wordfreq, force=force, log=log)
    csv_path = download(ECDICT_URL, paths.data / "ecdict.csv", force=force, log=log)
    return build_dictionary(csv_path, paths.dictionary, log=log)
