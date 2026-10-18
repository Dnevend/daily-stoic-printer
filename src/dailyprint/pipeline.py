"""流水线：来源 -> 文章 -> 过滤推广 -> 生词/释义 -> 一期内容。"""

from __future__ import annotations

import logging

from .config import AppConfig, Paths
from .enrich import (
    CoverRequest,
    TranslationError,
    Translator,
    fetch_cover,
    fetch_image,
    load_dictionary,
    select_content_images,
    select_vocab,
    strip_promo_paragraphs,
)
from .models import ImageRef, Issue
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

    body_md = article.raw
    if cfg.render.filter_promos:
        body_md, dropped = strip_promo_paragraphs(
            article.raw, extra_phrases=cfg.render.promo_phrases
        )
        if dropped:
            log.info("过滤推广段落 %d 个（--keep-promos 可关闭）：", len(dropped))
            for reason, text in dropped:
                log.info("  - [%s] %s", reason, text)
        article.text = md_to_plain(body_md)

    issue = Issue(article=article)

    if cfg.cover.source != "none":
        seed = article.date or article.title
        try:
            cover = fetch_cover(
                CoverRequest(
                    source=cfg.cover.source,
                    keywords=cfg.cover.keywords,
                    local_path=cfg.cover.local_path,
                    width=cfg.cover.width,
                    height=cfg.cover.height,
                ),
                cfg.paths.image_cache,
                seed=seed,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("封面获取失败，跳过封面: %s", e)
            cover = None
        if cover is not None and cover.image.path is None:
            try:
                cover.image.path = fetch_image(cover.image.url, cfg.paths.image_cache)
            except Exception as e:  # noqa: BLE001
                log.warning("封面下载失败，跳过封面: %s", e)
                cover = None
        if cover is not None:
            issue.cover = cover
            log.info(
                "封面: %s%s",
                cover.image.label,
                f"  ({cover.credit})" if cover.credit else "",
            )

    if cfg.render.images != "off":
        refs = select_content_images(
            body_md,
            limit=cfg.render.max_images,
            skip_promo=cfg.render.images == "content",
            base_url=article.url,
        )
        kept: list[ImageRef] = []
        for ref in refs:
            try:
                ref.path = fetch_image(ref.url, cfg.paths.image_cache)
                kept.append(ref)
            except Exception as e:  # noqa: BLE001
                log.warning("配图下载失败，跳过 %s: %s", ref.label, e)
        issue.images = kept
        if kept:
            log.info("正文配图 %d 张: %s", len(kept), ", ".join(r.label for r in kept))

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
