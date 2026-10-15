import os

from app import processes


def test_windows_liveness_never_uses_posix_signal(monkeypatch):
    monkeypatch.setattr(processes.sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(
        processes, "windows_process_alive", lambda pid: calls.append(pid) or True
    )
    monkeypatch.setattr(
        os,
        "kill",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("Windows signal would terminate the process")
        ),
    )
    assert processes.process_alive(12345)
    assert calls == [12345]
    assert not processes.process_alive(0)


def test_windows_query_closes_handle_and_never_terminates_process():
    class Function:
        def __init__(self, result):
            self.result = result

        def __call__(self, *args):
            return self.result(*args) if callable(self.result) else self.result

    class Kernel:
        OpenProcess = Function(42)
        WaitForSingleObject = Function(0x102)
        CloseHandle = Function(1)

    kernel = Kernel()
    closed = []
    kernel.CloseHandle = Function(lambda handle: closed.append(handle) or 1)
    assert processes.windows_process_alive(999, kernel=kernel)
    assert closed == [42]
    kernel.WaitForSingleObject = Function(0)
    assert not processes.windows_process_alive(999, kernel=kernel)
    assert closed == [42, 42]
