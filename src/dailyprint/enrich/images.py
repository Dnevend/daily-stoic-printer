"""正文配图的挑选与下载。

"正文配图"= 没有被链到商店/推广页的图片；推广图（如书籍横幅、纪念币照片）
在段落过滤和这里都会被排除。图片按 URL 缓存在 ``data/cache/images/``。
"""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
from pathlib import Path

from ..models import ImageRef
from ..sources.http import get
from .promo import is_promo_link

log = logging.getLogger("dailyprint")

# [![alt](img)](link) —— 图片被链接包着（推广图常见）
_LINKED_IMG = re.compile(
    r"\[\s*!\[[^\]]*\]\((https?://[^)]+)\)\s*\]\((https?://[^)]+)\)"
)
# ![alt](img)
_PLAIN_IMG = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)")


def _label(url: str, used: set[str]) -> str:
    name = Path(urllib.parse.urlsplit(url).path).name or "image"
    name = urllib.parse.unquote(name)[:48]
    if name not in used:
        used.add(name)
        return name
    stem, dot, ext = name.rpartition(".")
    i = 2
    while f"{stem}-{i}{dot}{ext}" in used:
        i += 1
    unique = f"{stem}-{i}{dot}{ext}"
    used.add(unique)
    return unique


def select_content_images(
    md: str, *, limit: int = 2, skip_promo: bool = True
) -> list[ImageRef]:
    """从 Markdown 里挑出正文配图（保持出现顺序、去重、限量）。"""
    found: list[ImageRef] = []

    def take_linked(match: re.Match) -> str:
        img_url, link_url = match.group(1), match.group(2)
        if not skip_promo or not (is_promo_link(link_url) or is_promo_link(img_url)):
            found.append(ImageRef(url=img_url, label=""))
        return " "  # 已处理，从待扫描文本里移除

    rest = _LINKED_IMG.sub(take_linked, md)
    for match in _PLAIN_IMG.finditer(rest):
        url = match.group(1)
        if skip_promo and is_promo_link(url):
            continue
        found.append(ImageRef(url=url, label=""))

    used: set[str] = set()
    unique: list[ImageRef] = []
    for ref in found:
        if any(ref.url == kept.url for kept in unique):
            continue
        ref.label = _label(ref.url, used)
        unique.append(ref)
    return unique[:limit]


def fetch_image(url: str, cache_dir: Path, *, timeout: int = 60) -> Path:
    """下载图片到缓存目录（按 URL 哈希命名），返回本地路径。"""
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower() or ".img"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    dest = Path(cache_dir) / f"{digest}{ext}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(get(url, timeout=timeout))
    log.debug("图片已缓存: %s", dest.name)
    return dest
