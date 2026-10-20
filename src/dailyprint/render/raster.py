"""把图片编码成 ESC/POS 位图（``GS v 0``）。

- 80mm 热敏机可打印宽度 576 dots（203dpi）
- 图片先等比缩放到宽度/高度上限，再二值化（默认 Floyd-Steinberg 抖动，照片更耐看）
- 需要 Pillow：``uv pip install -e ".[images]"``

关于 XPrinter XP-80T 的实测结论（2026-10，型号固件差异，仅供排错参考）：

- 命令头顺序必须是 ``1D 56 30 00``（``GS v 0 m``）；写成 ``1D 56 00 30``
  打印机会把整段位图当文本逐字节打出来，变成一长条乱码。
- 整张图必须用**一条**命令发完。切成多条 ``GS v 0`` 连续下发时，这台机器
  从第二条起就解析错乱。
- 仍有未解的固件缺陷：同样的 576x200 位图，单独发（前面只有一行标签）能印出
  清晰照片，夹在完整文章里却印成噪点，而命令字节、字节数、后续文字都正常。
  怀疑与前置文本长度或打印机内部行缓冲有关，未验证。当前生产配置直接
  关掉图片（``images = "off"``、``cover.source = "none"``）绕开。
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

    整张图必须用**一条**命令发完。实测 XPrinter XP-80T 收到第二条 ``GS v 0``
    就解析错乱，把后续数据当文本打成乱码——所以不要再按行切带。
    """
    mono = prepare_bitmap(source, max_width=max_width, max_height=max_height, dither=dither)

    stride = (mono.width + 7) // 8
    # Pillow 的 1bit 输出里 1=白；ESC/POS 里 1=黑，所以要反相
    payload = bytes(b ^ 0xFF for b in mono.tobytes())

    # GS v 0 m xL xH yL yH —— 第三个字节必须是 0x30（"GS v 0" 的命令字），
    # 第四个才是 m（位图模式 0）。顺序写反的话打印机会把后面的数据当文本，
    # 打出一长串乱码。
    header = b"\x1dV\x30\x00" + bytes(
        [stride & 0xFF, (stride >> 8) & 0xFF, mono.height & 0xFF, (mono.height >> 8) & 0xFF]
    )
    return header + payload
