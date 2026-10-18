"""ESC/POS 编码（80mm 热敏机）。

中文需要用 GB18030 编码并先发 ``FS &`` 进入中文模式；不支持的机型可用
``chinese=False`` 退化为纯 ASCII。
"""

from __future__ import annotations

ESC = b"\x1b"
GS = b"\x1d"


def encode(text: str, *, chinese: bool = True, cut: bool = True) -> bytes:
    buf = bytearray()
    buf += ESC + b"@"  # 初始化
    buf += ESC + b"3\x18"  # 行距
    if chinese:
        buf += b"\x1c\x26"  # FS & 进入中文模式
    enc = "gb18030" if chinese else "ascii"
    for line in text.split("\n"):
        buf += line.encode(enc, "replace") + b"\n"
    if cut:
        buf += b"\n\n\n\n"
        buf += GS + b"V\x42\x00"  # 进纸并切纸
    return bytes(buf)
