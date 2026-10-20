"""``dailyprint print`` 流程测试：去重跳过、--force、--dry-run、断更提醒。

来源、打印机、Telegram 发送全部打桩，不碰网络与真实外设。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from dailyprint import cli
from dailyprint.config import AppConfig, Paths
from dailyprint.models import Article, Issue
from dailyprint.state import StateStore

URL = "https://example.com/daily"


def _issue(date_str: str, url: str = URL) -> Issue:
    return Issue(
        article=Article(
            source="test",
            title="Let Each Sphere Come First",
            url=url,
            date=date_str,
            text="One two three four five.",
        )
    )


def _cfg(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.paths = Paths(tmp_path)
    cfg.audio.enabled = False  # 语音链路不在本文件测试范围
    cfg.render.chinese = False
    return cfg


class _FakePrinter:
    def __init__(self, payloads: list, exc: Exception | None = None) -> None:
        self.payloads = payloads
        self.exc = exc

    def send(self, payload: bytes) -> None:
        if self.exc is not None:
            raise self.exc
        self.payloads.append(payload)

    def __repr__(self) -> str:
        return "FakePrinter()"


def _run_print(
    monkeypatch: pytest.MonkeyPatch,
    cfg: AppConfig,
    issue: Issue,
    *,
    force: bool = False,
    dry_run: bool = False,
    sender=None,
    printer_exc: Exception | None = None,
) -> tuple[int, list, list]:
    """跑一次 cmd_print；返回 (exit_code, 打印机收到的 payload, 发出的消息)。"""
    payloads: list = []
    messages: list = []

    def fake_sender(msg: str, *, channel: str, target: str) -> bool:
        messages.append(msg)
        return True

    monkeypatch.setattr(cli, "build_issue", lambda c: issue)
    monkeypatch.setattr(cli, "build_printer", lambda c: _FakePrinter(payloads, printer_exc))
    monkeypatch.setattr(cli, "send_text", sender or fake_sender)
    args = SimpleNamespace(dry_run=dry_run, force=force, no_audio=True)
    rc = cli.cmd_print(args, cfg)
    return rc, payloads, messages


def test_print_records_and_second_run_skips(monkeypatch, tmp_path, caplog):
    cfg = _cfg(tmp_path)
    issue = _issue(date.today().isoformat())

    rc, payloads, _ = _run_print(monkeypatch, cfg, issue)
    assert rc == 0 and len(payloads) == 1
    assert StateStore.load(cfg.paths.state).is_printed(URL)

    with caplog.at_level(logging.INFO, logger="dailyprint"):
        rc, payloads2, _ = _run_print(monkeypatch, cfg, issue)
    assert rc == 0 and payloads2 == []
    assert "已印过，跳过: Let Each Sphere Come First" in caplog.text
    assert "--force 可强制重印" in caplog.text


def test_force_reprints(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    issue = _issue(date.today().isoformat())

    _run_print(monkeypatch, cfg, issue)
    rc, payloads, _ = _run_print(monkeypatch, cfg, issue, force=True)
    assert rc == 0 and len(payloads) == 1


def test_dry_run_does_not_record(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    issue = _issue(date.today().isoformat())

    rc, payloads, _ = _run_print(monkeypatch, cfg, issue, dry_run=True)
    assert rc == 0 and payloads == []
    assert not StateStore.load(cfg.paths.state).is_printed(URL)


def test_failed_send_not_recorded(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    issue = _issue(date.today().isoformat())

    with pytest.raises(RuntimeError, match="printer offline"):
        _run_print(monkeypatch, cfg, issue, printer_exc=RuntimeError("printer offline"))
    assert not StateStore.load(cfg.paths.state).is_printed(URL)


def test_alert_fires_even_when_dedup_skips(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    old_date = (date.today() - timedelta(days=3)).isoformat()
    issue = _issue(old_date)

    # 台账里已有这篇 → dedup 会跳过，但断更提醒仍应发出
    StateStore.load(cfg.paths.state).mark_printed(issue.article, tmp_path / "prints" / "old.txt")

    rc, payloads, messages = _run_print(monkeypatch, cfg, issue)
    assert rc == 0 and payloads == []
    assert messages == [f"源站断更 3 天：最新仍是 {old_date}《Let Each Sphere Come First》"]


def test_raising_sender_does_not_break_print(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    old_date = (date.today() - timedelta(days=5)).isoformat()
    issue = _issue(old_date)

    def boom(*a, **k):
        raise RuntimeError("openclaw exploded")

    rc, payloads, _ = _run_print(monkeypatch, cfg, issue, sender=boom)
    assert rc == 0 and len(payloads) == 1
    assert StateStore.load(cfg.paths.state).is_printed(URL)


def test_parser_has_force_flag():
    args = cli.build_parser().parse_args(["print", "--force", "--dry-run"])
    assert args.force is True and args.dry_run is True
    assert cli.build_parser().parse_args(["print"]).force is False
