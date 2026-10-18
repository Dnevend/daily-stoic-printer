"""本地存档：文章 Markdown（可选下载图片）与每次打印的文本副本。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

from .config import Paths
from .models import Article
from .sources.http import get


def slugify(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9\-_.]", "-", slug) or "article"


class Store:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    # ------------------------------------------------------------ 文章

    def save_article(self, article: Article, *, download_images: bool = False) -> Path:
        self.paths.articles.mkdir(parents=True, exist_ok=True)
        body = article.raw or article.text
        if download_images:
            body = self._localize_images(body, f"{article.date}-{slugify(article.url)}")
        out = self.paths.articles / f"{article.date}-{slugify(article.url)}.md"
        header = (
            f"# {article.title}\n\n"
            f"- 来源: {article.source}\n"
            f"- 日期: {article.date}\n"
            f"- 原文: {article.url}\n"
            f"- 抓取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
        )
        out.write_text(header + body + "\n", encoding="utf-8")
        return out

    def _localize_images(self, md: str, slug: str) -> str:
        urls = list(dict.fromkeys(re.findall(r"!\[[^\]]*\]\((https?://[^)]+)\)", md)))
        if not urls:
            return md
        img_dir = self.paths.articles / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, url in enumerate(urls, start=1):
            ext = Path(urlparse(url).path).suffix or ".jpg"
            name = f"{slug}-{i}{ext}"
            dest = img_dir / name
            if not dest.exists():
                dest.write_bytes(get(url, timeout=60))
            md = md.replace(f"]({url})", f"](images/{name})")
        return md

    # ------------------------------------------------------------ 打印副本

    def save_print(self, name: str, text: str) -> Path:
        self.paths.prints.mkdir(parents=True, exist_ok=True)
        out = self.paths.prints / f"{name}.txt"
        out.write_text(text + "\n", encoding="utf-8")
        return out
