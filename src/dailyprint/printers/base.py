"""打印机基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Printer(ABC):
    """把 ESC/POS 字节流送到打印机。"""

    kind = "printer"

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
