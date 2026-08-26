"""
Task Manager - Logging System
Provides file + console logging with crash dump on unhandled exceptions.

Features:
- Console handler: INFO+ with colored output
- File handler: DEBUG+ rotating logs/app.log (1 MB, 5 backups)
- Error dump: On crash, writes full traceback to logs/error.log + logs/crash_*.log
- Uncaught exception hook installed at setup()

Usage:
    from utils.logger import setup_logging, get_logger
    setup_logging('/path/to/project')
    log = get_logger(__name__)
    log.info('App started')
"""
import logging
import logging.handlers
import sys
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional


# Module-level logger (works even before setup_logging is called)
_default_handler = logging.StreamHandler(sys.stderr)
_default_handler.setLevel(logging.WARNING)
logging.basicConfig(handlers=[_default_handler], level=logging.WARNING)


def setup_logging(app_dir: str = ".") -> Path:
    """Initialize logging with console + file handlers.
    
    Args:
        app_dir: Application root directory. Logs go to {app_dir}/logs/
    
    Returns:
        Path to the logs directory
    """
    app_path = Path(app_dir)
    logs_dir = app_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove default handlers
    root_logger.handlers.clear()
    
    # ── Console Handler (INFO+) ──
    console_fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)-20s %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)
    
    # ── File Handler (DEBUG+, rotating 1 MB, 5 backups) ──
    app_log = logs_dir / "app.log"
    file_fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)-25s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        str(app_log), maxBytes=1_000_000, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)
    
    # ── Error-only file handler ──
    error_log = logs_dir / "error.log"
    error_handler = logging.handlers.RotatingFileHandler(
        str(error_log), maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_fmt)
    root_logger.addHandler(error_handler)
    
    # ── Install uncaught exception hook ──
    sys.excepthook = _crash_dump_handler
    
    log = logging.getLogger("logger")
    log.info(f"Logging initialized. Logs dir: {logs_dir}")
    log.info(f"App log: {app_log}")
    log.info(f"Error log: {error_log}")
    
    return logs_dir


def _crash_dump_handler(exc_type, exc_value, exc_traceback):
    """Global exception hook — writes full crash dump to logs/crash_*.log."""
    log = logging.getLogger("crash")
    
    # Full traceback as text
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = "".join(tb_lines)
    
    # Log to root logger (goes to error.log + console)
    log.critical("\n" + "=" * 60)
    log.critical("UNCAUGHT EXCEPTION — CRASH DUMP")
    log.critical("=" * 60)
    for line in tb_lines:
        log.critical(line.rstrip())
    log.critical("=" * 60 + "\n")
    
    # Write standalone crash dump file
    try:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        crash_filename = f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        crash_path = logs_dir / crash_filename
        
        with open(crash_path, "w", encoding="utf-8") as f:
            f.write(f"CRASH DUMP — {datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"CWD: {os.getcwd()}\n")
            f.write(f"argv: {sys.argv}\n")
            f.write("\n--- TRACEBACK ---\n")
            f.write(tb_text)
            f.write("\n--- ENVIRONMENT ---\n")
            try:
                import platform
                f.write(f"OS: {platform.system()} {platform.release()}\n")
                f.write(f"Architecture: {platform.machine()}\n")
                f.write(f"Python version: {platform.python_version()}\n")
            except Exception:
                f.write("(env info unavailable)\n")
            f.write("\n--- LOCALS (top frame) ---\n")
            if exc_traceback:
                frame = exc_traceback.tb_frame
                while frame.tb_next:
                    frame = frame.tb_next
                locals_str = ""
                for name, val in (frame.tb_frame.f_locals or {}).items():
                    try:
                        val_str = repr(val)
                        if len(val_str) > 500:
                            val_str = val_str[:500] + "... (truncated)"
                        locals_str += f"  {name} = {val_str}\n"
                    except Exception:
                        locals_str += f"  {name} = <error repr>\n"
                f.write(locals_str)
        
        log.error(f"Crash dump saved: {crash_path}")
    except Exception as dump_err:
        log.error(f"Failed to write crash dump file: {dump_err}")
    
    # Also call the default handler so the process still terminates
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        logging.Logger instance
    """
    return logging.getLogger(name)


__all__ = ["setup_logging", "get_logger"]
