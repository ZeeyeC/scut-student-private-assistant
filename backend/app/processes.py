"""Non-destructive process liveness on Windows and POSIX."""

import os
import sys


def windows_process_alive(pid, *, kernel=None):
    import ctypes
    from ctypes import wintypes

    if kernel is None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # SYNCHRONIZE permits a zero-timeout wait; it never signals or terminates.
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        # Access denied is not evidence that a PID is dead; preserve its lock.
        return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no PID
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        return result != 0  # WAIT_OBJECT_0 is exited, timeout/unknown is live.
    finally:
        kernel.CloseHandle(handle)


def process_alive(pid):
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
