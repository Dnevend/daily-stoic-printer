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
    translation: bool = True  # 是否打印中文译文（需要联网，且打印机支持中文）
    images: str = "content"  # off | content（跳过推广图）| all
    max_images: int = 2  # 最多打印几张配图
    max_image_height: int = 400  # 位图最大高度（dots，越小越省纸）


@dataclass
class CoverConfig:
    source: str = "wikimedia"  # wikimedia | picsum | local | none
    keywords: tuple[str, ...] = (
        "marcus aurelius bust",
        "seneca statue",
        "epictetus",
        "stoicism",
    )
    local_path: str = ""
    width: int = 576
    height: int = 320
    credit: bool = True  # 是否打印图片来源/许可


@dataclass
class TranslationConfig:
    target: str = "zh-CN"
    providers: tuple[str, ...] = ("mymemory", "google")
    email: str = ""  # MyMemory 可选邮箱，可提高每日额度


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
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def translation_cache(self) -> Path:
        return self.cache / "translate"

    @property
    def image_cache(self) -> Path:
        return self.cache / "images"

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
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    cover: CoverConfig = field(default_factory=CoverConfig)
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
        cfg.render = _dataclass_from(RenderConfig, cfg.render, kw, "defaults")
    if "render" in data:
        cfg.render = _dataclass_from(RenderConfig, cfg.render, data["render"], "render")
    if "translation" in data:
        cfg.translation = _dataclass_from(
            TranslationConfig, cfg.translation, data["translation"], "translation"
        )
    if "cover" in data:
        cfg.cover = _dataclass_from(CoverConfig, cfg.cover, data["cover"], "cover")
    if "printer" in data:
        cfg.printer = _dataclass_from(PrinterConfig, cfg.printer, data["printer"], "printer")
    if "paths" in data and data["paths"].get("home"):
        cfg.paths = Paths(Path(data["paths"]["home"]).expanduser())
    if "sources" in data:
        cfg.sources = _merge(cfg.sources, data["sources"])


def _dataclass_from(cls, current, over: dict, section: str):
    """用配置覆盖 dataclass；键名不认识时报出具体是哪个。"""
    over = dict(over)
    unknown = sorted(set(over) - set(cls.__dataclass_fields__))
    if unknown:
        raise ValueError(
            f"config.toml 的 [{section}] 里有无法识别的配置项: {', '.join(unknown)}"
        )
    # TOML 的数组在 Python 里是 list，转成 tuple 保持 dataclass 不可变
    for key, value in over.items():
        if isinstance(value, list) and isinstance(current.__dict__.get(key), tuple):
            over[key] = tuple(value)
    return cls(**{**current.__dict__, **over})


def _render_config(current: RenderConfig, over: dict) -> RenderConfig:  # 兼容旧调用
    return _dataclass_from(RenderConfig, current, over, "render")
