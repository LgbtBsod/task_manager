"""Single-instance / port arbitration for the local Flet web server.

Flet's ``WEB_BROWSER`` view means the "app" is really a local server plus a
browser tab; closing the tab does not stop the server, and there is no
"window close" event tied to the process. Left alone, every relaunch could
pile up another orphaned server. So instead of trying to detect and reuse a
still-healthy instance (fragile — a slow health probe reads as "not ours" and
falls through to spawning yet another one, which is how orphans piled up),
``run_app`` calls :func:`resolve_port` once at startup and it unconditionally
terminates anything already on our port before serving: at most one instance
of this app ever holds the port. Only processes recognisable as this app
(``TaskManager.exe`` or a Python running ``main.py`` / ``task_manager``) are
ever killed.
"""
import socket
import subprocess
import sys
import time

from core import strings as L

_PORT_SCAN_SPAN = 40


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


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


def resolve_port(port: int) -> int:
    """See the module docstring: always end up the sole instance on ``port``."""
    if port_is_free(port):
        return port

    # Something (healthy or hung, doesn't matter) is on our port -> it's an
    # earlier instance of us; take the port back.
    _kill_stale_on_port(port)
    for _ in range(15):                       # up to ~3s for the OS to release it
        if port_is_free(port):
            return port
        time.sleep(0.2)

    # Kill didn't free it in time (or it's a foreign process) -> next free port.
    for cand in range(port + 1, port + _PORT_SCAN_SPAN):
        if port_is_free(cand):
            print(L.APP.PORT_BUSY.format(port=port, alt=cand))
            return cand
    return port
