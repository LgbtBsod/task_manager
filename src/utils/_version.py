"""
Task Manager - Version helper.

The canonical version lives in ``version.txt`` at the project / EXE root.
This module just locates and reads it, tolerating both source and frozen
(PyInstaller) layouts.
"""
import sys
from pathlib import Path


def _candidates() -> list:
    out = []
    if getattr(sys, "frozen", False):
        # Authoritative after an update.
        out.append(Path(sys.executable).resolve().parent / "version.txt")
    here = Path(__file__).resolve().parent.parent.parent  # src/ -> root / _MEIPASS
    out.append(here / "version.txt")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(Path(meipass) / "version.txt")
    return out


def get_version() -> str:
    """Return the current version string, or ``"unknown"``.

    Trims a release-tag prefix (``v``, ``v.``) so a version.txt written by an
    older updater build (which left a leading dot) still displays cleanly.
    """
    for path in _candidates():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip().lstrip("vV").strip(". \t\r\n")
                if text:
                    return text
        except Exception:
            pass
    return "unknown"

