"""
Task Manager - build a standalone executable with PyInstaller.

    python build.py                # onefile build for the current OS
    python build.py --onedir       # folder build (faster cold start)
    python build.py --clean        # wipe build/ and dist/ first
    python build.py --no-deps      # skip the dependency install step

Output:
    Windows : dist/TaskManager.exe   (+ dist/TaskManager/ for --onedir)
    Linux   : dist/TaskManager
    macOS   : dist/TaskManager.app

The app runs Flet in web-browser mode: launching the executable starts a local
server and opens the default browser at http://localhost:8550.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
NAME = "TaskManager"

# Pinned so `--upgrade` can never swap in a Flet with breaking API changes.
BUILD_DEPS = [
    "pyinstaller>=6.10",
    "flet[web]==0.86.5",
    "pydantic>=2.0.0",
    "workalendar>=17.0.0",
]


def info(m):  print(f"[INFO] {m}")
def warn(m):  print(f"[WARN] {m}")
def err(m):   print(f"[ERROR] {m}")


def install_deps() -> None:
    info("Installing / verifying build dependencies...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", *BUILD_DEPS],
                       timeout=900)
    if r.returncode != 0:
        err("Dependency install failed.")
        sys.exit(1)
    probe = subprocess.run(
        [sys.executable, "-c", "import flet, flet_web, pydantic, PyInstaller"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        err(f"Post-install import check failed:\n{probe.stderr}")
        sys.exit(1)


def main() -> None:
    os.chdir(APP_DIR)
    args = sys.argv[1:]
    onedir = "--onedir" in args
    clean = "--clean" in args

    print("=" * 60)
    print(f"  {NAME} — PyInstaller build ({sys.platform}, py{sys.version_info.major}.{sys.version_info.minor})")
    print("=" * 60)

    if "--no-deps" not in args:
        install_deps()

    if clean:
        for d in ("build", "dist"):
            shutil.rmtree(APP_DIR / d, ignore_errors=True)
        info("Cleaned build/ and dist/")

    # Skip PyInstaller's flet hook downloading the 100 MB desktop Flutter client
    # (web-browser mode never loads it).
    empty_view = APP_DIR / "build" / "_no_flet_view"
    empty_view.mkdir(parents=True, exist_ok=True)
    os.environ["FLET_VIEW_PATH"] = str(empty_view)

    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NAME,
        "--onedir" if onedir else "--onefile",
        "--paths", "src",
        "--add-data", f"src{sep}src",
        "--add-data", f"version.txt{sep}.",
        "--collect-all", "flet",
        "--collect-all", "flet_web",
        "--collect-submodules", "core",
        "--collect-submodules", "gui_flet",
        "--collect-submodules", "utils",
        "--collect-all", "workalendar",
        "--exclude-module", "flet_desktop",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--noupx",
    ]

    if sys.platform == "win32":
        # A console window that is hidden at startup: no visual clutter, but the
        # server process is still killable and can print update/errors.
        cmd += ["--console", "--hide-console", "hide-early"]
    # macOS / Linux: a plain --onefile console binary (dist/TaskManager). Not a
    # .app bundle — keeps the CI asset path simple and the self-updater's
    # single-file swap working the same on every OS.

    cmd.append("main.py")

    info("Running PyInstaller...")
    print("  " + " ".join(cmd))
    r = subprocess.run(cmd, timeout=1800)
    if r.returncode != 0:
        err("PyInstaller failed.")
        sys.exit(1)

    # Ship version.txt next to the output too (the updater reads it there).
    dist = APP_DIR / "dist"
    try:
        if onedir:
            shutil.copy2(APP_DIR / "version.txt", dist / NAME / "version.txt")
        else:
            shutil.copy2(APP_DIR / "version.txt", dist / "version.txt")
    except OSError:
        pass

    exe = (dist / NAME / (NAME + (".exe" if sys.platform == "win32" else ""))) if onedir \
        else (dist / (NAME + (".exe" if sys.platform == "win32" else "")))
    macapp = dist / f"{NAME}.app"

    print()
    print("=" * 60)
    if exe.exists():
        print(f"  BUILD OK -> {exe}   ({exe.stat().st_size / 1e6:.0f} MB)")
    elif macapp.exists():
        print(f"  BUILD OK -> {macapp}")
    else:
        err("Build finished but no executable was found in dist/.")
        sys.exit(1)
    print("  Data is stored next to the executable in  data/db/  and is")
    print("  never touched by an update.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        warn("cancelled")
        sys.exit(1)
