"""共享的 HTTP 抓取（带重试与 gzip 处理）。"""

from __future__ import annotations

import gzip
import time
import urllib.request

UA = "dailyprint/0.1 (+https://github.com/Dnevend/daily-stoic-printer)"


def get(url: str, timeout: int = 30, retries: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} 失败: {last_err}")


def get_text(url: str, timeout: int = 30, retries: int = 3) -> str:
    return get(url, timeout=timeout, retries=retries).decode("utf-8", "replace")
