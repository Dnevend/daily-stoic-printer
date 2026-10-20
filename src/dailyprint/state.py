"""打印台账与断更提醒状态：``data/state.json``。

台账按文章 URL 记录已打印的条目，避免源站停更时每天重印同一篇；
断更提醒每个自然日最多发一次。文件损坏或格式不对时按空状态处理
（宁可多印一次，也不让定时任务崩掉）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Article

log = logging.getLogger("dailyprint")


class StateStore:
    """``data/state.json`` 的读写。结构::

        {
          "printed": {"<url>": {date, title, printed_at, print_path}, ...},
          "last_stale_alert": "YYYY-MM-DD"
        }
    """

    def __init__(self, path: Path, data: dict[str, Any] | None = None) -> None:
        self.path = path
        data = data or {}
        printed = data.get("printed")
        self._printed: dict[str, dict[str, Any]] = (
            dict(printed) if isinstance(printed, dict) else {}
        )
        last = data.get("last_stale_alert")
        self._last_stale_alert: str = last if isinstance(last, str) else ""

    @classmethod
    def load(cls, path: Path) -> StateStore:
        """读取状态；文件不存在或损坏时返回空状态。"""
        if not path.exists():
            return cls(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("状态文件损坏，按空状态重来: %s (%s)", path, e)
            return cls(path)
        if not isinstance(data, dict):
            log.warning("状态文件格式不对，按空状态重来: %s", path)
            return cls(path)
        return cls(path, data)

    def save(self) -> None:
        """写回状态文件（先写临时文件再替换，避免写一半留坏文件）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "printed": self._printed,
            "last_stale_alert": self._last_stale_alert,
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    # ------------------------------------------------------------ 打印台账

    def is_printed(self, url: str) -> bool:
        return url in self._printed

    def mark_printed(self, article: Article, print_path: Path) -> None:
        """把文章记入台账并立即写盘。只在打印机发送成功后调用。"""
        self._printed[article.url] = {
            "date": article.date,
            "title": article.title,
            "printed_at": datetime.now().isoformat(timespec="seconds"),
            "print_path": str(print_path),
        }
        self.save()

    # ------------------------------------------------------------ 断更提醒

    def stale_alert_sent_on(self, day: str) -> bool:
        """``day``（YYYY-MM-DD）当天是否已发过断更提醒。"""
        return self._last_stale_alert == day

    def mark_stale_alert(self, day: str) -> None:
        self._last_stale_alert = day
        self.save()
