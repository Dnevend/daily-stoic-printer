"""生词挑选：按词频排除"已认识"的词，取稀有词并附原文语境。"""

from __future__ import annotations

import re

from ..models import VocabItem
from ..textutil import lemmas, split_sentences


def select_vocab(
    text: str,
    freq: list[str],
    known: int = 6000,
    limit: int = 8,
    min_len: int = 6,
    ctx_max: int = 180,
) -> list[VocabItem]:
    """挑生词。

    规则：
    - 不在「前 known 个高频词」里（含词形还原判断）
    - 出现过全小写形式（排除人名/专有名词）
    - 每句最多取一个词（避免语境重复）
    - 按稀有度取前 limit 个，输出时按文章出现顺序
    """
    common = {w.lower() for w in freq[:known]}
    rank = {w.lower(): i for i, w in enumerate(freq)}
    sentences = split_sentences(text)

    cands: list[dict] = []
    seen: set[str] = set()
    used_sent: set[int] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z\-]+", text):
        word = m.group(0).lower()
        if len(word) < min_len or word in seen:
            continue
        forms = lemmas(word)
        if not forms or forms & common:
            continue
        if not re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text):
            continue  # 只出现大写形式 -> 人名/专有名词
        idx = next(
            (i for i, s in enumerate(sentences) if re.search(rf"\b{re.escape(word)}\b", s, re.I)),
            None,
        )
        if idx is None or idx in used_sent:
            continue
        seen.add(word)
        used_sent.add(idx)
        ctx = sentences[idx]
        if len(ctx) > ctx_max:
            ctx = ctx[:ctx_max].rsplit(" ", 1)[0] + " ..."
        cands.append(
            {
                "word": word,
                "context": ctx,
                "order": m.start(),
                "rank": rank.get(word, len(freq) + 1),
            }
        )

    cands.sort(key=lambda c: (-c["rank"], c["order"]))  # 越稀有越优先
    picked = cands[:limit]
    picked.sort(key=lambda c: c["order"])  # 输出按文章顺序
    return [VocabItem(word=c["word"], context=c["context"]) for c in picked]
