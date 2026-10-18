"""打印机注册表。"""

from __future__ import annotations

from ..config import PrinterConfig
from .base import Printer
from .cups import CupsPrinter
from .network import NetworkPrinter

TYPES: dict[str, type[Printer]] = {
    "network": NetworkPrinter,
    "cups": CupsPrinter,
}

__all__ = ["Printer", "NetworkPrinter", "CupsPrinter", "TYPES", "build_printer"]


def build_printer(cfg: PrinterConfig) -> Printer:
    if cfg.ip:
        return NetworkPrinter(cfg.ip, port=cfg.port)
    if cfg.queue:
        return CupsPrinter(cfg.queue)
    if cfg.kind == "cups":
        return CupsPrinter(cfg.queue)
    raise ValueError("未配置打印机：请在 config.toml 里设置 printer.ip 或 printer.queue")
