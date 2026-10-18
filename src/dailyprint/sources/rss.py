"""通用 RSS / Atom 来源。

适合接任何提供 feed 的站点：优先使用 feed 自带的全文（``content:encoded`` /
``<content>``），没有全文时退回摘要。

config.toml 里加一段即可：
    [sources.marginalian]
    type = "rss"
    url = "https://www.themarginalian.org/feed/"
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from ..models import Article
from ..textutil import html_to_md, md_to_plain
from .base import Source
from .http import get_text

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


def _parse_date(value: str) -> datetime:
    value = (value or "").strip()
    if not value:
        return datetime(1970, 1, 1, tzinfo=UTC)
    try:  # Atom / ISO 8601
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:  # RSS / RFC 822
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=UTC)


class RssSource(Source):
    def __init__(
        self, name: str = "rss", url: str = "", max_entries: int = 30, **_: object
    ) -> None:
        super().__init__(name)
        if not url:
            raise ValueError(f"来源 {name!r} 缺少 url")
        self.url = url
        self.max_entries = max_entries

    def _entries(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        entries: list[dict] = []

        if root.tag == f"{ATOM}feed" or root.find(f"{ATOM}entry") is not None:
            for e in root.findall(f"{ATOM}entry"):
                link_el = e.find(f"{ATOM}link[@rel='alternate']") or e.find(f"{ATOM}link")
                link = link_el.get("href", "") if link_el is not None else ""
                content_el = e.find(f"{ATOM}content") or e.find(f"{ATOM}summary")
                entries.append(
                    {
                        "title": (e.findtext(f"{ATOM}title") or "").strip(),
                        "link": link,
                        "date": _parse_date(
                            e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated") or ""
                        ),
                        "content": content_el.text or "" if content_el is not None else "",
                    }
                )

        for item in root.findall("./channel/item"):
            entries.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "date": _parse_date(item.findtext("pubDate") or ""),
                    "content": item.findtext(f"{CONTENT}encoded")
                    or item.findtext("description")
                    or "",
                }
            )
        return entries

    def latest(self, count: int = 1) -> list[Article]:
        entries = self._entries(get_text(self.url))
        entries.sort(key=lambda e: e["date"], reverse=True)
        out: list[Article] = []
        for e in entries[:count]:
            raw = html_to_md(e["content"])
            out.append(
                Article(
                    source=self.name,
                    title=e["title"] or "(untitled)",
                    url=e["link"],
                    date=e["date"].strftime("%Y-%m-%d"),
                    text=md_to_plain(raw),
                    raw=raw,
                )
            )
        if not out:
            raise RuntimeError(f"feed 里没有条目: {self.url}")
        return out
