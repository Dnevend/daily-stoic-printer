"""网络打印机：直接把 ESC/POS 字节流发到 9100 端口（免驱动）。"""

from __future__ import annotations

import socket

from .base import Printer


class NetworkPrinter(Printer):
    kind = "network"

    def __init__(self, ip: str, port: int = 9100, timeout: float = 5.0) -> None:
        if not ip:
            raise ValueError("网络打印机需要 ip")
        self.ip = ip
        self.port = port
        self.timeout = timeout

    def send(self, data: bytes) -> None:
        with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
            sock.sendall(data)

    def __repr__(self) -> str:
        return f"<NetworkPrinter {self.ip}:{self.port}>"
