"""CUPS 队列打印机：通过 ``lp -o raw`` 发送（USB 打印机走这条路）。"""

from __future__ import annotations

import subprocess

from .base import Printer


class CupsPrinter(Printer):
    kind = "cups"

    def __init__(self, queue: str) -> None:
        if not queue:
            raise ValueError("CUPS 打印机需要 queue（队列名）")
        self.queue = queue

    def send(self, data: bytes) -> None:
        proc = subprocess.run(
            ["lp", "-d", self.queue, "-o", "raw"],
            input=data,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"lp 失败: {proc.stderr.decode().strip()}")

    def __repr__(self) -> str:
        return f"<CupsPrinter {self.queue}>"
