from pathlib import Path

import pytest

from dailyprint.config import AppConfig, PrinterConfig, RenderConfig, load_config, project_root
from dailyprint.sources import available_types


def test_defaults():
    cfg = load_config("/nonexistent/config.toml")
    assert cfg.source == "daily-stoic"
    assert cfg.render.width == 48
    assert cfg.render.chinese is True
    assert "daily-stoic" in cfg.sources
    assert cfg.printer.kind == "network"


def test_load_toml(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[defaults]\nsource = "myblog"\n\n'
        '[render]\nwidth = 42\nwords = 5\nchinese = false\n\n'
        '[printer]\nip = "192.168.1.9"\nport = 9100\n\n'
        '[sources.myblog]\ntype = "rss"\nurl = "https://example.com/feed"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.source == "myblog"
    assert cfg.render.width == 42
    assert cfg.render.words == 5
    assert cfg.render.chinese is False
    assert cfg.printer.ip == "192.168.1.9"
    assert cfg.sources["myblog"]["type"] == "rss"
    # 内置来源仍在
    assert "daily-stoic" in cfg.sources
    assert cfg.config_path == path


def test_source_spec_unknown():
    cfg = AppConfig()
    try:
        cfg.source_spec("nope")
    except KeyError as e:
        assert "nope" in str(e)
    else:  # pragma: no cover
        raise AssertionError("应当抛 KeyError")


def test_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DAILYPRINT_HOME", str(tmp_path))
    monkeypatch.setenv("DAILYPRINT_PRINTER_IP", "10.0.0.2")
    cfg = load_config("/nonexistent/config.toml")
    assert cfg.paths.home == tmp_path
    assert cfg.printer.ip == "10.0.0.2"
    assert cfg.paths.dictionary == tmp_path / "data" / "dict.tsv"


def test_project_root_has_pyproject():
    assert (project_root() / "pyproject.toml").exists()


def test_source_types_registered():
    assert {"daily_stoic", "rss"} <= set(available_types())


def test_config_dataclasses_are_independent():
    a, b = RenderConfig(), RenderConfig()
    a.width = 1
    assert b.width == 48
    assert PrinterConfig().port == 9100


def test_example_config_loads():
    """守住仓库里那份示例配置：照抄 config.toml 必须能加载。"""
    path = project_root() / "config.example.toml"
    cfg = load_config(path)
    assert cfg.source == "daily-stoic"
    assert cfg.render.images in {"off", "content", "all"}
    assert cfg.render.chinese is True
    assert cfg.cover.source in {"wikimedia", "picsum", "local", "none"}
    assert cfg.cover.keywords  # 非空
    assert cfg.translation.providers
    assert cfg.printer.kind in {"network", "cups"}


def test_unknown_key_in_section_reports_name(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[render]\nwidht = 48\n', encoding="utf-8")  # 拼错 width
    with pytest.raises(ValueError) as err:
        load_config(path)
    assert "widht" in str(err.value) and "[render]" in str(err.value)


def test_toml_lists_become_tuples(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[render]\npromo_phrases = ["a", "b"]\n[cover]\nkeywords = ["x"]\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.render.promo_phrases == ("a", "b")
    assert cfg.cover.keywords == ("x",)


def test_translation_config_from_toml(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[translation]\ntarget = "zh-TW"\nproviders = ["google"]\nemail = "me@example.com"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.translation.target == "zh-TW"
    assert cfg.translation.providers == ("google",)  # TOML 列表被转成 tuple
    assert cfg.translation.email == "me@example.com"
    assert cfg.paths.translation_cache == cfg.paths.cache / "translate"
