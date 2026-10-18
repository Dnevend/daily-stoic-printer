import io
from pathlib import Path

import pytest

from dailyprint.enrich.images import select_content_images
from dailyprint.enrich.promo import promo_reason
from dailyprint.models import Article, ImageRef, Issue
from dailyprint.render import encode
from dailyprint.render.raster import RasterError, image_to_raster
from dailyprint.render.receipt import render
from dailyprint.textutil import dlen

PLAIN = "![A photo](https://www.themarginalian.org/wp-content/uploads/2026/10/spac1.jpg)"
LINKED_PROMO = (
    "[![Book](https://dailystoic.com/wp-content/uploads/x/banner.jpg)]"
    "(https://store.dailystoic.com/pages/x)"
)
LINKED_PLAIN = "[![Photo](https://example.com/a/pic.jpg)](https://example.com/article)"


# ---------------------------------------------------------------- 挑选

def test_select_skips_promo_linked_images():
    images = select_content_images("\n\n".join([PLAIN, LINKED_PROMO]))
    assert [i.url for i in images] == [PLAIN.split("(")[-1].rstrip(")")]
    assert images[0].label == "spac1.jpg"


def test_select_keeps_plain_linked_images():
    assert [i.url for i in select_content_images(LINKED_PLAIN)] == ["https://example.com/a/pic.jpg"]


def test_select_dedupes_and_limits():
    md = "\n\n".join([PLAIN, PLAIN, LINKED_PLAIN])
    assert len(select_content_images(md, limit=2)) == 2
    assert len(select_content_images(md, limit=1)) == 1


def test_select_all_mode_keeps_promo_images():
    assert len(select_content_images(LINKED_PROMO, skip_promo=False)) == 1


def test_select_resolves_relative_urls_with_base():
    md = "![photo](/media/2026/10/pic.jpg)"
    images = select_content_images(md, base_url="https://example.com/posts/hello/")
    assert [i.url for i in images] == ["https://example.com/media/2026/10/pic.jpg"]


def test_select_skips_relative_urls_without_base():
    assert select_content_images("![photo](/media/pic.jpg)") == []


def test_select_ignores_data_urls():
    md = "![inline](data:image/gif;base64,R0lGODlhAQABAAAAACw=)"
    assert select_content_images(md, base_url="https://example.com/") == []


def test_select_handles_markdown_image_titles():
    md = '![photo](https://example.com/a.jpg "A caption")'
    assert [i.url for i in select_content_images(md)] == ["https://example.com/a.jpg"]


def test_labels_are_unique_for_same_filename():
    a = "![x](https://a.example.com/2026/10/photo.jpg)"
    b = "![y](https://b.example.com/2026/11/photo.jpg)"
    labels = [i.label for i in select_content_images("\n\n".join([a, b]))]
    assert len(set(labels)) == 2


# ---------------------------------------------------------------- 段落规则

def test_content_images_are_not_treated_as_promo():
    assert promo_reason(PLAIN) is None
    assert promo_reason(LINKED_PLAIN) is None


def test_store_linked_image_paragraph_is_promo():
    assert promo_reason(LINKED_PROMO) == "image-only"


# ---------------------------------------------------------------- 排版

def test_render_lists_images():
    article = Article(source="s", title="T", url="u", date="2026-10-18", text="Hello world.")
    issue = Issue(article=article, images=[ImageRef(url="x", label="spac1.jpg")])
    text = render(issue, width=48)
    assert "[IMAGE] spac1.jpg" in text
    assert all(dlen(line) <= 48 for line in text.split("\n"))


# ---------------------------------------------------------------- 位图

def _png(width: int = 8, height: int = 2, black_first_row: bool = True) -> bytes:
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("1", (width, height), 1)
    if black_first_row:
        for x in range(width):
            img.putpixel((x, 0), 0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_raster_header_geometry_and_inversion():
    data = image_to_raster(_png())
    assert data[:4] == b"\x1dV\x000"
    assert data[4:8] == bytes([1, 0, 2, 0])  # stride=1 byte, height=2
    assert data[8:] == b"\xff\x00"  # 黑行全 1、白行全 0（位图 1=黑）


def test_raster_scales_down_to_max_width():
    big = _png(width=64, height=8)
    data = image_to_raster(big, max_width=16, max_height=100)
    stride = data[4] | (data[5] << 8)
    height = data[6] | (data[7] << 8)
    assert stride == 2  # 16 dots -> 2 bytes
    assert height == 2  # 8 * (16/64)
    assert len(data) == 8 + stride * height


def test_raster_wraps_decode_errors():
    pytest.importorskip("PIL")
    with pytest.raises(RasterError):
        image_to_raster(b"definitely not an image")


def test_encode_replaces_image_line(tmp_path: Path):
    path = tmp_path / "t.png"
    path.write_bytes(_png())
    data = encode("[IMAGE] t.png\nhello", chinese=False, images={"t.png": path})
    assert b"\x1dV\x000" in data
    assert b"hello" in data


def test_encode_reports_missing_image():
    data = encode("[IMAGE] nope.png", chinese=False, images={})
    assert b"[image missing: nope.png]" in data


def test_encode_without_images_param_keeps_line():
    data = encode("[IMAGE] t.png", chinese=False)
    assert b"[IMAGE] t.png" in data
