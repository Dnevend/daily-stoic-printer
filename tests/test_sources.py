from pathlib import Path

import pytest

from dailyprint.sources.daily_stoic import DailyStoicSource
from dailyprint.sources.rss import RssSource

FIXTURES = Path(__file__).parent / "fixtures"

CONTAINER_HTML = """
<html><body>
  <div class="fe-post-head">head</div>
  <div class="fe-single-post-content">
    <p>Hello <em>world</em>.</p>
    <div class="inner"><p>Nested paragraph.</p></div>
    <blockquote><p>A quote.</p></blockquote>
  </div>
  <div class="fe-post-share">share buttons</div>
</body></html>
"""


def test_daily_stoic_extracts_balanced_container():
    src = DailyStoicSource(name="t")
    container = src._extract_container(CONTAINER_HTML)
    assert "Hello" in container
    assert "Nested paragraph." in container
    assert "share buttons" not in container
    assert "fe-post-head" not in container


def test_daily_stoic_meta_parsing():
    html = '<meta property="og:title" content="A &amp; B">'
    assert DailyStoicSource._meta(html, "og:title") == "A & B"


def test_rss_parses_feed_entries():
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    src = RssSource(name="t", url="https://example.com/feed")
    entries = src._entries(xml)
    assert len(entries) == 2
    titles = {e["title"] for e in entries}
    assert titles == {"First Post", "Second Post"}


def test_rss_latest_orders_by_date_and_uses_full_content(monkeypatch):
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    monkeypatch.setattr("dailyprint.sources.rss.get_text", lambda url, **kw: xml)
    src = RssSource(name="t", url="https://example.com/feed")
    articles = src.latest(1)
    assert len(articles) == 1
    assert articles[0].title == "Second Post"  # 日期更新的一篇
    assert "Second body" in articles[0].text
    assert articles[0].date == "2026-10-17"
    assert articles[0].source == "t"


def test_rss_requires_url():
    with pytest.raises(ValueError):
        RssSource(name="t", url="")
