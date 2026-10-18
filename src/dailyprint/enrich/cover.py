"""封面图：从外部图源取一张图，作为小票的"封面"。

支持的源（都免 key）：

- ``wikimedia``（默认）：按关键词在 Wikimedia Commons 搜图，公版/CC 为主，
  可打印署名（作者 + 许可 + 来源页）
- ``picsum``：https://picsum.photos 随机美图（与内容无关，无需署名）
- ``local``：用本地固定图片（``cover.local_path``）
- ``none``：不要封面

同一天内结果稳定（用日期做种子），换一天自动换图。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..models import Cover, ImageRef
from ..sources.http import get_text

log = logging.getLogger("dailyprint")

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
PICSUM = "https://picsum.photos"
UA_CREDIT = "Wikimedia Commons"


def _strip_html(text: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", "", text or "")
    return " ".join(text.split())


def _pick(candidates: list, seed: str):
    """同一天内稳定地挑一个；优先横向构图（更适合做封面）。"""
    if not candidates:
        return None
    landscape = [c for c in candidates if c.get("ratio", 1.6) >= 1.2]
    pool = landscape or candidates
    ordered = sorted(pool, key=lambda c: abs(c.get("ratio", 1.6) - 1.6))
    shortlist = ordered[:5]
    index = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(shortlist)
    return shortlist[index]


def _wikimedia(keyword: str, *, width: int, seed: str, timeout: int = 20) -> Cover | None:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {keyword}",
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": str(width),
        "format": "json",
        "formatversion": "2",
    }
    from urllib.parse import urlencode

    data = json.loads(get_text(f"{WIKIMEDIA_API}?{urlencode(params)}", timeout=timeout))
    pages = (data.get("query") or {}).get("pages") or []

    candidates = []
    for page in pages:
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        url = info.get("thumburl") or info.get("url")
        height = info.get("thumbheight") or info.get("height") or 0
        w = info.get("thumbwidth") or info.get("width") or 1
        if not url or height < 120:  # 太扁/太小的不要
            continue
        meta = info.get("extmetadata") or {}
        candidates.append(
            {
                "url": url,
                "ratio": (w / height) if height else 1.6,
                "title": page.get("title", ""),
                "artist": _strip_html((meta.get("Artist") or {}).get("value", "")),
                "license": _strip_html((meta.get("LicenseShortName") or {}).get("value", "")),
            }
        )

    chosen = _pick(candidates, seed or keyword)
    if not chosen:
        return None
    name = chosen["title"].removeprefix("File:").strip()
    credit_parts = [p for p in (chosen["artist"], chosen["license"], UA_CREDIT) if p]
    return Cover(
        image=ImageRef(url=chosen["url"], label=name[:40].rstrip() or "cover.jpg"),
        credit=" / ".join(credit_parts),
    )


def _picsum(*, width: int, height: int, seed: str) -> Cover:
    url = f"{PICSUM}/seed/{seed or 'dailyprint'}/{width}/{height}"
    return Cover(image=ImageRef(url=url, label="cover-picsum.jpg"), credit="Photo: Lorem Picsum")


def _local(path: str) -> Cover | None:
    file = Path(path).expanduser()
    if not file.exists():
        log.warning("封面图不存在: %s", file)
        return None
    return Cover(image=ImageRef(url=str(file), label=file.name, path=file))


@dataclass
class CoverRequest:
    source: str = "wikimedia"
    keywords: tuple[str, ...] = ()
    local_path: str = ""
    width: int = 576
    height: int = 320


def fetch_cover(
    request: CoverRequest, cache_dir: Path, *, seed: str = "", timeout: int = 20
) -> Cover | None:
    """按配置取一张封面；失败返回 None（调用方跳过封面即可）。"""
    source = (request.source or "none").lower()
    if source == "none":
        return None
    if source == "local":
        return _local(request.local_path)
    if source == "picsum":
        return _picsum(width=request.width, height=request.height, seed=seed)

    keywords = request.keywords or ("stoicism",)
    # 用种子的不同位轮流取关键词，保证每天换主题
    index = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(keywords)
    for offset in range(len(keywords)):
        keyword = keywords[(index + offset) % len(keywords)]
        try:
            cover = _wikimedia(keyword, width=request.width, seed=seed, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            log.warning("封面搜索失败（%s）: %s", keyword, e)
            continue
        if cover:
            log.debug("封面关键词: %s", keyword)
            return cover
    return None
