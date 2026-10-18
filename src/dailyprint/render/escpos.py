"""ESC/POS 编码（80mm 热敏机）。

- 文本用 GB18030 + ``FS &`` 走中文模式（不支持中文的机型可 ``chinese=False``）
- 正文配图用位图（``GS v 0``），需要 Pillow；缺依赖时退化成一行提示文字
"""

from __future__ import annotations

import re
from pathlib import Path

from .raster import RasterError, image_to_raster

ESC = b"\x1b"
GS = b"\x1d"

_IMAGE_LINE = re.compile(r"^\[IMAGE\]\s+(.+?)\s*$")


def encode(
    text: str,
    *,
    chinese: bool = True,
    cut: bool = True,
    images: dict[str, Path] | None = None,
    max_image_height: int = 400,
) -> bytes:
    """文本 -> ESC/POS 字节流；``images`` 用于把 ``[IMAGE] 名字`` 行替换成位图。"""
    enc = "gb18030" if chinese else "ascii"
    buf = bytearray()
    buf += ESC + b"@"  # 初始化
    buf += ESC + b"3\x18"  # 行距
    if chinese:
        buf += b"\x1c\x26"  # FS & 进入中文模式

    for line in text.split("\n"):
        match = _IMAGE_LINE.match(line.strip())
        path = images.get(match.group(1)) if (match and images) else None
        if match and images is not None:
            if path is None:
                buf += f"[image missing: {match.group(1)}]".encode(enc, "replace") + b"\n"
            else:
                try:
                    buf += image_to_raster(path, max_height=max_image_height)
                    buf += b"\n"
                except RasterError as e:
                    buf += f"[image skipped: {e}]".encode(enc, "replace") + b"\n"
            continue
        buf += line.encode(enc, "replace") + b"\n"

    if cut:
        buf += b"\n\n\n\n"
        buf += GS + b"V\x42\x00"  # 进纸并切纸
    return bytes(buf)
