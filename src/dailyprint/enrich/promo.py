"""过滤推广段落。

Daily Stoic 的邮件正文常夹带书籍/周边推广（CTA 式短段、商店链接、
"while supplies last" 这类促销话术）。这些内容对学英语没价值，还占热敏纸，
所以打印前过一遍（存档仍保留原文）。

判定规则（段落级，命中任一即为推广）：

A. 强短语命中（``STRONG_PHRASES``，见文即删）
B. 弱短语命中（``WEAK_PHRASES``）**且段落很短**（≤ ``weak_max_words`` 词）——
   弱短语可能出现在正文里（如 "medallion"、"painted porch"），长段落不算推广
C. CTA 段：≤ ``cta_words`` 词、以 CTA 动词开头、且含链接
   （"Order The Book" / "Get your copy here."）
D. 整段加粗/斜体 + ≤ ``emph_words`` 词 + 含链接（营销排版习惯）
E. 只有图片/链接、没有文字

刻意**不**按域名删段：正文引用书籍时也会链到商店，那属于正文。
"""

from __future__ import annotations

import re

from ..textutil import md_to_plain

# 见文即删：这些说法在正文里基本只出现在推广中
STRONG_PHRASES: tuple[str, ...] = (
    "daily stoic store",
    "memento mori collection",
    "add to cart",
    "shop now",
    "order now",
    "buy now",
    "get your copy",
    "grab one now",
    "check out our",
    "supplies last",
    "free shipping",
    "discount code",
    "coupon code",
    "available now in hardcover",
    "sign up for one free email",
    "subscribe to the daily stoic podcast",
    "to learn more on this topic, check out",
    "secure your",
    "secure those now",
    "exclusive bonuses",
    "preorder bonus",
    "pre-order bonus",
    "first-edition copy",
    "pick up a copy",
)

# 只在短段落里+带链接时才算推广：这些词在正文里也可能合法出现
WEAK_PHRASES: tuple[str, ...] = (
    "medallion",
    "preorder",
    "pre-order",
    "signed first edition",
    "signed and numbered",
    "hardcover",
    "leatherbound",
)

_CTA_START = re.compile(
    r"^(order|get|buy|shop|grab|claim|pre-?order|reserve|download|subscribe|"
    r"sign ?up|check out|pick up|book)\b",
    re.I,
)
_LINK_RE = re.compile(r"\]\((https?://[^)]+)\)")


def split_paragraphs(md: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", md.strip()) if p.strip()]


def _whole_emphasis(paragraph: str) -> bool:
    s = paragraph.strip()
    if len(s) < 4:
        return False
    return bool(re.match(r"^[*_]{1,3}\S", s)) and bool(re.search(r"\S[*_]{1,3}$", s))


def promo_reason(
    paragraph: str,
    *,
    extra_phrases: tuple[str, ...] = (),
    weak_max_words: int = 40,
    cta_words: int = 25,
    emph_words: int = 30,
) -> str | None:
    """返回命中规则名；不是推广则返回 None。"""
    plain = md_to_plain(paragraph)
    lower = plain.lower()
    words = len(plain.split())
    has_link = bool(_LINK_RE.search(paragraph))

    if not plain.strip():
        return "image-only" if has_link or "![" in paragraph else None

    for phrase in STRONG_PHRASES:
        if phrase in lower:
            return f"strong:{phrase}"
    for phrase in extra_phrases:
        if phrase and phrase.lower() in lower:
            return f"extra:{phrase}"

    if has_link and words <= weak_max_words and any(p in lower for p in WEAK_PHRASES):
        return "weak-phrase"

    if has_link and words <= cta_words and _CTA_START.match(plain.strip()):
        return "cta-line"

    if has_link and words <= emph_words and _whole_emphasis(paragraph):
        return "emphasized-cta"

    return None


def strip_promo_paragraphs(
    md: str, *, extra_phrases: tuple[str, ...] = ()
) -> tuple[str, list[tuple[str, str]]]:
    """返回 (过滤后的 markdown, [(命中规则, 被删段落), ...])。"""
    kept: list[str] = []
    dropped: list[tuple[str, str]] = []
    for paragraph in split_paragraphs(md):
        reason = promo_reason(paragraph, extra_phrases=extra_phrases)
        if reason:
            dropped.append((reason, " ".join(md_to_plain(paragraph).split())[:100]))
        else:
            kept.append(paragraph)
    return "\n\n".join(kept), dropped
