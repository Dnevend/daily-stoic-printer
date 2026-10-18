"""流水线：来源 -> 文章 -> 过滤推广 -> 生词/释义 -> 一期内容。"""

from __future__ import annotations

import logging

from .config import AppConfig, Paths
from .enrich import (
    TranslationError,
    Translator,
    load_dictionary,
    select_vocab,
    strip_promo_paragraphs,
)
from .models import Issue
from .sources import build_source
from .textutil import md_to_plain, truncate_words

log = logging.getLogger("dailyprint")


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

    if cfg.render.filter_promos:
        filtered, dropped = strip_promo_paragraphs(
            article.raw, extra_phrases=cfg.render.promo_phrases
        )
        if dropped:
            log.info("过滤推广段落 %d 个（--keep-promos 可关闭）：", len(dropped))
            for reason, text in dropped:
                log.info("  - [%s] %s", reason, text)
        article.text = md_to_plain(filtered)

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

    if cfg.render.translation and cfg.render.chinese:
        theme, _ = truncate_words(article.text, cfg.render.max_words)
        try:
            translator = Translator(
                cfg.paths.translation_cache,
                target=cfg.translation.target,
                providers=cfg.translation.providers,
                email=cfg.translation.email,
            )
            issue.translation = translator.translate(theme)
            log.info(
                "中文译文: %d 字（翻译请求 %d 次）", len(issue.translation), translator.requests
            )
        except TranslationError as e:
            log.warning("翻译失败，跳过译文: %s", e)
            log.warning("（可设 HTTPS_PROXY 走代理，或在此处填邮箱提高额度）")

    return issue
