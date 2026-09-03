"""
Task Manager - Main Entry Point

Launches the Flet GUI by default (web + desktop).
Use --gui ctk to launch the CustomTkinter alternative.

Portable EXE mode:
  When frozen via PyInstaller, data is stored in a 'data' folder
  next to the executable:  <exe_dir>/data/db/tasks.json
  This ensures user data survives app updates.
"""
import sys
import os
from pathlib import Path


def get_app_dir() -> Path:
    """Return the application directory.

    - Frozen (PyInstaller EXE): directory containing the .exe
    - Normal (python main.py): directory containing main.py
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


def configure_import_path() -> None:
    """Add the source directory for both normal and frozen execution."""
    candidates = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / "src")
    candidates.append(get_app_dir() / "src")

    for src_path in candidates:
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))


configure_import_path()


def get_data_dir() -> Path:
    """Return the user-data directory.

    Structure:  <app_dir>/data/db/
    The 'data' folder is created automatically on first run.
    This folder is NEVER touched by app updates, so user data survives.
    """
    d = get_app_dir() / "data" / "db"
    d.mkdir(parents=True, exist_ok=True)

    # Seed an empty task database on first run. TaskRepository owns the schema
    # (a JSON *list* of task dicts), so we must not write a dict here.
    tasks_file = d / "tasks.json"
    if not tasks_file.exists():
        import json
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump([], f)

    return d


def get_db_path() -> str:
    """Return the path to the tasks JSON database file."""
    return str(get_data_dir() / "tasks.json")


def main():
    app_dir = get_app_dir()
    db_path = get_db_path()

    # Setup logging FIRST — before anything else
    from utils.logger import setup_logging, get_logger
    logs_dir = setup_logging(str(app_dir))
    log = get_logger("main")
    log.info(f"App dir: {app_dir}")
    log.info(f"Data dir: {get_data_dir()}")
    log.info(f"DB path: {db_path}")
    log.info(f"Python: {sys.version}")
    log.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    log.info(f"Args: {sys.argv}")

    # Install enhanced error handler (writes to error_log.txt on crash)
    from utils.error_handler import install_error_handler, ErrorContext
    install_error_handler(str(app_dir))

    args = sys.argv[1:]
    if getattr(sys, "frozen", False):
        # Clean up the previous executable left behind by a self-update.
        try:
            old_exe = Path(sys.executable).with_name(Path(sys.executable).name + ".old")
            if old_exe.exists():
                old_exe.unlink()
        except OSError:
            pass

    if getattr(sys, "frozen", False) and "--no-update" not in args:
        # Self-update: if a newer GitHub release exists, download it, swap the
        # binary and relaunch (we return so this old process exits). Any
        # failure here must never block the app from starting.
        try:
            from utils.updater import check_updates
            if check_updates("LgbtBsod", "task_manager", auto=True):
                log.info("Update staged; exiting for relaunch.")
                return
        except Exception as e:
            log.warning(f"Update check failed, continuing: {e}")

    gui_mode = "flet"  # default

    if "--gui" in args:
        idx = args.index("--gui")
        if idx + 1 < len(args):
            gui_mode = args[idx + 1].lower()

    log.info(f"Starting GUI: {gui_mode}")

    # Store context for crash dumps
    ErrorContext().set("gui_mode", gui_mode)
    ErrorContext().set("app_dir", str(app_dir))
    ErrorContext().set("db_path", db_path)

    try:
        if gui_mode == "ctk":
            from gui.main_window import run_app
            run_app()
        else:
            from gui_flet.app import run_app
            run_app(db_path=db_path)
    except Exception as e:
        log.critical(f"Fatal error starting GUI: {e}", exc_info=True)
        from utils.error_handler import write_error_log
        error_path = write_error_log(
            f"Fatal error starting GUI ({gui_mode}): {e}",
            app_dir=str(app_dir),
            context={"gui_mode": gui_mode, "phase": "gui_launch"},
        )
        sys.stderr.write(f"[FATAL] Error log: {error_path}\n")
        import traceback as tb
        tb.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
