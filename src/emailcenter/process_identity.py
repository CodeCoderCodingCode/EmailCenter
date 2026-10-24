"""Identify a local run owner without terminating or signalling Windows processes."""

import os
import socket


def process_start(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return "alive"
        except ProcessLookupError:
            return None
        except PermissionError:
            return "unknown"
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return "unknown" if ctypes.get_last_error() == 5 else None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return "unknown"
        return f"{times[0].dwHighDateTime:08x}{times[0].dwLowDateTime:08x}"
    finally:
        kernel.CloseHandle(handle)


def owner_is_alive(run):
    if run.get("owner_host") != socket.gethostname():
        return True
    actual = process_start(run.get("owner_pid"))
    return actual == "unknown" or bool(actual and actual == run.get("owner_started"))


def current_owner():
    return os.getpid(), process_start(os.getpid()), socket.gethostname()
