#!/usr/bin/env python3
"""
Daily Stoic 每日邮件文章抓取

用法:
    python3 fetch_latest.py                 # 抓最新 1 篇（含图片下载）
    python3 fetch_latest.py 3               # 抓最新 3 篇
    python3 fetch_latest.py 3 --no-images   # 不下载图片，只保留远程链接
    python3 fetch_latest.py 3 --force       # 覆盖已存在的文件

原理:
    1. 读 sitemap 索引，选最近更新的 post-sitemap
    2. 按 lastmod 从新到旧取候选 URL
    3. 页面 HTML 含 /category/daily-stoic-emails/ 的才是每日邮件（播客/长文会被过滤）
    4. 从 <div class="fe-single-post-content"> 提取正文，转 Markdown 保存
    5. 默认把正文图片下载到 articles/images/，用相对路径引用（方便本地预览/离线查看）

输出: ./articles/YYYY-MM-DD-<slug>.md
"""

from __future__ import annotations

import argparse
import gzip
import html as html_lib
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://dailystoic.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) daily-stoic-fetch/0.1"
EMAIL_CAT = "/category/daily-stoic-emails/"
TOP_CANDIDATES = 12
ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "articles"
IMG_DIR = OUT_DIR / "images"


# ---------------------------------------------------------------- HTTP

def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": UA})


def get(url: str, timeout: int = 30) -> bytes:
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} 失败: {last_err}")


def get_text(url: str) -> str:
    return get(url).decode("utf-8", "replace")


# ---------------------------------------------------------------- 发现候选

def newest_post_sitemap() -> str:
    index = get_text(f"{BASE}/sitemap_index.xml")
    entries = []
    for block in re.findall(r"(?s)<sitemap>(.*?)</sitemap>", index):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        lastmod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        if loc and lastmod and "post-sitemap" in loc.group(1):
            entries.append((loc.group(1), lastmod.group(1)))
    if not entries:
        raise RuntimeError("sitemap 索引里没有找到 post-sitemap")
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries[0][0]


def recent_urls(sitemap_url: str, n: int = TOP_CANDIDATES) -> list[str]:
    xml = get_text(sitemap_url)
    urls = []
    for block in re.findall(r"(?s)<url>(.*?)</url>", xml):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        lastmod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        if loc:
            urls.append((loc.group(1), lastmod.group(1) if lastmod else ""))
    urls.sort(key=lambda x: x[1], reverse=True)
    return [u for u, _ in urls[:n]]


# ---------------------------------------------------------------- 提取

def extract_content(html: str) -> str:
    """按嵌套配平，抽取 fe-single-post-content 这个 div 的完整内容。"""
    m = re.search(r'<div[^>]*class="[^"]*fe-single-post-content[^"]*"[^>]*>', html)
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


def strip_tags(s: str) -> str:
    return re.sub(r"(?s)<[^>]+>", "", s)


def html_to_md(fragment: str) -> str:
    """正文 HTML -> Markdown（覆盖 <p>/<em>/<strong>/<a>/<img>/<h2>/<blockquote> 等常见结构）。"""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", fragment)
    # noscript 里是同一张图的重复版本，直接丢掉，避免重复图片
    s = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", "", s)
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)

    def img_repl(m: re.Match) -> str:
        tag = m.group(0)
        # 懒加载图：真链接在 data-src；没有 data-src 时用 src（跳过 data: 占位图）
        src = re.search(r'data-src="([^"]+)"', tag) or re.search(r'src="([^"]+)"', tag)
        if not src or src.group(1).startswith("data:"):
            return ""
        alt = re.search(r'alt="([^"]*)"', tag)
        return f"![{alt.group(1) if alt else ''}]({src.group(1)})"

    s = re.sub(r"(?is)<img[^>]*>", img_repl, s)
    s = re.sub(
        r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"[{html_lib.unescape(strip_tags(m.group(2))).strip()}]({m.group(1)})",
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


def parse_meta(html: str, prop: str) -> str:
    m = re.search(rf'<meta property="{re.escape(prop)}" content="([^"]*)"', html)
    return html_lib.unescape(m.group(1)).strip() if m else ""


# ---------------------------------------------------------------- 图片本地化

def localize_images(md: str, slug: str) -> str:
    """把 markdown 里的远程图片下载到 articles/images/，改成相对路径引用。"""
    urls = list(dict.fromkeys(re.findall(r"!\[[^\]]*\]\((https?://[^)]+)\)", md)))
    if not urls:
        return md
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for i, url in enumerate(urls, start=1):
        ext = Path(urlparse(url).path).suffix or ".jpg"
        fname = f"{slug}-{i}{ext}"
        dest = IMG_DIR / fname
        if not dest.exists():
            try:
                dest.write_bytes(get(url, timeout=60))
                print(f"  图片: {fname} ({dest.stat().st_size // 1024} KB)")
                time.sleep(0.3)
            except RuntimeError as e:
                print(f"  ! 图片下载失败 {url}: {e}")
                continue
        mapping[url] = f"images/{fname}"
    for url, local in mapping.items():
        md = md.replace(f"]({url})", f"]({local})")
    return md


# ---------------------------------------------------------------- 主流程

def main() -> int:
    p = argparse.ArgumentParser(description="抓取 Daily Stoic 每日邮件文章")
    p.add_argument("count", nargs="?", type=int, default=1, help="抓最新 N 篇（默认 1）")
    p.add_argument("--no-images", action="store_true", help="不下载图片，只保留远程链接")
    p.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = p.parse_args()
    if args.count < 1:
        print("count 要 >= 1")
        return 2

    sitemap = newest_post_sitemap()
    print(f"最新 sitemap: {sitemap}")
    candidates = recent_urls(sitemap)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    found = 0
    for url in candidates:
        if found >= args.count:
            break
        try:
            page = get_text(url)
        except RuntimeError as e:
            print(f"  ! 跳过 {url}: {e}")
            continue
        if EMAIL_CAT not in page:
            continue  # 播客/长文，不是每日邮件

        title = parse_meta(page, "og:title")
        published = parse_meta(page, "article:published_time")
        date = (published or "")[:10]
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        out_path = OUT_DIR / f"{date}-{slug}.md"

        if out_path.exists() and not args.force:
            print(f"已存在，跳过: {out_path.name}  （要覆盖加 --force）")
            found += 1
            continue

        body = html_to_md(extract_content(page))
        if not args.no_images:
            body = localize_images(body, slug)
        header = (
            f"# {title}\n\n"
            f"- 发布日期: {date}\n"
            f"- 原文: {url}\n"
            f"- 抓取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
        )
        out_path.write_text(header + body + "\n", encoding="utf-8")
        words = len(re.findall(r"\w+", body))
        print(f"已保存: {out_path}  ({words} words)")
        found += 1
        time.sleep(0.5)  # 对站点的基本礼貌

    if found == 0:
        print("最近的候选中没有发现每日邮件文章（可能还没发布）")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"错误: {e}")
        raise SystemExit(1)
