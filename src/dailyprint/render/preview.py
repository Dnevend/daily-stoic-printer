"""把排版结果导出成"能看"的预览。

- ``.png``：热敏纸模拟（576px 宽、48 列、图片按 1bit 抖动），和真打出来的最接近
- ``.html``：网页预览（等宽 + 图片原图），方便快速浏览
- 其它后缀：纯文本（就是发给打印机的字符）

PNG 需要 Pillow；HTML 无依赖。
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from pathlib import Path

from ..models import Issue
from ..textutil import WIDTH

IMAGE_LINE = re.compile(r"^\[IMAGE\]\s+(.+?)\s*$")

# macOS 自带字体（按优先级）
ASCII_FONTS = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Courier.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
)
CJK_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)


def _wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def _fit_font(paths: tuple[str, ...], target: float, probe: str):
    """挑一个能加载的字体，并把字号校准到"字符宽度 ≈ target"（用 probe 字符测）。"""
    from PIL import ImageFont

    for path in paths:
        try:
            base = ImageFont.truetype(path, 24)
        except OSError:
            continue
        advance = base.getlength(probe)
        if advance <= 0:
            continue
        size = max(8, round(24 * target / advance))
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def write_png(
    issue: Issue,
    text: str,
    path: Path | str,
    *,
    columns: int = WIDTH,
    paper_width: int = 576,
    max_image_height: int = 400,
) -> Path:
    """把一期内容画成"热敏纸模拟"PNG。"""
    from PIL import Image, ImageDraw

    from .raster import prepare_bitmap

    unit = paper_width / columns
    ascii_font = _fit_font(ASCII_FONTS, unit, "A")
    cjk_font = _fit_font(CJK_FONTS, unit * 2, "中")
    line_height = max(10, round(unit * 2.1))

    images = {img.label: img for img in issue.all_images() if img.path}
    lines = text.split("\n")

    blocks: list[tuple[str, object, int]] = []  # (类型, 内容, 高度)
    for line in lines:
        match = IMAGE_LINE.match(line.strip())
        ref = images.get(match.group(1)) if match else None
        if ref is not None and ref.path is not None:
            bitmap = prepare_bitmap(
                ref.path, max_width=paper_width, max_height=max_image_height
            )
            blocks.append(("image", bitmap, bitmap.height))
        elif re.fullmatch(r"[-=]{5,}", line.strip()):
            blocks.append(("rule", line.strip()[0], round(unit)))
        else:
            blocks.append(("text", line, line_height))

    height = sum(block[2] for block in blocks) + round(unit * 2)
    canvas = Image.new("L", (paper_width, height), 255)
    draw = ImageDraw.Draw(canvas)

    y = round(unit)
    for kind, content, block_height in blocks:
        if kind == "image":
            canvas.paste(content, (0, y))  # 1=白，正好贴合白纸
        elif kind == "rule":
            mid = y + block_height // 2
            draw.rectangle([0, mid, paper_width - 1, mid + 1], fill=0)
        else:
            x = 0.0
            for ch in str(content):
                step = unit * (2 if _wide(ch) else 1)
                if ch != " ":
                    font = cjk_font if _wide(ch) else ascii_font
                    draw.text((x, y - round(unit * 0.15)), ch, font=font, fill=0)
                x += step
        y += block_height

    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def write_html(
    issue: Issue,
    text: str,
    path: Path | str,
    *,
    columns: int = WIDTH,
    paper_width: int = 576,
    title: str = "dailyprint preview",
) -> Path:
    """把一期内容导出成一个窄版网页（等宽文本 + 图片）。"""
    images = {img.label: img for img in issue.all_images() if img.path}

    body: list[str] = []
    for line in text.split("\n"):
        match = IMAGE_LINE.match(line.strip())
        ref = images.get(match.group(1)) if match else None
        if ref is not None and ref.path is not None:
            src = Path(ref.path).resolve().as_uri()
            body.append(f'<figure><img src="{src}" alt="" width="{paper_width}"></figure>')
            continue
        if re.fullmatch(r"[-=]{5,}", line.strip()):
            body.append('<hr>')
            continue
        body.append(html_lib.escape(line) or "&nbsp;")

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{html_lib.escape(title)}</title>
<style>
  body {{ margin: 0; padding: 24px; background: #eceff1;
         font: 13px/1.35 "Menlo", "Courier New", monospace; }}
  .paper {{ width: {paper_width + 32}px; margin: 0 auto; padding: 16px; background: #fff;
            box-shadow: 0 2px 12px rgba(0,0,0,.18); white-space: pre-wrap; color: #111; }}
  figure {{ margin: 8px 0; }}
  img {{ display: block; max-width: 100%; image-rendering: pixelated; }}
  hr {{ border: 0; border-top: 1px dashed #999; margin: 8px 0; }}
</style></head>
<body><div class="paper">{chr(10).join(body)}</div></body></html>
"""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def write_preview(
    issue: Issue,
    text: str,
    path: Path | str,
    *,
    columns: int = WIDTH,
    paper_width: int = 576,
    max_image_height: int = 400,
) -> Path:
    """按后缀选格式：``.png`` 热敏模拟 / ``.html`` 网页 / 其它纯文本。"""
    out = Path(path).expanduser()
    suffix = out.suffix.lower()
    if suffix == ".png":
        return write_png(
            issue,
            text,
            out,
            columns=columns,
            paper_width=paper_width,
            max_image_height=max_image_height,
        )
    if suffix in (".html", ".htm"):
        return write_html(
            issue, text, out, columns=columns, paper_width=paper_width, title=issue.article.title
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return out
