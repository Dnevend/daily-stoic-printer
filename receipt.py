#!/usr/bin/env python3
"""
80mm 热敏小票排版（ESC/POS，支持中英混排）

要点:
- 有效宽度默认 48 列（Font A）；中文字符按 2 列计算，换行按"显示宽度"处理
- 英文正文强制转 ASCII（热敏机默认代码页不含弯引号/破折号等）
- 中文（生词释义）保留，打印时用 GB18030 编码并切换中文模式
"""

from __future__ import annotations

import re
import unicodedata

WIDTH = 48
ESC = b"\x1b"
GS = b"\x1d"

_TYPO = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "--", "\u2026": "...", "\u00a0": " ",
    "\u2022": "*", "\u00b7": "-", "\u2032": "'", "\u2033": '"',
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*|.", re.S)


# ---------------------------------------------------------------- 基础工具

def to_ascii(s: str) -> str:
    """英文文本 -> 纯 ASCII（用于标题/正文，不能用于中文）。"""
    for k, v in _TYPO.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if ord(c) < 128)


def dlen(s: str) -> int:
    """显示宽度：全角/CJK 字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _hard_split(tok: str, width: int) -> list[str]:
    out, cur = [], ""
    for ch in tok:
        if dlen(cur) + dlen(ch) > width:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    return out


def wrap_disp(text: str, width: int = WIDTH) -> list[str]:
    """按显示宽度换行（中英混排安全；超长 token 如 URL 会硬切）。"""
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        line = ""
        for tok in _TOKEN_RE.findall(para):
            if tok.isspace():
                if line:
                    line += " "
                continue
            if dlen(tok) > width:
                for j, piece in enumerate(_hard_split(tok, width)):
                    if j == 0:
                        if line.strip():
                            lines.append(line.rstrip())
                        line = piece
                    else:
                        lines.append(line.rstrip())
                        line = piece
                continue
            if line.strip() and dlen(line.rstrip()) + dlen(tok) > width:
                lines.append(line.rstrip())
                line = tok
            else:
                line += tok
        lines.append(line.rstrip())
    return lines


def center_disp(s: str, width: int = WIDTH) -> str:
    return " " * max(0, (width - dlen(s)) // 2) + s


# ---------------------------------------------------------------- 文本处理

def md_to_plain(md: str) -> str:
    """去掉 Markdown 装饰，得到适合打印的纯文本（英文，转 ASCII）。"""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)          # 图片
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)         # 链接 -> 文字
    s = re.sub(r"(?m)^\s*>\s?", "", s)                     # 引用前缀
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"(?m)^#{1,6}\s*", "", s)                   # 标题符号
    s = to_ascii(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [p.strip() for p in parts if p.strip()]


def _lemmas(w: str) -> set[str]:
    """粗糙词形还原：推出可能的原形（用于判断是否属于'已认识'的高频词）。"""
    if "'" in w:            # 缩写（we're）不算
        return set()
    forms = {w}
    if w.endswith("ies") and len(w) > 4:
        forms.add(w[:-3] + "y")
    for suf, extra in (
        ("es", ["", "e"]), ("s", [""]), ("ed", ["", "e"]),
        ("ing", ["", "e"]), ("ly", [""]), ("er", [""]), ("est", [""]),
    ):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            for e in extra:
                forms.add(base + e)
            if suf in ("ing", "ed") and len(base) >= 3 and base[-1] == base[-2]:
                forms.add(base[:-1])   # running -> run
    return forms


def find_vocab(
    text: str,
    freq: list[str],
    known: int = 6000,
    limit: int = 8,
    min_len: int = 6,
    ctx_max: int = 180,
) -> list[dict]:
    """挑生词：不在「前 known 个高频词」里、出现过小写形式、每句最多一个，按稀有度取前 limit 个。"""
    common = {w.lower() for w in freq[:known]}
    rank = {w.lower(): i for i, w in enumerate(freq)}
    sentences = split_sentences(text)

    cands: list[dict] = []
    seen: set[str] = set()
    used_sent: set[int] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z\-]+", text):
        w = m.group(0).lower()
        if len(w) < min_len or w in seen:
            continue
        forms = _lemmas(w)
        if not forms or forms & common:
            continue
        if not re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", text):
            continue  # 只出现大写形式 -> 人名/专有名词
        idx = next(
            (i for i, s in enumerate(sentences) if re.search(rf"\b{re.escape(w)}\b", s, re.I)),
            None,
        )
        if idx is None or idx in used_sent:
            continue
        seen.add(w)
        used_sent.add(idx)
        ctx = sentences[idx]
        if len(ctx) > ctx_max:
            ctx = ctx[:ctx_max].rsplit(" ", 1)[0] + " ..."
        cands.append({"word": w, "context": ctx, "order": m.start(), "rank": rank.get(w, len(freq) + 1)})

    cands.sort(key=lambda c: (-c["rank"], c["order"]))   # 越稀有越优先
    picked = cands[:limit]
    picked.sort(key=lambda c: c["order"])                # 输出按文章顺序
    return [{"word": c["word"], "context": c["context"]} for c in picked]


_MESSY = re.compile(r"的(复数|过去式|过去分词|现在分词|第三人称单数|比较级|最高级)")


def trim_gloss(zh: str, max_cols: int = 44, max_senses: int = 3) -> str:
    """释义截断：保留最前面的若干词性释义，按显示宽度填满后截断。"""
    senses = [p.strip() for p in re.split(r";\s*", zh) if p.strip()]
    out = ""
    truncated = False
    for i, s in enumerate(senses):
        if i >= max_senses:
            truncated = True
            break
        candidate = f"{out}; {s}" if out else s
        if dlen(candidate) <= max_cols:
            out = candidate
            continue
        # 这一条塞不下：能塞多少塞多少，然后收尾
        room = max_cols - (dlen(out) + 2 if out else 0) - 4
        if room >= 6:
            acc = ""
            for ch in s:
                if dlen(acc + ch) > room:
                    break
                acc += ch
            acc = acc.rstrip(" ,;，；")
            if acc:
                out = f"{out}; {acc}" if out else acc
        truncated = True
        break
    return out + (" ..." if truncated else "")


def lookup_zh(dic: dict[str, str], word: str) -> str:
    """查中文释义。若命中的是屈折词条（"X的复数"这种），回退到原形再查。"""
    w = word.lower()
    zh = dic.get(w, "")
    if zh and not _MESSY.search(zh):
        return trim_gloss(zh)
    for cand in sorted(_lemmas(w)):
        if cand == w:
            continue
        other = dic.get(cand, "")
        if other and not _MESSY.search(other):
            return trim_gloss(other)
    return trim_gloss(zh)


# ---------------------------------------------------------------- 排版

def render(
    *,
    title: str,
    date: str,
    body: str,
    url: str,
    vocab: list[dict] | None = None,
    stamp: str = "",
    width: int = WIDTH,
) -> str:
    """vocab 里每项形如 {"word": ..., "context": ..., "zh": ...}"""
    L: list[str] = []
    L.append("=" * width)
    L.append(center_disp("DAILY STOIC", width))
    L.append(center_disp(date, width))
    L.append("=" * width)
    L.append("")
    for ln in wrap_disp(title, width):
        L.append(center_disp(ln, width))
    L.append("")
    L.append("-" * width)
    L.append("")
    L.extend(wrap_disp(body, width))

    if vocab:
        L.append("")
        L.append("-" * width)
        L.append("TODAY'S WORDS")
        L.append("-" * width)
        for i, v in enumerate(vocab, 1):
            L.append(f"{i}. {v['word']}")
            if v.get("zh"):
                for ln in wrap_disp(v["zh"], width - 3):
                    L.append("   " + ln)
            for ln in wrap_disp(v["context"], width - 3):
                L.append("   " + ln)
            L.append("")

    L.append("-" * width)
    L.extend(wrap_disp(f"source: {url}", width))
    if stamp:
        L.append(f"printed: {stamp}")
    L.append("=" * width)
    return "\n".join(L)


def to_escpos(text: str, *, chinese: bool = True, cut: bool = True) -> bytes:
    buf = bytearray()
    buf += ESC + b"@"                 # 初始化
    buf += ESC + b"3\x18"             # 行距
    if chinese:
        buf += b"\x1c\x26"            # FS & —— 进入中文模式（GBK/GB18030）
    enc = "gb18030" if chinese else "ascii"
    for line in text.split("\n"):
        buf += line.encode(enc, "replace") + b"\n"
    if cut:
        buf += b"\n\n\n\n"
        buf += GS + b"V\x42\x00"      # 进纸并切纸
    return bytes(buf)


def test_page(width: int = WIDTH) -> str:
    return "\n".join([
        "=" * width,
        center_disp("XP-80T TEST PAGE", width),
        "=" * width,
        "",
        "If you can read this, printing works.",
        "",
        "0123456789" * 4,
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "abcdefghijklmnopqrstuvwxyz",
        "",
        "ABC 中文测试：热敏打印正常 / 中文模式正常",
        "Mixed 中英 mixed 一行 width test 12345",
        "",
        f"width = {width} columns",
        "chars: ' \" - -- ... * @#$%&()",
        "",
        "=" * width,
    ])
