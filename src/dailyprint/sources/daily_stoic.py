"""Daily Stoic 来源。

站点把每日邮件同步发布在 ``/category/daily-stoic-emails/`` 分类下，
但该分类的 RSS 与 REST API 都被站方过滤了，因此走 sitemap 发现 + 页面分类链接判定。
"""

from __future__ import annotations

import html as html_lib
import re

from ..models import Article
from ..textutil import html_to_md, md_to_plain
from .base import Source
from .http import get_text


class DailyStoicSource(Source):
    def __init__(
        self,
        name: str = "daily-stoic",
        base_url: str = "https://dailystoic.com",
        category_path: str = "/category/daily-stoic-emails/",
        container_class: str = "fe-single-post-content",
        max_candidates: int = 12,
        **_: object,
    ) -> None:
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.category_path = category_path
        self.container_class = container_class
        self.max_candidates = max_candidates

    # ------------------------------------------------------------ 站点结构

    def _newest_post_sitemap(self) -> str:
        index = get_text(f"{self.base_url}/sitemap_index.xml")
        entries: list[tuple[str, str]] = []
        for block in re.findall(r"(?s)<sitemap>(.*?)</sitemap>", index):
            loc = re.search(r"<loc>([^<]+)</loc>", block)
            lastmod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
            if loc and lastmod and "post-sitemap" in loc.group(1):
                entries.append((loc.group(1), lastmod.group(1)))
        if not entries:
            raise RuntimeError("sitemap 索引里没有找到 post-sitemap")
        entries.sort(key=lambda x: x[1], reverse=True)
        return entries[0][0]

    def _recent_urls(self, sitemap_url: str, n: int) -> list[str]:
        xml = get_text(sitemap_url)
        urls: list[tuple[str, str]] = []
        for block in re.findall(r"(?s)<url>(.*?)</url>", xml):
            loc = re.search(r"<loc>([^<]+)</loc>", block)
            lastmod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
            if loc:
                urls.append((loc.group(1), lastmod.group(1) if lastmod else ""))
        urls.sort(key=lambda x: x[1], reverse=True)
        return [u for u, _ in urls[:n]]

    def _extract_container(self, html: str) -> str:
        """按标签嵌套配平，抽出正文容器。"""
        m = re.search(
            rf'<div[^>]*class="[^"]*{re.escape(self.container_class)}[^"]*"[^>]*>', html
        )
        if not m:
            return ""
        start = m.end()
        pos, depth, end = start, 1, None
        while depth > 0:
            nxt_open = html.find("<div", pos)
            nxt_close = html.find("</div", pos)
            if nxt_close == -1:
                end = len(html)
                break
            if nxt_open != -1 and nxt_open < nxt_close:
                depth += 1
                pos = nxt_open + 4
            else:
                depth -= 1
                if depth == 0:
                    end = nxt_close
                pos = nxt_close + 5
        return html[start : end if end is not None else len(html)]

    @staticmethod
    def _meta(html: str, prop: str) -> str:
        m = re.search(rf'<meta property="{re.escape(prop)}" content="([^"]*)"', html)
        return html_lib.unescape(m.group(1)).strip() if m else ""

    # ------------------------------------------------------------ 对外接口

    def latest(self, count: int = 1) -> list[Article]:
        candidates = self._recent_urls(self._newest_post_sitemap(), self.max_candidates)
        found: list[Article] = []
        for url in candidates:
            if len(found) >= count:
                break
            page = get_text(url)
            if self.category_path not in page:  # 播客/长文，不是每日邮件
                continue
            raw = html_to_md(self._extract_container(page))
            found.append(
                Article(
                    source=self.name,
                    title=self._meta(page, "og:title") or "(untitled)",
                    url=url,
                    date=(self._meta(page, "article:published_time") or "")[:10],
                    text=md_to_plain(raw),
                    raw=raw,
                )
            )
        if not found:
            raise RuntimeError("最近的候选中没有找到每日邮件文章（可能还没发布）")
        return found
