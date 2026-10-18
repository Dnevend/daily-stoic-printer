"""配置加载：``config.toml`` + 环境变量覆盖。

优先级（低 -> 高）：内置默认值 < config.toml < 环境变量 < 命令行参数。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .sources import DEFAULT_SOURCES

ENV_HOME = "DAILYPRINT_HOME"
ENV_SOURCE = "DAILYPRINT_SOURCE"
ENV_PRINTER_IP = "DAILYPRINT_PRINTER_IP"


def project_root() -> Path:
    """从包位置向上寻找 pyproject.toml；找不到则用当前目录。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@dataclass
class RenderConfig:
    width: int = 48
    words: int = 8
    common: int = 6000
    chinese: bool = True
    vocab: bool = True
    count: int = 1  # 一次取几篇（默认最新一篇）
    max_words: int = 900  # 打印时正文最多保留多少词（0 = 不限制）
    filter_promos: bool = True  # 过滤正文里的推广/CTA 段落
    promo_phrases: tuple[str, ...] = ()  # 追加的促销短语


@dataclass
class PrinterConfig:
    kind: str = "network"  # network | cups
    ip: str = ""
    port: int = 9100
    queue: str = ""
    cut: bool = True


@dataclass
class Paths:
    home: Path

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def articles(self) -> Path:
        return self.home / "articles"

    @property
    def prints(self) -> Path:
        return self.home / "prints"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def wordfreq(self) -> Path:
        return self.data / "wordfreq.txt"

    @property
    def dictionary(self) -> Path:
        return self.data / "dict.tsv"


@dataclass
class AppConfig:
    source: str = "daily-stoic"
    render: RenderConfig = field(default_factory=RenderConfig)
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    paths: Paths = field(default_factory=lambda: Paths(project_root()))
    sources: dict[str, dict] = field(default_factory=lambda: dict(DEFAULT_SOURCES))
    config_path: Path | None = None

    def source_spec(self, name: str | None = None) -> dict:
        name = name or self.source
        if name not in self.sources:
            raise KeyError(
                f"未知来源 {name!r}；可用：{', '.join(sorted(self.sources))}"
            )
        return {"name": name, **self.sources[name]}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    out.update(over or {})
    return out


def load_config(path: Path | str | None = None) -> AppConfig:
    """读取配置。``path`` 为空时依次找 ``config.toml``、``config.json``。"""
    cfg = AppConfig()

    candidates: list[Path] = []
    if path:
        candidates.append(Path(path).expanduser())
    else:
        root = project_root()
        candidates += [root / "config.toml", root / "config.json"]

    for candidate in candidates:
        if candidate.exists():
            with candidate.open("rb") as f:
                data = tomllib.load(f)
            cfg.config_path = candidate
            _apply(cfg, data)
            break

    # 环境变量覆盖
    if os.environ.get(ENV_HOME):
        cfg.paths = Paths(Path(os.environ[ENV_HOME]).expanduser())
    if os.environ.get(ENV_SOURCE):
        cfg.source = os.environ[ENV_SOURCE]
    if os.environ.get(ENV_PRINTER_IP):
        cfg.printer.kind = "network"
        cfg.printer.ip = os.environ[ENV_PRINTER_IP]
    return cfg


def _apply(cfg: AppConfig, data: dict) -> None:
    if "defaults" in data:
        d = data["defaults"]
        if "source" in d:
            cfg.source = d["source"]
        kw = {k: v for k, v in d.items() if k in RenderConfig.__dataclass_fields__}
        cfg.render = _render_config(cfg.render, kw)
    if "render" in data:
        cfg.render = _render_config(cfg.render, data["render"])
    if "printer" in data:
        cfg.printer = PrinterConfig(**{**cfg.printer.__dict__, **data["printer"]})
    if "paths" in data and data["paths"].get("home"):
        cfg.paths = Paths(Path(data["paths"]["home"]).expanduser())
    if "sources" in data:
        cfg.sources = _merge(cfg.sources, data["sources"])


def _render_config(current: RenderConfig, over: dict) -> RenderConfig:
    over = dict(over)
    if isinstance(over.get("promo_phrases"), list):
        over["promo_phrases"] = tuple(over["promo_phrases"])
    return RenderConfig(**{**current.__dict__, **over})
