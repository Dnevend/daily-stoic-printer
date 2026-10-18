"""语音合成辅助函数测试。"""

from pathlib import Path
from types import SimpleNamespace

from dailyprint.config import AppConfig
from dailyprint.enrich.audio import build_speech_text
from dailyprint.models import Article, Issue


def _issue(text: str = "Hello world.", translation: str = "") -> Issue:
    return Issue(
        article=Article(
            source="test",
            title="Test Article",
            url="https://example.com/test",
            date="2026-10-18",
            text=text,
        ),
        translation=translation,
    )


def test_build_speech_text_uses_plain_text():
    issue = _issue("One two three.")
    assert build_speech_text(issue) == "One two three."


def test_build_speech_text_limits_words():
    issue = _issue("One two three four five.")
    assert build_speech_text(issue, max_words=3) == "One two three"


def test_build_speech_text_zero_means_unlimited():
    text = "One two three four five."
    issue = _issue(text)
    assert build_speech_text(issue, max_words=0) == text


def test_build_speech_text_includes_translation_when_requested():
    issue = _issue("Hello.", translation="你好。")
    result = build_speech_text(issue, include_translation=True)
    assert "Hello." in result
    assert "Translation." in result
    assert "你好。" in result


def test_build_speech_text_ignores_empty_translation():
    issue = _issue("Hello.")
    result = build_speech_text(issue, include_translation=True)
    assert "Translation" not in result


def test_build_speech_text_strips_whitespace():
    issue = _issue("  Hello world.  ")
    assert build_speech_text(issue) == "Hello world."


def test_synthesize_missing_say_returns_none(tmp_path: Path):
    from dailyprint.enrich import audio as audio_mod

    out = tmp_path / "x.ogg"
    assert audio_mod.synthesize("hi", out, say="/nonexistent/say") is None


def test_send_audio_missing_openclaw_returns_false(tmp_path: Path):
    from dailyprint.enrich import audio as audio_mod

    path = tmp_path / "fake.ogg"
    path.write_text("x", encoding="utf-8")
    assert (
        audio_mod.send_audio(path, "telegram", "123", "cap", openclaw="/nonexistent/openclaw")
        is False
    )


def test_run_audio_swallows_synthesize_failure(monkeypatch, tmp_path: Path):
    """synthesize 返回 None 时 _run_audio 不应抛异常。"""
    from dailyprint import cli

    cfg = AppConfig()
    cfg.paths = cfg.paths.__class__(tmp_path)
    issue = _issue("Hello world.")
    args = SimpleNamespace(no_audio=False)
    monkeypatch.setattr(cli, "synthesize", lambda *a, **k: None)
    cli._run_audio(args, cfg, issue)  # 不抛即通过


def test_run_audio_swallows_exception(monkeypatch, tmp_path: Path):
    """语音链路抛异常时 _run_audio 应吞掉，不影响打印主流程。"""
    from dailyprint import cli

    cfg = AppConfig()
    cfg.paths = cfg.paths.__class__(tmp_path)
    issue = _issue("Hello world.")
    args = SimpleNamespace(no_audio=False)

    def boom(*a, **k):
        raise RuntimeError("say broken")

    monkeypatch.setattr(cli, "synthesize", boom)
    cli._run_audio(args, cfg, issue)  # 不抛即通过
