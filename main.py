"""Task Manager — entry point.

Launches the Flet GUI (a local web server; opens a browser tab). When frozen
via PyInstaller, all data / logs live next to the .exe so they survive updates
(see ``core.paths``).
"""
import os
import sys
import time
from pathlib import Path


def _ensure_std_streams() -> None:
    """A PyInstaller ``--windowed`` build has no console, so ``sys.stdout`` /
    ``sys.stderr`` are ``None`` and the first ``print()`` (ours, uvicorn's,
    Flet's) would crash the app. Point them at a log file next to the exe,
    falling back to the null device. Must run before anything prints.
    """
    if not getattr(sys, "frozen", False):
        return
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is not None:
            continue
        stream = None
        try:
            log_path = Path(sys.executable).parent / "logs" / "console.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            stream = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
        except OSError:
            try:
                stream = open(os.devnull, "w")
            except OSError:
                stream = None
        if stream is not None:
            setattr(sys, name, stream)
            setattr(sys, f"__{name}__", stream)


_ensure_std_streams()

# Bootstrap: put src/ on the path so `import core.*` works, then hand every
# other path question to core.paths.
_here = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
for _p in (_here / "src", Path(__file__).resolve().parent / "src"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core import paths  # noqa: E402
from core.app_context import AppContext  # noqa: E402

paths.ensure_src_on_path()


def _finish_pending_update(log) -> bool:
    """If a previous run downloaded an update but the relaunch helper never
    swapped it in (killed helper, AV-quarantined script, a Cyrillic path that
    broke the old helper), a ``<exe>.updated`` file is sitting next to us.
    We are the OLD binary — retry the swap via a fresh helper and exit.

    Returns True if a relaunch was kicked off (caller should exit).
    """
    exe = paths.exe_path or Path(sys.executable)
    staged = exe.with_name(exe.name + ".updated")
    if not staged.is_file() or staged.stat().st_size < 1_000_000:
        return False
    log.warning("Found a staged update (%s); finishing it now.", staged.name)
    try:
        from utils.updater import AutoUpdater
        AutoUpdater("LgbtBsod", "task_manager")._relaunch_after_update()
        return True
    except Exception as e:
        log.error("Could not finish the pending update: %s", e)
        return False


def _cleanup_update_leftovers(log) -> None:
    """Sweep files a completed self-update leaves behind (the helper cleans up
    after itself, but a hard-killed one may not)."""
    exe = paths.exe_path or Path(sys.executable)
    for path in (exe.with_name(exe.name + ".old"),
                 paths.app_dir / "update_restart.vbs",
                 paths.app_dir / "update_restart.cmd"):
        for attempt in range(3):
            try:
                if path.exists():
                    path.unlink()
                    log.info("Removed update leftover: %s", path.name)
                break
            except OSError:
                time.sleep(0.3 * (attempt + 1))


def main() -> None:
    from utils.logger import setup_logging, get_logger
    setup_logging(str(paths.app_dir))
    log = get_logger("main")
    log.info("App dir: %s | frozen: %s | python: %s", paths.app_dir, paths.frozen,
             sys.version.split()[0])
    log.info("Args: %s", sys.argv)

    from utils.error_handler import install_error_handler, ErrorContext
    install_error_handler(str(paths.app_dir))
    ErrorContext().set("app_dir", str(paths.app_dir))

    args = sys.argv[1:]
    if paths.frozen:
        if _finish_pending_update(log):
            log.info("Pending update handed to the relaunch helper; exiting.")
            return
        _cleanup_update_leftovers(log)

    if paths.frozen and "--force-update" in args:
        # Opt-in CLI path: download + install now, before the GUI, then exit for
        # relaunch. The normal flow asks inside the running app instead.
        try:
            from utils.updater import check_updates
            if check_updates("LgbtBsod", "task_manager", auto=True, force=True):
                log.info("Update staged; exiting for relaunch.")
                return
        except Exception as e:
            log.warning("Forced update failed, continuing: %s", e)

    port = 8550
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except (ValueError, IndexError):
            pass

    log.info("Starting Flet GUI on port %d", port)
    try:
        context = AppContext.create()
        from gui_flet.app import run_app
        run_app(context=context, port=port)
    except Exception as e:
        log.critical("Fatal error starting GUI: %s", e, exc_info=True)
        from utils.error_handler import write_error_log
        error_path = write_error_log(
            f"Fatal error starting GUI: {e}",
            app_dir=str(paths.app_dir),
            context={"phase": "gui_launch"},
        )
        sys.stderr.write(f"[FATAL] Error log: {error_path}\n")
        import traceback as tb
        tb.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
