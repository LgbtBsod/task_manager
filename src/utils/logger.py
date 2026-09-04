"""Logging setup: console + rotating files.

    from utils.logger import setup_logging, get_logger
    setup_logging("/path/to/app")     # once, at startup
    log = get_logger(__name__)

The uncaught-exception hook is a separate concern — ``utils.error_handler``
owns it (``main`` installs it right after ``setup_logging``).
"""
import logging
import logging.handlers
import sys
from pathlib import Path

# Until setup_logging() runs, still surface WARNING+ on stderr.
logging.basicConfig(handlers=[logging.StreamHandler(sys.stderr)], level=logging.WARNING)

_CONSOLE_FMT = logging.Formatter("%(asctime)s %(levelname)-5s %(name)-20s %(message)s",
                                 datefmt="%H:%M:%S")
_FILE_FMT = logging.Formatter("%(asctime)s %(levelname)-8s %(name)-25s %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")

# (filename, level, backup count) — app.log is the firehose, error.log the tail.
_FILES = (("app.log", logging.DEBUG, 5), ("error.log", logging.ERROR, 3))


def setup_logging(app_dir: str = ".") -> Path:
    """Wire the root logger: console at INFO, ``logs/app.log`` at DEBUG,
    ``logs/error.log`` at ERROR (both rotating, 1 MB × N). Returns the logs dir.
    """
    logs_dir = Path(app_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_CONSOLE_FMT)
    root.addHandler(console)

    for name, level, backups in _FILES:
        handler = logging.handlers.RotatingFileHandler(
            logs_dir / name, maxBytes=1_000_000, backupCount=backups, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(_FILE_FMT)
        root.addHandler(handler)

    logging.getLogger("logger").info("Logging initialized -> %s", logs_dir)
    return logs_dir


def get_logger(name: str) -> logging.Logger:
    """``logging.getLogger`` — the project's single import point for loggers."""
    return logging.getLogger(name)


__all__ = ["setup_logging", "get_logger"]
