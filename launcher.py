"""
Task Manager - Unified Cross-Platform Launcher
Replaces start.bat / start.sh with a single Python script.

Responsibilities:
- Check Python availability
- Create/activate virtual environment
- Install/upgrade dependencies
- Optional: quick non-blocking update check via Git or GitHub API
- Launch main.py

Usage:
    python launcher.py [--no-update] [--skip-deps] [--gui flet|ctk]

GUI modes:
    flet  — Flet web/desktop GUI (default, opens in browser)
    ctk   — CustomTkinter desktop GUI
"""
import sys
import os
import traceback
import subprocess
import shutil
from pathlib import Path

# Project root is the directory containing this script
APP_DIR = Path(__file__).resolve().parent
VENV_DIR = APP_DIR / "venv"
REQUIREMENTS_FILE = APP_DIR / "requirements.txt"
REPO_OWNER = "LgbtBsod"
REPO_NAME = "task_manager"


def _write_crash_log(error_msg: str):
    """Write crash log to logs/error_log.txt when launcher fails."""
    try:
        logs_dir = APP_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        crash_path = logs_dir / "error_log.txt"
        from datetime import datetime
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"LAUNCHER CRASH — {datetime.now().isoformat()}\n")
            f.write(f"{'='*60}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"CWD: {os.getcwd()}\n")
            f.write(f"argv: {sys.argv}\n")
            f.write(f"Error: {error_msg}\n")
            f.write(f"\nTraceback:\n")
            f.write(traceback.format_exc())
            f.write(f"\n")
        print(f"[ERROR] Crash log written to: {crash_path}")
    except Exception:
        pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def info(msg: str):
    print(f"[INFO] {msg}")


def warn(msg: str):
    print(f"[WARNING] {msg}")


def err(msg: str):
    print(f"[ERROR] {msg}")


def find_python() -> str:
    """Return a usable python executable path."""
    # Prefer the current interpreter
    if sys.executable and "venv" not in sys.executable:
        return sys.executable
    # Search PATH
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            return path
    err("Python not found! Install it from https://www.python.org/downloads/")
    sys.exit(1)


def get_venv_python() -> str:
    """Return the python executable inside the venv."""
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def get_venv_pip() -> str:
    """Return the pip executable inside the venv."""
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


# ── Step 1: Virtual Environment ─────────────────────────────────────────────

def setup_venv(system_python: str) -> str:
    """Ensure venv exists and return the venv python path."""
    venv_python = get_venv_python()
    if VENV_DIR.exists() and Path(venv_python).exists():
        info("Virtual environment already exists")
        return venv_python

    info("Creating virtual environment...")
    result = subprocess.run(
        [system_python, "-m", "venv", str(VENV_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        err(f"Failed to create venv:\n{result.stderr}")
        sys.exit(1)
    info("Virtual environment created")
    return venv_python


# ── Step 2: Dependencies ─────────────────────────────────────────────────────

def install_deps(venv_python: str):
    """Upgrade pip and install requirements."""
    venv_pip = get_venv_pip()

    # Upgrade pip
    info("Upgrading pip...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        capture_output=True, text=True, timeout=120,
    )

    if not REQUIREMENTS_FILE.exists():
        warn("requirements.txt not found, skipping dependency install")
        return

    info("Installing dependencies...")
    result = subprocess.run(
        [venv_pip, "install", "-r", str(REQUIREMENTS_FILE), "--quiet"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        warn("Some dependencies may have failed to install")
    else:
        info("Dependencies installed")


# ── Step 3: Optional Git Pull (non-blocking, short timeout) ──────────────────

def try_git_pull():
    """Attempt git pull with a short timeout. Never blocks startup."""
    git = shutil.which("git")
    if not git:
        return

    git_dir = APP_DIR / ".git"
    if not git_dir.exists():
        return

    info("Checking for git updates (5 s timeout)...")
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, text=True, timeout=5, cwd=str(APP_DIR),
        )
        if fetch.returncode != 0:
            warn("Could not reach remote repository, skipping")
            return

        diff = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "origin/main"],
            capture_output=True, text=True, timeout=5, cwd=str(APP_DIR),
        )
        if diff.returncode == 0:
            info("Project is up to date")
            return

        info("Updates found, pulling...")
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, timeout=30, cwd=str(APP_DIR),
        )
        if pull.returncode != 0:
            warn("git pull failed, continuing with current version")
        else:
            info("Project updated from git")
    except subprocess.TimeoutExpired:
        warn("Git operation timed out, skipping")
    except Exception as e:
        warn(f"Git update skipped: {e}")


# ── Step 4: Launch ───────────────────────────────────────────────────────────

def launch(venv_python: str):
    """Launch main.py inside the venv."""
    main_py = APP_DIR / "main.py"
    if not main_py.exists():
        err("main.py not found!")
        sys.exit(1)

    info("Starting Task Manager...")
    if gui_args:
        info(f"GUI mode: {gui_args[1]}")
    print("=" * 50)
    os.chdir(str(APP_DIR))
    os.execv(venv_python, [venv_python, str(main_py)] + gui_args)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    raw_args = sys.argv[1:]
    args = set(raw_args)
    skip_deps = "--skip-deps" in args
    no_update = "--no-update" in args

    # Extract --gui value for passing to main.py
    gui_args = []
    if "--gui" in raw_args:
        idx = raw_args.index("--gui")
        if idx + 1 < len(raw_args):
            gui_args = ["--gui", raw_args[idx + 1]]

    print("=" * 50)
    print("  Task Manager - Launcher")
    print("=" * 50)
    print()

    # 1. Find Python
    info("Checking Python...")
    system_python = find_python()
    version = subprocess.run(
        [system_python, "--version"], capture_output=True, text=True
    ).stdout.strip()
    info(f"Python: {version}")
    print()

    # 2. Setup venv
    info("[1/4] Setting up virtual environment...")
    venv_python = setup_venv(system_python)
    print()

    # 3. Install deps
    if not skip_deps:
        info("[2/4] Installing dependencies...")
        install_deps(venv_python)
    else:
        info("[2/4] Skipping dependency install")
    print()

    # 4. Git update (non-blocking, optional)
    if not no_update:
        info("[3/4] Checking git updates...")
        try_git_pull()
    else:
        info("[3/4] Skipping update check")
    print()

    # 5. Launch
    info("[4/4] Launching application...")
    launch(venv_python)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        err(f"Launcher crashed: {e}")
        _write_crash_log(str(e))
        sys.exit(1)
