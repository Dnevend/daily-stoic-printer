import io
import socket

import pytest

from dailyprint.printers.network import NetworkPrinter


class _FakeSock:
    def __init__(self) -> None:
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def __enter__(self) -> "_FakeSock":
        return self

    def __exit__(self, *exc) -> None:
        return None


class _FakeStdin:
    def __init__(self, calls: dict) -> None:
        self.calls = calls
        self.calls["data"] = b""

    def write(self, data: bytes) -> int:
        self.calls["data"] += data
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_send_uses_socket(monkeypatch: pytest.MonkeyPatch):
    sock = _FakeSock()
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)
    monkeypatch.setattr("dailyprint.printers.network.time.sleep", lambda s: None)

    NetworkPrinter("192.168.124.51").send(b"hi")
    assert sock.sent == b"hi"


def test_send_chunks_large_payload(monkeypatch: pytest.MonkeyPatch):
    sock = _FakeSock()
    writes: list[int] = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)
    monkeypatch.setattr("dailyprint.printers.network.time.sleep", lambda s: None)
    real_sendall = sock.sendall
    monkeypatch.setattr(
        sock, "sendall", lambda data: (writes.append(len(data)), real_sendall(data))[1]
    )

    payload = b"x" * 5000
    NetworkPrinter("192.168.124.51").send(payload)
    assert sock.sent == payload
    assert len(writes) > 1  # 不是一口气 5000 字节灌进去
    assert max(writes) <= 1024


def test_send_falls_back_to_nc(monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise OSError(65, "No route to host")

    calls = {}

    class _Proc:
        def __init__(self) -> None:
            self.stdin = _FakeStdin(calls)
            self.stderr = io.BytesIO(b"")

        def wait(self) -> int:
            return 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    def fake_popen(cmd, stdin=None, stderr=None):  # noqa: ARG001
        calls["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/nc")
    monkeypatch.setattr("dailyprint.printers.network.subprocess.Popen", fake_popen)
    monkeypatch.setattr("dailyprint.printers.network.time.sleep", lambda s: None)

    NetworkPrinter("192.168.124.51", timeout=5).send(b"hi")
    assert calls["data"] == b"hi"
    assert calls["cmd"][:2] == ["/usr/bin/nc", "-w"]
    assert calls["cmd"][-2:] == ["192.168.124.51", "9100"]


def test_send_raises_when_nc_missing(monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise OSError(65, "No route to host")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(OSError, match="No route to host"):
        NetworkPrinter("192.168.124.51").send(b"hi")
