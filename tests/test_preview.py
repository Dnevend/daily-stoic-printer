from pathlib import Path

import pytest

from dailyprint.models import Article, Cover, ImageRef, Issue
from dailyprint.render.preview import write_preview
from dailyprint.render.receipt import render


def _make_issue(tmp_path: Path) -> Issue:
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("L", (900, 500), 200)
    for x in range(900):
        for y in range(0, 500, 25):
            img.putpixel((x, y), 0)
    cover_path = tmp_path / "cover.png"
    img.save(cover_path)

    article = Article(
        source="s", title="Let Each Sphere Come First", url="u", date="2026-10-18", text="Hi. " * 40
    )
    return Issue(
        article=article,
        cover=Cover(
            image=ImageRef(url="x", label="cover.png", path=cover_path),
            credit="Someone / CC BY 4.0",
        ),
    )


def test_preview_txt_is_plain_text(tmp_path: Path):
    issue = _make_issue(tmp_path)
    text = render(issue, width=48)
    out = write_preview(issue, text, tmp_path / "p.txt")
    assert out.read_text(encoding="utf-8") == text + "\n"


def test_preview_png_matches_paper_width_and_has_ink(tmp_path: Path):
    from PIL import Image

    issue = _make_issue(tmp_path)
    out = write_preview(issue, render(issue, width=48), tmp_path / "p.png", columns=48)
    with Image.open(out) as im:
        assert im.width == 576  # 80mm 纸宽
        assert im.height > 400
        assert im.getextrema()[0] == 0  # 有黑像素（文字 + 图片）


def test_preview_html_embeds_images_and_escapes_text(tmp_path: Path):
    issue = _make_issue(tmp_path)
    text = render(issue, width=48).replace("Hi.", "A < B & C")
    doc = write_preview(issue, text, tmp_path / "p.html").read_text(encoding="utf-8")

    assert "<img" in doc and "file://" in doc
    assert "[IMAGE]" not in doc  # 占位行被换成真图
    assert "<hr>" in doc  # 分隔线变成分割线
    assert "A &lt; B &amp; C" in doc


def test_fit_font_calibrates_to_target_advance():
    from dailyprint.render.preview import ASCII_FONTS, CJK_FONTS, _fit_font

    ascii_font = _fit_font(ASCII_FONTS, 12.0, "A")  # 1 列 = 12px
    cjk_font = _fit_font(CJK_FONTS, 24.0, "中")  # 2 列 = 24px
    assert abs(ascii_font.getlength("A") - 12.0) < 1.5
    assert abs(cjk_font.getlength("中") - 24.0) < 1.5
