"""文本工具：显示宽度、混排换行、HTML/Markdown 清理、词形还原、释义截断。"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata

WIDTH = 48  # 80mm 热敏纸 Font A 的常见列数

# 常见排版字符 -> ASCII（热敏机默认代码页不含这些字符）
_TYPO = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "--",
    "\u2026": "...",
    "\u00a0": " ",
    "\u2022": "*",
    "\u00b7": "-",
    "\u2032": "'",
    "\u2033": '"',
}

# 英文单词整体成块；其它字符（含中文）逐个成块
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*|.", re.S)


# ---------------------------------------------------------------- 宽度与换行

def to_ascii(s: str) -> str:
    """英文文本 -> 纯 ASCII（不可用于中文）。"""
    for k, v in _TYPO.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if ord(c) < 128)


def dlen(s: str) -> int:
    """显示宽度：全角/CJK 字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def hard_split(tok: str, width: int) -> list[str]:
    out: list[str] = []
    cur = ""
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
        need_space = False
        for tok in _TOKEN_RE.findall(para):
            if tok.isspace():
                need_space = True
                continue

            if dlen(tok) > width:  # 超长 token（URL）：冲掉当前行再硬切
                if line.strip():
                    lines.append(line.rstrip())
                pieces = hard_split(tok, width)
                lines.extend(pieces[:-1])
                line = pieces[-1]
                need_space = False
                continue

            sep = " " if (need_space and line) else ""
            if line and dlen(line) + len(sep) + dlen(tok) > width:
                lines.append(line.rstrip())
                line = tok
            else:
                line += sep + tok
            need_space = False
        lines.append(line.rstrip())
    return lines


def center_disp(s: str, width: int = WIDTH) -> str:
    return " " * max(0, (width - dlen(s)) // 2) + s


def truncate_words(text: str, max_words: int) -> tuple[str, bool]:
    """按词数截断，返回 (文本, 是否被截断)。``max_words <= 0`` 表示不限制。"""
    if max_words <= 0:
        return text, False
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]), True


# ---------------------------------------------------------------- 内容清理

def html_to_text(html: str) -> str:
    """通用 HTML -> 纯文本（用于 RSS 内容）。"""
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "", html)
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)<li[^>]*>", "- ", s)
    s = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|blockquote)>", "\n\n", s)
    s = re.sub(r"(?is)<[^>]+>", "", s)
    s = html_lib.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def md_to_plain(md: str) -> str:
    """Markdown -> 打印用纯文本（英文，转 ASCII）。"""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)  # 图片
    s = re.sub(r"\[\]\([^)]*\)", "", s)  # 只剩空链接时（图片套链接）残留的 []
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # 链接 -> 文字
    s = re.sub(r"(?m)^\s*>\s?", "", s)  # 引用前缀
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"(?m)^#{1,6}\s*", "", s)  # 标题符号
    s = to_ascii(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- HTML -> Markdown

def strip_tags(s: str) -> str:
    return re.sub(r"(?s)<[^>]+>", "", s)


def html_to_md(fragment: str) -> str:
    """HTML 片段 -> Markdown（覆盖常见结构；懒加载图片取 data-src）。"""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", fragment)
    s = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", "", s)  # noscript 里是重复图片
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    # 相邻的同名内联标签之间补一个空格，避免 "…</strong><strong>…" 粘成 "GetThe"
    s = re.sub(r"(?i)</(a|strong|b|em|i)>\s*<\1\b", r"</\1> <\1", s)

    def img_repl(m: re.Match) -> str:
        tag = m.group(0)
        src = re.search(r'data-src="([^"]+)"', tag) or re.search(r'src="([^"]+)"', tag)
        if not src or src.group(1).startswith("data:"):
            return ""
        alt = re.search(r'alt="([^"]*)"', tag)
        return f"![{alt.group(1) if alt else ''}]({src.group(1)})"

    s = re.sub(r"(?is)<img[^>]*>", img_repl, s)
    s = re.sub(
        r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        # 不要 strip：原文有时把分词的空格写在链接文字里（如 "<a>Get </a>"）
        lambda m: "[{}]({})".format(
            re.sub(r"\s+", " ", html_lib.unescape(strip_tags(m.group(2)))).strip("\n\r\t"),
            m.group(1),
        ),
        s,
    )
    s = re.sub(r"(?is)<(em|i)[^>]*>(.*?)</\1>", r"*\2*", s)
    s = re.sub(r"(?is)<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", s)
    s = re.sub(
        r"(?is)<h([1-4])[^>]*>(.*?)</h\1>",
        lambda m: "#" * int(m.group(1)) + " " + strip_tags(m.group(2)).strip() + "\n",
        s,
    )
    s = re.sub(
        r"(?is)<blockquote[^>]*>(.*?)</blockquote>",
        lambda m: "\n"
        + "\n".join(
            "> " + ln.strip()
            for ln in strip_tags(m.group(1)).strip().splitlines()
            if ln.strip()
        )
        + "\n",
        s,
    )
    s = re.sub(
        r"(?is)<li[^>]*>(.*?)</li>",
        lambda m: "- " + html_lib.unescape(strip_tags(m.group(1))).strip() + "\n",
        s,
    )
    s = re.sub(r"(?is)</p>", "\n\n", s)
    s = re.sub(r"(?is)<p[^>]*>", "", s)
    s = strip_tags(s)
    s = html_lib.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ---------------------------------------------------------------- 词形与释义

def lemmas(w: str) -> set[str]:
    """粗糙词形还原：由屈折形式推出可能的原形。"""
    if "'" in w:  # 缩写（we're）不参与
        return set()
    w = w.lower()
    forms = {w}
    if w.endswith("ies") and len(w) > 4:
        forms.add(w[:-3] + "y")
    for suf, extra in (
        ("es", ["", "e"]),
        ("s", [""]),
        ("ed", ["", "e"]),
        ("ing", ["", "e"]),
        ("ly", [""]),
        ("er", [""]),
        ("est", [""]),
    ):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            for e in extra:
                forms.add(base + e)
            if suf in ("ing", "ed") and len(base) >= 3 and base[-1] == base[-2]:
                forms.add(base[:-1])  # running -> run
    return forms


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
