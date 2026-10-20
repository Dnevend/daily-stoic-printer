"""把图片编码成 ESC/POS 位图（``GS v 0``）。

- 80mm 热敏机可打印宽度 576 dots（203dpi）
- 图片先等比缩放到宽度/高度上限，再二值化（默认 Floyd-Steinberg 抖动，照片更耐看）
- 需要 Pillow：``uv pip install -e ".[images]"``

关于 XPrinter XP-80T 的实测结论（2026-10，型号固件差异，仅供排错参考）：

- 命令头必须是 ``1D 76 30 00``（``GS v 0 m``，小写 ``v``）。写成大写
  ``1D 56 30 00`` 是 ``GS V 48``，即**切纸**，打印机随后把整段位图当文本
  逐字节打出来，变成一长条乱码（乱码前会先切一刀）。
- 之前记录的「同一串位图单独发正常、夹在文章里成噪点」是同一个 bug 的
  另一种表现（缺纸/切纸后的错位），已随命令头修复；若再现再单独排查。
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


def prepare_bitmap(
    source: bytes | str | Path,
    *,
    max_width: int = MAX_WIDTH,
    max_height: int = 400,
    dither: bool = True,
):
    """把图片处理成热敏打印机要的 1bit 图（1=白、0=黑）。位图编码与预览共用。

    等比缩放到 (max_width, max_height) 以内，并**居中补白到纸宽**，
    这样窄图/竖图不会贴着左边。
    """
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

    if mono.width < max_width:  # 纸宽内居中
        canvas = Image.new("1", (max_width, mono.height), 1)
        canvas.paste(mono, ((max_width - mono.width) // 2, 0))
        mono = canvas
    return mono


def image_to_raster(
    source: bytes | str | Path,
    *,
    max_width: int = MAX_WIDTH,
    max_height: int = 400,
    dither: bool = True,
) -> bytes:
    """返回 ESC/POS 位图命令（``GS v 0`` 头 + 1bit 数据，1=黑）。

    整张图用**一条**命令发完。历史实测这台机器收到多条 ``GS v 0`` 会解析错乱，
    但那批实验是在命令头写错（大写 ``V``）的前提下做的，结论未复测，保守起见
    仍不按行切带。
    """
    mono = prepare_bitmap(source, max_width=max_width, max_height=max_height, dither=dither)

    stride = (mono.width + 7) // 8
    # Pillow 的 1bit 输出里 1=白；ESC/POS 里 1=黑，所以要反相
    payload = bytes(b ^ 0xFF for b in mono.tobytes())

    # GS v 0 m xL xH yL yH —— 四个字节是 1D 76 30 00：
    #   1D 76 = GS v（小写 v，位图；大写 V 是 GS V 切纸）
    #   30    = m，位图模式 0
    # 写成大写 1D 56 30 00 会让打印机执行切纸，再把后面的数据当文本打成
    # 一长条乱码（2026-10 真机复现：乱码前正好被切了一刀）。
    header = b"\x1dv0\x00" + bytes(
        [stride & 0xFF, (stride >> 8) & 0xFF, mono.height & 0xFF, (mono.height >> 8) & 0xFF]
    )
    return header + payload
