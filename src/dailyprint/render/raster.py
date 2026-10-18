"""把图片编码成 ESC/POS 位图（``GS v 0``）。

- 80mm 热敏机可打印宽度 576 dots（203dpi）
- 图片先等比缩放到宽度/高度上限，再二值化（默认 Floyd-Steinberg 抖动，照片更耐看）
- 需要 Pillow：``uv pip install -e ".[images]"``
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_WIDTH = 576  # 80mm @203dpi


class RasterError(RuntimeError):
    pass


def available() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def image_to_raster(
    source: bytes | str | Path,
    *,
    max_width: int = MAX_WIDTH,
    max_height: int = 400,
    dither: bool = True,
) -> bytes:
    """返回 ESC/POS 位图命令（``GS v 0`` 头 + 1bit 数据，1=黑）。"""
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover - 取决于环境
        raise RasterError('需要 Pillow：uv pip install -e ".[images]"') from e

    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    try:
        with Image.open(io.BytesIO(data)) as raw:
            img = raw.convert("L")
    except Exception as e:  # noqa: BLE001
        raise RasterError(f"无法解码图片: {e}") from e

    scale = min(1.0, max_width / img.width, max_height / img.height)
    if scale < 1.0:
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.resize(size, Image.LANCZOS)

    mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    mono = img.convert("1", dither=mode)

    stride = (mono.width + 7) // 8
    # Pillow 的 1bit 输出里 1=白；ESC/POS 里 1=黑，所以要反相
    payload = bytes(b ^ 0xFF for b in mono.tobytes())

    header = b"\x1dV\x000" + bytes(
        [stride & 0xFF, (stride >> 8) & 0xFF, mono.height & 0xFF, (mono.height >> 8) & 0xFF]
    )
    return header + payload
