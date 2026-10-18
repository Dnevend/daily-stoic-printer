from dailyprint.models import Article, Issue, VocabItem
from dailyprint.render import encode, render
from dailyprint.render.receipt import test_page as build_test_page
from dailyprint.textutil import dlen


def make_issue() -> Issue:
    article = Article(
        source="test",
        title="Let Each Sphere Come First",
        url="https://example.com/let-each-sphere-come-first/",
        date="2026-10-17",
        text="Think about how rarely we give ourselves fully to what we are doing. " * 4,
    )
    return Issue(
        article=article,
        vocab=[
            VocabItem(
                word="sphere",
                context="Each was first in its own sphere, neither came second.",
                gloss="n. 球, 球体, 范围",
            )
        ],
    )


def test_render_contains_header_and_vocab():
    text = render(make_issue(), width=48, stamp="2026-10-18 09:00")
    assert "DAILY ENGLISH" in text
    assert "TODAY'S WORDS" in text
    assert "sphere" in text
    assert "球" in text
    assert "printed: 2026-10-18 09:00" in text


def test_render_lines_fit_width():
    text = render(make_issue(), width=48)
    assert all(dlen(line) <= 48 for line in text.split("\n"))


def test_render_truncates_long_articles():
    issue = make_issue()
    issue.article.text = " ".join(f"w{i}" for i in range(500))
    text = render(issue, width=48, max_words=100)
    assert "truncated to first 100 words" in text
    assert all(dlen(line) <= 48 for line in text.split("\n"))


def test_render_keeps_short_articles_intact():
    text = render(make_issue(), width=48, max_words=900)
    assert "truncated" not in text
    assert "Think about how rarely" in text


def test_render_includes_translation_section():
    issue = make_issue()
    issue.translation = (
        "想想我们很少会全身心地投入到自己正在做的事情里。"
        "这段中文用来验证译文分区的换行是否按显示宽度处理。"
    )
    text = render(issue, width=48)
    assert "TRANSLATION" in text
    assert "想想我们很少" in text
    assert all(dlen(line) <= 48 for line in text.split("\n"))


def test_render_without_vocab():
    issue = make_issue()
    issue.vocab = []
    assert "TODAY'S WORDS" not in render(issue)


def test_test_page_lines_fit_width():
    assert all(dlen(line) <= 48 for line in build_test_page(48).split("\n"))


def test_encode_init_and_cut():
    data = encode("hello", chinese=False)
    assert data.startswith(b"\x1b@")
    assert data.endswith(b"\x1dVB\x00")
    assert b"\x1c&" not in data


def test_encode_chinese_mode():
    data = encode("中文", chinese=True)
    assert b"\x1c&" in data
    assert "中文".encode("gb18030") in data
