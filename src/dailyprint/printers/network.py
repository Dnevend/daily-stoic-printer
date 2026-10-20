"""网络打印机：直接把 ESC/POS 字节流发到 9100 端口（免驱动）。"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import time

from .base import Printer

log = logging.getLogger(__name__)

CHUNK = 1024  # 热敏机接收缓冲很小，分块发，别一口气灌
PAUSE = 0.02  # 每秒约 50KB，给打印机留出解析和打印的时间


class NetworkPrinter(Printer):
    kind = "network"

    def __init__(self, ip: str, port: int = 9100, timeout: float = 5.0) -> None:
        if not ip:
            raise ValueError("网络打印机需要 ip")
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.nc = shutil.which("nc")

    def send(self, data: bytes) -> None:
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        except OSError as exc:
            # macOS 的「本地网络」隐私会静默拒绝未系统签名的进程：手动跑没问题，
            # 但 launchd 里的 Python 会拿到 EHOSTUNREACH。系统自带的 nc 不受限制。
            if not self._send_via_nc(data, exc):
                raise
            return

        with sock:
            for i in range(0, len(data), CHUNK):
                sock.sendall(data[i : i + CHUNK])
                time.sleep(PAUSE)
            # 慢一点断开，免得打印机还没收完就被 FIN 打断
            time.sleep(0.2)

    def _send_via_nc(self, data: bytes, cause: OSError) -> bool:
        """改用 ``nc`` 发送；成功返回 True，失败返回 False（由调用方抛原异常）。"""
        if not self.nc:
            return False
        cmd = [self.nc, "-w", str(max(1, int(self.timeout))), self.ip, str(self.port)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            assert proc.stdin is not None
            try:
                for i in range(0, len(data), CHUNK):
                    proc.stdin.write(data[i : i + CHUNK])
                    proc.stdin.flush()
                    time.sleep(PAUSE)
                proc.stdin.close()
            except BrokenPipeError:
                pass
            err = proc.stderr.read() if proc.stderr else b""
            code = proc.wait()
        if code != 0:
            log.warning("nc 回退失败: %s", err.decode(errors="replace").strip())
            return False
        log.info("直连失败（%s），已改用 nc 发送", cause)
        return True

    def __repr__(self) -> str:
        return f"<NetworkPrinter {self.ip}:{self.port}>"
