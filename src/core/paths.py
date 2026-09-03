"""Filesystem layout — the single place that resolves where things live.

Frozen (PyInstaller one-file): everything is next to the .exe, so user data and
logs survive an update.  From source: everything is under the repo root.

``main.py``, ``gui_flet.app``, ``utils.updater`` and ``utils._version`` all read
from here instead of each re-deriving ``sys.executable`` / ``__file__`` chains.
"""
import sys
from pathlib import Path

frozen: bool = bool(getattr(sys, "frozen", False))
meipass: Path | None = Path(sys._MEIPASS) if getattr(sys, "_MEIPASS", None) else None

if frozen:
    app_dir: Path = Path(sys.executable).resolve().parent
    exe_path: Path | None = Path(sys.executable).resolve()
else:
    app_dir = Path(__file__).resolve().parent.parent.parent   # src/core/ -> repo root
    exe_path = None

src_dir: Path = (meipass / "src") if meipass else (app_dir / "src")
data_dir: Path = app_dir / "data" / "db"
db_path: Path = data_dir / "tasks.json"
settings_path: Path = data_dir / "settings.json"
logs_dir: Path = app_dir / "logs"


def version_file_candidates() -> list[Path]:
    """Every place ``version.txt`` might be, most-authoritative first.

    ``app_dir/version.txt`` comes first for a frozen build — the updater writes
    it there after an update, while the bundled ``_MEIPASS`` copy is frozen at
    build time and must not win (it would cause an endless update loop).
    """
    out = [app_dir / "version.txt"]
    if meipass:
        out.append(meipass / "version.txt")
    return out


def read_version() -> str:
    """Current version string from ``version.txt``, or ``"unknown"``.

    Trims a release-tag prefix (``v`` / ``v.``) so a file written by an older
    updater build (which once left a leading dot) still reads cleanly.
    """
    for path in version_file_candidates():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip().lstrip("vV").strip(". \t\r\n")
                if text:
                    return text
        except OSError:
            pass
    return "unknown"


def ensure_src_on_path() -> None:
    """Put the source dir on ``sys.path`` (idempotent) so ``import core.*`` works
    both from a source checkout and a frozen bundle."""
    for candidate in ({src_dir} | ({meipass / "src"} if meipass else set())):
        s = str(candidate)
        if candidate.exists() and s not in sys.path:
            sys.path.insert(0, s)


def ensure_data_dir() -> Path:
    """Create ``data/db`` and seed an empty ``tasks.json`` on first run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.write_text("[]", encoding="utf-8")
    return data_dir
