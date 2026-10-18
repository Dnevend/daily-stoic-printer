"""流水线：来源 -> 文章 -> 生词/释义 -> 一期内容。"""

from __future__ import annotations

from .config import AppConfig, Paths
from .enrich import load_dictionary, select_vocab
from .models import Issue
from .sources import build_source


def load_wordlist(paths: Paths) -> list[str]:
    if not paths.wordfreq.exists():
        return []
    lines = paths.wordfreq.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def build_issue(cfg: AppConfig, source: str | None = None) -> Issue:
    """抓最新一篇并挑生词（含中文释义）。"""
    spec = dict(cfg.source_spec(source))
    name = spec.pop("name")
    src = build_source(name, spec)

    article = src.latest(1)[0]
    issue = Issue(article=article)

    if cfg.render.vocab:
        freq = load_wordlist(cfg.paths)
        if freq:
            issue.vocab = select_vocab(
                article.text, freq, known=cfg.render.common, limit=cfg.render.words
            )
            if cfg.render.chinese and issue.vocab:
                dictionary = load_dictionary(cfg.paths.dictionary)
                if dictionary.available:
                    for item in issue.vocab:
                        item.gloss = dictionary.lookup(item.word)
    return issue
