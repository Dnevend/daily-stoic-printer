from dailyprint.textutil import (
    center_disp,
    dlen,
    lemmas,
    md_to_plain,
    to_ascii,
    trim_gloss,
    wrap_disp,
)


def test_dlen_counts_cjk_as_two():
    assert dlen("abc") == 3
    assert dlen("中文") == 4
    assert dlen("a中") == 3


def test_wrap_disp_respects_display_width():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    assert all(dlen(line) <= 20 for line in wrap_disp(text, 20))

    zh = "这是一段中文文字，用来测试换行是否正确处理全角字符宽度。"
    assert all(dlen(line) <= 10 for line in wrap_disp(zh, 10))


def test_wrap_disp_splits_overlong_token():
    lines = wrap_disp("https://example.com/" + "a" * 60, 20)
    assert len(lines) > 1
    assert all(dlen(line) <= 20 for line in lines)


def test_wrap_disp_keeps_paragraph_breaks():
    lines = wrap_disp("one\n\ntwo", 20)
    assert lines == ["one", "", "two"]


def test_center_disp_pads_to_width():
    out = center_disp("中文", 10)
    assert out.startswith(" ")
    assert dlen(out) <= 10


def test_to_ascii_transliterates_typography():
    assert to_ascii("“quote” — dash … caf\u00e9") == '"quote" -- dash ... cafe'


def test_md_to_plain_strips_markdown():
    md = "# Title\n\n![img](x.png)\n\nSee [link](http://a) and *em*.\n\n> quote"
    out = md_to_plain(md)
    assert "Title" in out
    assert "img" not in out
    assert "http" not in out
    assert "*em*" not in out
    assert not out.startswith(">")


def test_lemmas_reduces_inflections():
    assert "watch" in lemmas("watching")
    assert "errand" in lemmas("errands")
    assert "remind" in lemmas("reminded")
    assert lemmas("we're") == set()


def test_trim_gloss_keeps_multiple_senses():
    zh = "n. 有背长椅; vt. 决定, 整理, 安放, 使定居, 使平静, 支付, 安排, 解决, 结算"
    out = trim_gloss(zh)
    assert "vt." in out  # 不能只留下名词义
    assert dlen(out) <= 46
