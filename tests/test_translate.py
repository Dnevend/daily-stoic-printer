from pathlib import Path

import pytest

from dailyprint.enrich import translate as tr

# ---------------------------------------------------------------- 切块

def test_split_chunks_respects_limit_and_sentences():
    text = ("This is sentence one. " * 30).strip()
    chunks = tr.split_chunks(text, limit=100)
    assert chunks
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_split_chunks_hard_splits_long_sentence():
    chunks = tr.split_chunks("x" * 250, limit=100)
    assert [len(c) for c in chunks] == [100, 100, 50]


# ---------------------------------------------------------------- 提供方 / 回退

@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_translate_uses_provider_and_caches(monkeypatch, cache_dir: Path):
    calls: list[str] = []

    def fake(text, target, *, timeout=20, email=""):
        calls.append(text)
        return f"[{target}]{text}"

    monkeypatch.setitem(tr.PROVIDERS, "mymemory", fake)
    translator = tr.Translator(cache_dir, providers=("mymemory",))

    out1 = translator.translate("Hello world.")
    assert out1 == "[zh-CN]Hello world."
    assert translator.requests == 1

    # 同样内容再翻一次：命中缓存，不再请求
    out2 = translator.translate("Hello world.")
    assert out2 == out1
    assert translator.requests == 1
    assert len(calls) == 1


def test_translate_falls_back_to_second_provider(monkeypatch, cache_dir: Path):
    def broken(text, target, *, timeout=20, email=""):
        raise tr.TranslationError("boom")

    def good(text, target, *, timeout=20, email=""):
        return "好"

    monkeypatch.setitem(tr.PROVIDERS, "mymemory", broken)
    monkeypatch.setitem(tr.PROVIDERS, "google", good)
    monkeypatch.setattr(tr.time, "sleep", lambda *_: None)

    translator = tr.Translator(cache_dir, providers=("mymemory", "google"))
    assert translator.translate("Hello.") == "好"


def test_translate_raises_when_all_providers_fail(monkeypatch, cache_dir: Path):
    def broken(text, target, *, timeout=20, email=""):
        raise tr.TranslationError("boom")

    monkeypatch.setitem(tr.PROVIDERS, "mymemory", broken)
    monkeypatch.setattr(tr.time, "sleep", lambda *_: None)
    translator = tr.Translator(cache_dir, providers=("mymemory",))
    with pytest.raises(tr.TranslationError):
        translator.translate("Hello.")


def test_translate_keeps_paragraphs(monkeypatch, cache_dir: Path):
    monkeypatch.setitem(tr.PROVIDERS, "mymemory", lambda t, target, **kw: f"<{t}>")
    translator = tr.Translator(cache_dir, providers=("mymemory",))
    out = translator.translate("First para.\n\nSecond para.")
    assert out == "<First para.>\n\n<Second para.>"


def test_unknown_provider_falls_back_to_default(monkeypatch, cache_dir: Path):
    monkeypatch.setitem(tr.PROVIDERS, "mymemory", lambda t, target, **kw: "ok")
    translator = tr.Translator(cache_dir, providers=("nope",))
    assert translator.providers == tr.DEFAULT_PROVIDERS


def test_join_wrapped_handles_cjk_and_latin():
    assert tr._join_wrapped("你好，\n世界") == "你好，世界"
    assert tr._join_wrapped("wrote,\nIn the Elysee") == "wrote, In the Elysee"
    assert tr._join_wrapped("惊讶\n") == "惊讶"


def test_mymemory_detects_quota_warning(monkeypatch):
    warning = {"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE"}}
    monkeypatch.setattr(tr, "_get_json", lambda url, timeout: warning)
    with pytest.raises(tr.TranslationError):
        tr.mymemory("hi", "zh-CN")
