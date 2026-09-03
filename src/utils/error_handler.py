"""Task Manager - Enhanced Error Handler

Provides crash-safe error logging with full context dump.
Installed as the global exception hook so ANY unhandled error
in the app (GUI, service, repo) produces a readable error_log.txt.

Features:
- Writes to logs/error_log.txt with append mode
- Includes: timestamp, Python version, OS, CWD, argv, GUI mode
- Full traceback with chain of causes
- Locals from the deepest frame (truncated for safety)
- Installed modules list (for dependency issues)
- Task manager context: task count, DB path, last operation
- Separate crash_*.log files per incident
- stderr fallback if file write fails

Usage:
    from utils.error_handler import install_error_handler, ErrorContext
    install_error_handler(app_dir="/path/to/project")
    # Now any unhandled exception -> logs/error_log.txt + logs/crash_*.log
"""
import sys
import os
import traceback
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class ErrorContext:
    """Global error context — stores app state for crash dumps."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._data = {}
            return cls._instance

    def set(self, key: str, value: str):
        self._data[key] = value

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def to_dict(self) -> dict:
        return dict(self._data)

    def clear(self):
        self._data.clear()


def install_error_handler(app_dir: str = ".") -> Path:
    """Install the global exception hook and return the logs directory.

    Args:
        app_dir: Application root directory.

    Returns:
        Path to the logs directory.
    """
    logs_dir = Path(app_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _LOGS_DIR[0] = logs_dir
    sys.excepthook = _enhanced_crash_handler
    return logs_dir


_LOGS_DIR: list = [Path("logs")]  # mutable default for closure


def write_error_log(
    error_msg: str,
    app_dir: Optional[str] = None,
    context: Optional[dict] = None,
) -> Path:
    """Manually write an error to the error log.

    Args:
        error_msg: Human-readable error message.
        app_dir: App root (uses _LOGS_DIR if None).
        context: Extra key-value context to include.

    Returns:
        Path to the written error log file.
    """
    if app_dir:
        logs_dir = Path(app_dir) / "logs"
    else:
        logs_dir = _LOGS_DIR[0]
    logs_dir.mkdir(parents=True, exist_ok=True)

    error_log_path = logs_dir / "error_log.txt"
    ts = datetime.now().isoformat()

    try:
        import platform
        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    except Exception:
        os_info = "unknown"

    lines = [
        f"\n{'=' * 70}",
        f"ERROR LOG — {ts}",
        f"{'=' * 70}",
        f"Python:    {sys.version}",
        f"Platform:  {sys.platform} — {os_info}",
        f"CWD:       {os.getcwd()}",
        f"argv:      {sys.argv}",
    ]

    # Add ErrorContext
    try:
        ec = ErrorContext()
        ec_data = ec.to_dict()
        if ec_data:
            lines.append(f"\n--- APP CONTEXT ---")
            for k, v in ec_data.items():
                lines.append(f"  {k}: {v}")
    except Exception:
        pass

    # Add extra context
    if context:
        lines.append(f"\n--- EXTRA CONTEXT ---")
        for k, v in context.items():
            val_str = str(v)[:500]
            lines.append(f"  {k}: {val_str}")

    lines.append(f"\n--- ERROR ---")
    lines.append(f"  {error_msg}")
    lines.append(f"\n--- TRACEBACK ---")
    lines.append(traceback.format_exc())

    # Installed modules (useful for dependency issues)
    try:
        lines.append(f"\n--- INSTALLED MODULES ---")
        modules = sorted([m for m in sys.modules if not m.startswith('_')])
        lines.append(f"  ({len(modules)} modules loaded)")
        for m in modules[-30:]:  # last 30 modules
            lines.append(f"  - {m}")
    except Exception:
        pass

    content = "\n".join(lines) + "\n"

    try:
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        # Fallback to stderr
        sys.stderr.write(content)

    return error_log_path


def _enhanced_crash_handler(exc_type, exc_value, exc_traceback):
    """Global uncaught exception hook — writes to error_log.txt + crash_*.log."""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = "".join(tb_lines)
    logs_dir = _LOGS_DIR[0]
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()

    # ── 1. Append to error_log.txt ──
    error_log_path = logs_dir / "error_log.txt"
    try:
        import platform
        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    except Exception:
        os_info = "unknown"

    log_lines = [
        f"\n{'=' * 70}",
        f"CRASH — {ts.isoformat()}",
        f"{'=' * 70}",
        f"Exception: {exc_type.__name__}: {exc_value}",
        f"Python:    {sys.version}",
        f"Platform:  {sys.platform} — {os_info}",
        f"CWD:       {os.getcwd()}",
        f"argv:      {sys.argv}",
    ]

    # ErrorContext
    try:
        ec = ErrorContext()
        ec_data = ec.to_dict()
        if ec_data:
            log_lines.append(f"\n--- APP CONTEXT ---")
            for k, v in ec_data.items():
                log_lines.append(f"  {k}: {v}")
    except Exception:
        pass

    log_lines.append(f"\n--- TRACEBACK ---")
    log_lines.extend(tb_lines)

    # Locals from deepest frame
    if exc_traceback:
        try:
            frame = exc_traceback
            while frame.tb_next:
                frame = frame.tb_next
            log_lines.append(f"\n--- LOCALS (deepest frame: {frame.tb_frame.f_code.co_name}) ---")
            for name, val in (frame.tb_frame.f_locals or {}).items():
                try:
                    val_str = repr(val)
                    if len(val_str) > 500:
                        val_str = val_str[:500] + "... (truncated)"
                    log_lines.append(f"  {name} = {val_str}")
                except Exception:
                    log_lines.append(f"  {name} = <error repr>")
        except Exception:
            pass

    # Installed modules
    try:
        log_lines.append(f"\n--- MODULES ({len(sys.modules)} loaded) ---")
        key_modules = [m for m in sorted(sys.modules) if m in (
            'flet', 'flet_web', 'pydantic', 'pydantic_core',
            'uvicorn', 'fastapi',
        )]
        for m in key_modules:
            mod = sys.modules[m]
            ver = getattr(mod, '__version__', 'unknown')
            log_lines.append(f"  {m} == {ver}")
    except Exception:
        pass

    # Thread info
    try:
        log_lines.append(f"\n--- THREADS ---")
        for t in threading.enumerate():
            log_lines.append(f"  {t.name} (daemon={t.daemon}, alive={t.is_alive()})")
    except Exception:
        pass

    content = "\n".join(log_lines) + "\n"
    try:
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write(content)
        # Also print to stderr so user sees something
        sys.stderr.write(f"\n[CRASH] Error log written to: {error_log_path}\n")
    except Exception:
        sys.stderr.write(content)

    # ── 2. Write per-crash file ──
    crash_filename = f"crash_{ts.strftime('%Y%m%d_%H%M%S')}.log"
    crash_path = logs_dir / crash_filename
    try:
        with open(crash_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    # Call the original handler
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


__all__ = ['install_error_handler', 'write_error_log', 'ErrorContext']
