"""来源注册表：按配置里的 ``type`` 构造来源实例。

新增来源只需：
    1. 在 ``sources/`` 下写一个继承 ``Source`` 的类
    2. 在 ``TYPES`` 里注册
    3. 在 ``config.toml`` 的 ``[sources.<名字>]`` 里写 ``type``
"""

from __future__ import annotations

from .base import Source
from .daily_stoic import DailyStoicSource
from .rss import RssSource

TYPES: dict[str, type[Source]] = {
    "daily_stoic": DailyStoicSource,
    "rss": RssSource,
}

# 开箱可用的来源（config.toml 中 [sources.*] 会覆盖/追加）
DEFAULT_SOURCES: dict[str, dict] = {
    "daily-stoic": {"type": "daily_stoic", "base_url": "https://dailystoic.com"},
}

__all__ = ["Source", "DailyStoicSource", "RssSource", "TYPES", "DEFAULT_SOURCES", "build_source"]


def build_source(name: str, spec: dict) -> Source:
    spec = dict(spec)
    kind = spec.pop("type", None)
    if not kind:
        raise ValueError(f"来源 {name!r} 缺少 type")
    if kind not in TYPES:
        raise ValueError(f"未知来源类型 {kind!r}；可用：{', '.join(sorted(TYPES))}")
    return TYPES[kind](name=name, **spec)


def available_types() -> list[str]:
    return sorted(TYPES)
