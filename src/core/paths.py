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

    For a frozen build the bundled ``_MEIPASS/version.txt`` is authoritative:
    it ships *inside* the running binary, so it is always the true version of
    the code that is executing — even if a self-update swapped the .exe but a
    stale ``app_dir/version.txt`` was left behind, or vice-versa. From source
    there is only the repo-root file.
    """
    out: list[Path] = []
    if meipass:
        out.append(meipass / "version.txt")
    out.append(app_dir / "version.txt")
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


def sync_version_file() -> None:
    """Frozen only: mirror the bundled ``_MEIPASS/version.txt`` to
    ``app_dir/version.txt`` so external tools (and the atom-feed update check)
    see the version of the binary that is actually running. The updater never
    writes ``app_dir/version.txt`` itself, so this is the single writer.
    """
    if not (frozen and meipass):
        return
    src, dst = meipass / "version.txt", app_dir / "version.txt"
    try:
        want = src.read_text(encoding="utf-8")
        if not dst.is_file() or dst.read_text(encoding="utf-8") != want:
            dst.write_text(want, encoding="utf-8")
    except OSError:
        pass


def ensure_data_dir() -> Path:
    """Create ``data/db`` and seed an empty ``tasks.json`` on first run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.write_text("[]", encoding="utf-8")
    return data_dir


def open_in_file_manager(path: Path | str) -> bool:
    """Reveal ``path`` in the OS file manager. Returns whether the call was
    dispatched (not whether a window actually appeared)."""
    import subprocess

    target = str(path)
    match sys.platform:
        case "win32":
            argv = ["explorer.exe", target]
        case "darwin":
            argv = ["open", target]
        case _:
            argv = ["xdg-open", target]
    try:
        subprocess.Popen(argv)
        return True
    except OSError:
        return False
