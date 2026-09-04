"""Single-instance / port arbitration for the local Flet web server.

``run_app`` calls :func:`resolve_port` once at startup. The rules, in order:

1. Port free                    -> serve on it.
2. A healthy instance of *this* app already serving there
                                -> open a browser tab at it, return ``None``
                                   (the caller should just exit).
3. A hung / orphaned instance of *ours* holding the port
                                -> kill it, serve on the now-free port.
4. A foreign process holding it -> serve on the next free port.

Only processes recognisable as this app (``TaskManager.exe`` or a Python
running ``main.py`` / ``task_manager``) are ever killed.
"""
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

from core import strings as L

_PROBE_TIMEOUT = 2.0
_PORT_SCAN_SPAN = 40


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _healthy_instance_serving(port: int) -> bool:
    """Is the thing on ``port`` a live Flet/Flutter app (i.e. us)?"""
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/", timeout=_PROBE_TIMEOUT
        ).read(4096)
    except Exception:
        return False
    return b"flutter" in body.lower() or b"flet" in body.lower()


def _pids_listening_on(port: int) -> list[int]:
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue "
             "| Select-Object -Expand OwningProcess -Unique"],
            capture_output=True, text=True, timeout=8,
        ).stdout
    except Exception:
        return []
    pids = []
    for line in out.split():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            pass
    return pids


def _looks_like_our_process(pid: int) -> bool:
    try:
        info = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}';"
             "\"$($p.Name)|$($p.CommandLine)\""],
            capture_output=True, text=True, timeout=8,
        ).stdout.lower()
    except Exception:
        info = ""
    return ("taskmanager.exe" in info
            or ("python" in info and ("main.py" in info or "task_manager" in info)))


def _kill_stale_on_port(port: int) -> None:
    """Terminate a previous instance of *this app* holding the port. Never
    touches unrelated processes."""
    import os
    me = os.getpid()
    for pid in _pids_listening_on(port):
        if pid == me or not _looks_like_our_process(pid):
            continue
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Stop-Process -Id {pid} -Force -EA SilentlyContinue"],
                capture_output=True, timeout=8,
            )
            print(L.APP.KILLED_STALE.format(pid=pid, port=port))
        except Exception:
            pass


def resolve_port(port: int) -> int | None:
    """See the module docstring. ``None`` means "an instance is already running,
    a browser tab was opened, just exit"."""
    if port_is_free(port):
        return port

    if _healthy_instance_serving(port):
        webbrowser.open(f"http://127.0.0.1:{port}/")
        print(L.APP.ALREADY_RUNNING.format(port=port))
        return None

    # Busy but not answering -> a hung old instance of ours.
    _kill_stale_on_port(port)
    for _ in range(15):                       # up to ~3s for the OS to release it
        if port_is_free(port):
            return port
        time.sleep(0.2)

    # Still busy -> a foreign process. Take the next free port.
    for cand in range(port + 1, port + _PORT_SCAN_SPAN):
        if port_is_free(cand):
            print(L.APP.PORT_BUSY.format(port=port, alt=cand))
            return cand
    return port
