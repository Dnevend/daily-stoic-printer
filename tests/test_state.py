"""打印台账（data/state.json）与断更提醒的单元测试。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from dailyprint import cli
from dailyprint.config import AppConfig, NotifyConfig, Paths, load_config
from dailyprint.models import Article
from dailyprint.state import StateStore


def _article(date_str: str = "2026-10-17", url: str = "https://example.com/a") -> Article:
    return Article(source="test", title="Let Each Sphere Come First", url=url, date=date_str)


def _cfg(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.paths = Paths(tmp_path)
    return cfg


# ------------------------------------------------------------ StateStore


def test_missing_state_loads_empty_and_not_created(tmp_path: Path):
    state = StateStore.load(tmp_path / "data" / "state.json")
    assert not state.is_printed("https://example.com/a")
    assert not state.stale_alert_sent_on("2026-10-20")
    assert not (tmp_path / "data" / "state.json").exists()  # 只读不落盘


def test_state_created_on_first_write(tmp_path: Path):
    path = tmp_path / "data" / "state.json"
    state = StateStore.load(path)
    state.mark_printed(_article(), tmp_path / "prints" / "2026-10-17.txt")
    assert path.exists()

    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["printed"]["https://example.com/a"]
    assert entry["date"] == "2026-10-17"
    assert entry["title"] == "Let Each Sphere Come First"
    assert entry["printed_at"]  # 有时间戳即可
    assert entry["print_path"].endswith("prints/2026-10-17.txt")

    again = StateStore.load(path)
    assert again.is_printed("https://example.com/a")
    assert not again.is_printed("https://example.com/b")


def test_corrupt_state_loads_empty(tmp_path: Path):
    path = tmp_path / "data" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    state = StateStore.load(path)
    assert not state.is_printed("https://example.com/a")


def test_wrong_shape_state_loads_empty(tmp_path: Path):
    path = tmp_path / "data" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text('["a","b"]', encoding="utf-8")
    state = StateStore.load(path)
    assert not state.is_printed("a")


def test_stale_alert_marker_roundtrip(tmp_path: Path):
    path = tmp_path / "data" / "state.json"
    state = StateStore.load(path)
    state.mark_stale_alert("2026-10-20")
    again = StateStore.load(path)
    assert again.stale_alert_sent_on("2026-10-20")
    assert not again.stale_alert_sent_on("2026-10-21")


# ------------------------------------------------------------ 文章年龄


def test_age_days_across_month_boundary():
    assert cli._article_age_days("2026-09-29", date(2026, 10, 2)) == 3


def test_age_days_same_day_is_zero():
    assert cli._article_age_days("2026-10-20", date(2026, 10, 20)) == 0


def test_age_days_bad_date_returns_none():
    assert cli._article_age_days("", date(2026, 10, 20)) is None
    assert cli._article_age_days("not-a-date", date(2026, 10, 20)) is None


# ------------------------------------------------------------ 断更提醒


def _notify_cfg(tmp_path: Path, stale_days: int = 2) -> AppConfig:
    cfg = _cfg(tmp_path)
    cfg.notify.stale_days = stale_days
    cfg.audio.channel = "telegram"
    cfg.audio.target = "1419937886"
    return cfg


def _collect(messages: list):
    def fake(msg: str, *, channel: str, target: str) -> bool:
        messages.append((msg, channel, target))
        return True

    return fake


def test_alert_fires_when_older_than_threshold(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    cli._notify_stale(
        cfg,
        _article("2026-09-29"),
        state,
        sender=_collect(messages),
        today=date(2026, 10, 2),
    )
    assert [m[0] for m in messages] == [
        "源站断更 3 天：最新仍是 2026-09-29《Let Each Sphere Come First》"
    ]
    assert messages[0][1:] == ("telegram", "1419937886")
    assert state.stale_alert_sent_on("2026-10-02")


def test_alert_not_fired_at_exact_threshold(tmp_path: Path):
    cfg = _notify_cfg(tmp_path, stale_days=2)
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    cli._notify_stale(
        cfg, _article("2026-09-30"), state, sender=_collect(messages), today=date(2026, 10, 2)
    )
    assert messages == []


def test_alert_at_most_once_per_day(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    kwargs = dict(sender=_collect(messages))
    cli._notify_stale(cfg, _article("2026-09-29"), state, today=date(2026, 10, 2), **kwargs)
    cli._notify_stale(cfg, _article("2026-09-29"), state, today=date(2026, 10, 2), **kwargs)
    assert len(messages) == 1
    # 换一天可以再发
    cli._notify_stale(cfg, _article("2026-09-29"), state, today=date(2026, 10, 3), **kwargs)
    assert len(messages) == 2
    assert "源站断更 4 天" in messages[1][0]


def test_alert_disabled_sends_nothing(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    cfg.notify.enabled = False
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    cli._notify_stale(
        cfg, _article("2026-01-01"), state, sender=_collect(messages), today=date(2026, 10, 2)
    )
    assert messages == []


def test_alert_channel_target_override(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    cfg.notify.channel = "discord"
    cfg.notify.target = "999"
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    cli._notify_stale(
        cfg, _article("2026-09-29"), state, sender=_collect(messages), today=date(2026, 10, 2)
    )
    assert messages[0][1:] == ("discord", "999")


def test_alert_send_failure_not_marked_and_swallowed(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    state = StateStore.load(cfg.paths.state)

    def boom(*a, **k):
        raise RuntimeError("openclaw exploded")

    cli._notify_stale(cfg, _article("2026-09-29"), state, sender=boom, today=date(2026, 10, 2))
    assert not state.stale_alert_sent_on("2026-10-02")

    # 返回 False 也不标记，下次还会再试
    cli._notify_stale(
        cfg, _article("2026-09-29"), state, sender=lambda *a, **k: False, today=date(2026, 10, 2)
    )
    assert not state.stale_alert_sent_on("2026-10-02")


def test_alert_bad_article_date_sends_nothing(tmp_path: Path):
    cfg = _notify_cfg(tmp_path)
    state = StateStore.load(cfg.paths.state)
    messages: list = []
    cli._notify_stale(
        cfg, _article(""), state, sender=_collect(messages), today=date(2026, 10, 2)
    )
    assert messages == []


# ------------------------------------------------------------ [notify] 配置


def test_notify_defaults():
    nc = NotifyConfig()
    assert nc.enabled is True
    assert nc.stale_days == 2
    assert nc.channel == "" and nc.target == ""


def test_notify_section_loads(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[notify]\nenabled = false\nstale_days = 5\nchannel = "telegram"\ntarget = "42"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.notify.enabled is False
    assert cfg.notify.stale_days == 5
    assert cfg.notify.channel == "telegram"
    assert cfg.notify.target == "42"


def test_notify_unknown_key_raises(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[notify]\nstale_day = 2\n', encoding="utf-8")  # 拼错 stale_days
    with pytest.raises(ValueError) as err:
        load_config(path)
    assert "stale_day" in str(err.value) and "[notify]" in str(err.value)
