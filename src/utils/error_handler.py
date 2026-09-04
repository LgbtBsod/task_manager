"""Crash-safe error reporting.

``install_error_handler(app_dir)`` points ``sys.excepthook`` at a handler that
writes a full, human-readable report — context, traceback, deepest-frame
locals, loaded libraries, live threads — to ``logs/error_log.txt`` and to a
per-incident ``logs/crash_<timestamp>.log``.

``write_error_log(msg, context=...)`` writes the same shape for an exception
you caught yourself.

``ErrorContext().set("db_path", ...)`` stashes app state that every subsequent
report includes. All instances share one process-global store.

    from utils.error_handler import install_error_handler, ErrorContext
    install_error_handler("/path/to/app")
    ErrorContext().set("app_dir", "/path/to/app")
"""
import logging
import os
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

_log = logging.getLogger("crash")
_RULE = "=" * 70

# Set by install_error_handler(); write_error_log() falls back to it.
_logs_dir: Path = Path("logs")
# Shared app-state store behind every ErrorContext() instance.
_context: dict[str, str] = {}


class ErrorContext:
    """Key/value app state folded into every crash report. Constructing it
    anywhere reaches the same process-global store."""

    def set(self, key: str, value: object) -> None:
        _context[key] = str(value)

    def get(self, key: str, default: str = "") -> str:
        return _context.get(key, default)

    def to_dict(self) -> dict:
        return dict(_context)

    def clear(self) -> None:
        _context.clear()


def install_error_handler(app_dir: str = ".") -> Path:
    """Install the global exception hook; return the logs directory."""
    global _logs_dir
    _logs_dir = Path(app_dir) / "logs"
    _logs_dir.mkdir(parents=True, exist_ok=True)
    sys.excepthook = _crash_handler
    return _logs_dir


def write_error_log(error_msg: str, app_dir: str | None = None,
                    context: dict | None = None) -> Path:
    """Append a full report for a caught exception. Returns the log path."""
    logs_dir = (Path(app_dir) / "logs") if app_dir else _logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    report = _build_report("ERROR LOG", error_msg, sys.exc_info(), extra=context)
    path = logs_dir / "error_log.txt"
    _write(path, report, "a")
    return path


def _crash_handler(exc_type, exc_value, exc_tb) -> None:
    """``sys.excepthook``: full dump to error_log.txt + a per-incident file."""
    _logs_dir.mkdir(parents=True, exist_ok=True)
    report = _build_report("CRASH", f"{exc_type.__name__}: {exc_value}",
                           (exc_type, exc_value, exc_tb), deep=True)
    _write(_logs_dir / "error_log.txt", report, "a")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _write(_logs_dir / f"crash_{stamp}.log", report, "w")
    # A one-liner through logging so the crash is greppable in error.log; the
    # full traceback still goes to stderr via the default hook below, and the
    # structured dump is in error_log.txt / crash_*.log.
    try:
        _log.critical("uncaught %s: %s — see %s", exc_type.__name__, exc_value,
                      _logs_dir / "error_log.txt")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


# ── report building (the one place it happens) ────────────────────────

def _build_report(title: str, error_msg: str, exc_info, *,
                  extra: dict | None = None, deep: bool = False) -> str:
    lines = [
        "", _RULE, f"{title} — {datetime.now().isoformat()}", _RULE,
        f"Python:    {sys.version}",
        f"Platform:  {sys.platform} — {platform.system()} {platform.release()} "
        f"({platform.machine()})",
        f"CWD:       {os.getcwd()}",
        f"argv:      {sys.argv}",
    ]
    lines += _section("APP CONTEXT", (f"{k}: {v}" for k, v in _context.items())) if _context else []
    if extra:
        lines += _section("EXTRA CONTEXT", (f"{k}: {str(v)[:500]}" for k, v in extra.items()))

    lines += ["", "--- ERROR ---", f"  {error_msg}"]

    exc_type = exc_info[0] if exc_info else None
    lines += ["", "--- TRACEBACK ---"]
    if exc_type is not None:
        lines.append("".join(traceback.format_exception(*exc_info)).rstrip())
    else:
        lines.append("  (no active exception)")

    if deep:
        lines += _deepest_locals(exc_info[2] if exc_info else None)
        lines += _section("MODULES", _key_library_versions(),
                          header=f"MODULES ({len(sys.modules)} loaded)")
        lines += _section("THREADS", (
            f"{t.name} (daemon={t.daemon}, alive={t.is_alive()})"
            for t in threading.enumerate()))
    return "\n".join(lines) + "\n"


def _section(name: str, items, *, header: str | None = None) -> list[str]:
    return ["", f"--- {header or name} ---", *(f"  {it}" for it in items)]


def _deepest_locals(tb) -> list[str]:
    if tb is None:
        return []
    while tb.tb_next:
        tb = tb.tb_next
    frame = tb.tb_frame
    rows = []
    for name, val in (frame.f_locals or {}).items():
        try:
            text = repr(val)
        except Exception:
            text = "<unreprable>"
        rows.append(f"{name} = {text[:500]}{'... (truncated)' if len(text) > 500 else ''}")
    return _section("LOCALS", rows,
                    header=f"LOCALS (deepest frame: {frame.f_code.co_name})")


def _key_library_versions():
    names = ("flet", "flet_web", "pydantic", "pydantic_core", "packaging",
             "uvicorn", "fastapi")
    for name in names:
        mod = sys.modules.get(name)
        if mod is not None:
            yield f"{name} == {getattr(mod, '__version__', 'unknown')}"


def _write(path: Path, text: str, mode: str) -> None:
    try:
        with open(path, mode, encoding="utf-8") as f:
            f.write(text)
    except OSError:
        try:
            sys.stderr.write(text)
        except Exception:
            pass


__all__ = ["install_error_handler", "write_error_log", "ErrorContext"]
