import json
from pathlib import Path

from dailyprint.enrich import cover as cv
from dailyprint.models import Article, Cover, ImageRef, Issue
from dailyprint.render.receipt import render
from dailyprint.textutil import dlen

WIKI_PAYLOAD = {
    "query": {
        "pages": [
            {
                "title": "File:Marcus Aurelius statue.jpg",
                "imageinfo": [
                    {
                        "thumburl": "https://upload.wikimedia.org/thumb/marcus-576.jpg",
                        "thumbwidth": 576,
                        "thumbheight": 384,
                        "extmetadata": {
                            "Artist": {"value": '<a href="#">Someone</a>'},
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        },
                    }
                ],
            },
            {
                "title": "File:Tiny icon.png",
                "imageinfo": [
                    {
                        "thumburl": "https://upload.wikimedia.org/thumb/tiny.png",
                        "thumbwidth": 40,
                        "thumbheight": 40,
                        "extmetadata": {},
                    }
                ],
            },
        ]
    }
}


def test_wikimedia_picks_reasonable_image_and_builds_credit(monkeypatch):
    monkeypatch.setattr(cv, "get_text", lambda url, timeout=20: json.dumps(WIKI_PAYLOAD))
    cover = cv.fetch_cover(
        cv.CoverRequest(keywords=("marcus aurelius",)), Path("/tmp/x"), seed="2026-10-18"
    )
    assert cover is not None
    assert cover.image.url.endswith("marcus-576.jpg")  # 太小的 40x40 被跳过
    assert cover.image.label == "Marcus Aurelius statue.jpg"
    assert "Someone" in cover.credit and "CC BY-SA 4.0" in cover.credit


def test_wikimedia_returns_none_when_no_candidates(monkeypatch):
    empty = {"query": {"pages": []}}
    monkeypatch.setattr(cv, "get_text", lambda url, timeout=20: json.dumps(empty))
    assert cv.fetch_cover(cv.CoverRequest(keywords=("x",)), Path("/tmp/x"), seed="s") is None


def test_wikimedia_falls_through_to_next_keyword(monkeypatch):
    calls: list[str] = []

    def fake(url: str, timeout: int = 20) -> str:
        calls.append(url)
        if "seneca" in url:
            return json.dumps(WIKI_PAYLOAD)
        return json.dumps({"query": {"pages": []}})

    monkeypatch.setattr(cv, "get_text", fake)
    cover = cv.fetch_cover(
        cv.CoverRequest(keywords=("marcus aurelius bust", "seneca")),
        Path("/tmp/x"),
        seed="2026-10-18",
    )
    assert cover is not None
    assert any("seneca" in c for c in calls)  # 第一个关键词没结果时换了下一个


def test_picsum_is_deterministic_per_seed():
    req = cv.CoverRequest(source="picsum")
    a = cv.fetch_cover(req, Path("/tmp/x"), seed="2026-10-18")
    b = cv.fetch_cover(req, Path("/tmp/x"), seed="2026-10-18")
    c = cv.fetch_cover(req, Path("/tmp/x"), seed="2026-10-19")
    assert a.image.url == b.image.url != c.image.url
    assert "/576/320" in a.image.url


def test_local_source(tmp_path: Path):
    file = tmp_path / "cover.jpg"
    file.write_bytes(b"fake")
    cover = cv.fetch_cover(cv.CoverRequest(source="local", local_path=str(file)), tmp_path)
    assert cover.image.path == file
    assert cover.image.label == "cover.jpg"

    req = cv.CoverRequest(source="local", local_path=str(tmp_path / "nope.jpg"))
    assert cv.fetch_cover(req, tmp_path) is None


def test_none_source_returns_nothing():
    assert cv.fetch_cover(cv.CoverRequest(source="none"), Path("/tmp/x")) is None


def test_render_places_cover_after_title_with_credit():
    article = Article(
        source="s", title="Let Each Sphere Come First", url="u", date="2026-10-17", text="Body."
    )
    issue = Issue(
        article=article,
        cover=Cover(image=ImageRef(url="x", label="cover.jpg"), credit="Someone / CC BY-SA 4.0"),
    )
    lines = render(issue, width=48).split("\n")
    assert "[IMAGE] cover.jpg" in lines
    assert any("credit:" in ln for ln in lines)
    # 封面排在标题之后、正文之前
    title_at = next(i for i, ln in enumerate(lines) if "Let Each Sphere" in ln)
    assert lines.index("[IMAGE] cover.jpg") > title_at
    assert all(dlen(ln) <= 48 for ln in lines)
