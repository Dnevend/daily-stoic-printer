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


def test_synthesize_say_missing_returns_none(tmp_path: Path):
    from dailyprint.enrich import audio as audio_mod

    out = tmp_path / "x.ogg"
    assert audio_mod.synthesize_say("hi", out, say="/nonexistent/say") is None


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


def test_synthesize_edge_missing_uvx_returns_none(tmp_path: Path):
    from dailyprint.enrich import audio as audio_mod

    out = tmp_path / "x.ogg"
    assert audio_mod.synthesize_edge("hi", out, uvx="/nonexistent/uvx") is None


def test_synthesize_uses_edge_when_engine_edge(monkeypatch, tmp_path: Path):
    from dailyprint.config import AudioConfig
    from dailyprint.enrich import audio as audio_mod

    cfg = AudioConfig(engine="edge")
    out = tmp_path / "x.ogg"
    edge_calls = []

    def fake_edge(text, path, voice, rate, **kwargs):
        edge_calls.append((text, voice, rate))
        path.touch()
        return path

    monkeypatch.setattr(audio_mod, "synthesize_edge", fake_edge)

    def no_say(*a, **k):
        raise AssertionError("should not call say")

    monkeypatch.setattr(audio_mod, "synthesize_say", no_say)
    result = audio_mod.synthesize("hello", out, cfg=cfg)
    assert result == out
    assert edge_calls == [("hello", cfg.voice, cfg.rate)]


def test_synthesize_auto_falls_back_to_say(monkeypatch, tmp_path: Path):
    from dailyprint.config import AudioConfig
    from dailyprint.enrich import audio as audio_mod

    cfg = AudioConfig(engine="auto")
    out = tmp_path / "x.ogg"
    monkeypatch.setattr(audio_mod, "synthesize_edge", lambda *a, **k: None)

    say_calls = []

    def fake_say(text, path, voice, rate_wpm, **kwargs):
        say_calls.append((text, voice, rate_wpm))
        path.touch()
        return path

    monkeypatch.setattr(audio_mod, "synthesize_say", fake_say)
    result = audio_mod.synthesize("hello", out, cfg=cfg)
    assert result == out
    assert say_calls == [("hello", cfg.say_voice, cfg.say_rate)]


def test_synthesize_engine_say_skips_edge(monkeypatch, tmp_path: Path):
    from dailyprint.config import AudioConfig
    from dailyprint.enrich import audio as audio_mod

    cfg = AudioConfig(engine="say")
    out = tmp_path / "x.ogg"

    def fake_edge(*a, **k):
        raise AssertionError("should not call edge")

    monkeypatch.setattr(audio_mod, "synthesize_edge", fake_edge)
    monkeypatch.setattr(audio_mod, "synthesize_say", lambda text, path, **k: (path.touch() or path))
    result = audio_mod.synthesize("hello", out, cfg=cfg)
    assert result == out


def test_audio_config_has_new_fields():
    from dailyprint.config import AudioConfig

    cfg = AudioConfig()
    assert cfg.engine == "auto"
    assert cfg.voice == "en-US-AriaNeural"
    assert cfg.rate == "-10%"
    assert cfg.say_voice == "Samantha"
    assert cfg.say_rate == 160


def test_send_dir_and_archive_dir(tmp_path: Path):
    from dailyprint.config import AudioConfig, Paths
    from dailyprint.enrich.audio import archive_dir, send_dir

    ac = AudioConfig(send_dir=str(tmp_path / "send"), archive_dir=str(tmp_path / "arc"))
    paths = Paths(tmp_path)
    assert send_dir(ac) == tmp_path / "send"
    assert archive_dir(ac, paths) == tmp_path / "arc"


def test_archive_dir_falls_back_to_out_dir(tmp_path: Path):
    from dailyprint.config import AudioConfig, Paths
    from dailyprint.enrich.audio import archive_dir

    ac = AudioConfig(archive_dir="", out_dir=str(tmp_path / "legacy"))
    paths = Paths(tmp_path)
    assert archive_dir(ac, paths) == tmp_path / "legacy"
