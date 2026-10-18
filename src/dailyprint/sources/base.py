"""来源基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Article


class Source(ABC):
    """内容来源：返回最新的若干篇文章。"""

    name: str = "source"

    def __init__(self, name: str = "", **_: object) -> None:
        if name:
            self.name = name

    @abstractmethod
    def latest(self, count: int = 1) -> list[Article]:
        """返回最新的 ``count`` 篇文章（新 -> 旧）。"""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
