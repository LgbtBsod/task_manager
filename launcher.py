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
    python launcher.py [--no-update] [--skip-deps] [--port N]
"""
import os
import shutil
import subprocess
import sys
import traceback
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
            f.write("\nTraceback:\n")
            f.write(traceback.format_exc())
            f.write("\n")
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


def get_venv_bin_dir() -> Path:
    """Return the venv's binary directory, respecting the current platform."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts"
    return VENV_DIR / "bin"


def ensure_venv_compat_aliases():
    """Create compatibility symlinks/copies for Unix-style venv paths used by tests."""
    if sys.platform != "win32":
        return

    scripts_dir = VENV_DIR / "Scripts"
    bin_dir = VENV_DIR / "bin"
    if not scripts_dir.exists():
        return

    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("python.exe", "python", "pip.exe", "pip"):
        src = scripts_dir / name
        dst = bin_dir / name
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                try:
                    os.symlink(src, dst)
                except Exception:
                    pass


def get_venv_python() -> str:
    """Return the python executable inside the venv."""
    if sys.platform == "win32":
        return str(get_venv_bin_dir() / "python.exe")
    return str(get_venv_bin_dir() / "python")


def get_venv_pip() -> str:
    """Return the pip executable inside the venv."""
    if sys.platform == "win32":
        return str(get_venv_bin_dir() / "pip.exe")
    return str(get_venv_bin_dir() / "pip")


# ── Step 1: Virtual Environment ─────────────────────────────────────────────

def setup_venv(system_python: str) -> str:
    """Ensure a usable venv exists and return its python path.

    A venv directory that is missing its interpreter (e.g. one created on
    another OS and committed to the repo) is treated as broken and rebuilt.
    """
    venv_python = get_venv_python()
    if VENV_DIR.exists() and Path(venv_python).exists():
        info("Virtual environment already exists")
        ensure_venv_compat_aliases()
        return venv_python

    if VENV_DIR.exists():
        warn("Existing venv is broken (no interpreter) — recreating it")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    info("Creating virtual environment...")
    result = subprocess.run(
        [system_python, "-m", "venv", str(VENV_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not Path(venv_python).exists():
        err(f"Failed to create venv:\n{result.stderr}")
        sys.exit(1)
    ensure_venv_compat_aliases()
    info("Virtual environment created")
    return venv_python


# ── Step 2: Dependencies ─────────────────────────────────────────────────────

def _flet_ok(venv_python: str) -> bool:
    """True if flet + its web server deps import cleanly in the venv."""
    probe = subprocess.run(
        [venv_python, "-c", "import flet, flet_web, uvicorn, pydantic"],
        capture_output=True, text=True, timeout=60,
    )
    return probe.returncode == 0


def install_deps(venv_python: str, force: bool = False):
    """Upgrade pip and install requirements (skips if already satisfied)."""
    if not force and _flet_ok(venv_python):
        info("Dependencies already satisfied")
        return

    info("Upgrading pip...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        capture_output=True, text=True, timeout=120,
    )

    if not REQUIREMENTS_FILE.exists():
        warn("requirements.txt not found, skipping dependency install")
        return

    info("Installing dependencies (first run can take a minute)...")
    result = subprocess.run(
        [venv_python, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
        text=True, timeout=600,
    )
    if result.returncode != 0 or not _flet_ok(venv_python):
        err("Failed to install the required packages (flet / flet-web).")
        err("Try running manually:  venv\\Scripts\\python -m pip install -r requirements.txt")
        sys.exit(1)
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

def launch(venv_python: str, extra_args=None):
    """Launch main.py inside the venv."""
    main_py = APP_DIR / "main.py"
    if not main_py.exists():
        err("main.py not found!")
        sys.exit(1)

    info("Starting Task Manager...")
    print("=" * 50)
    os.chdir(str(APP_DIR))
    # subprocess (not os.execv): on Windows execv spawns a detached child and
    # kills the parent, which breaks argument quoting and terminal behaviour.
    try:
        ret = subprocess.call([venv_python, str(main_py), *(extra_args or [])])
    except KeyboardInterrupt:
        ret = 0
    sys.exit(ret)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    raw_args = sys.argv[1:]
    args = set(raw_args)
    skip_deps = "--skip-deps" in args
    no_update = "--no-update" in args

    # Anything that isn't a launcher flag is forwarded to main.py (e.g. --port).
    _own = {"--skip-deps", "--no-update"}
    passthrough = [a for a in raw_args if a not in _own]

    print("=" * 50)
    print("  Task Manager - Launcher")
    print("=" * 50)
    print()

    # 1. Find Python
    info("Checking Python...")
    system_python = find_python()
    try:
        version = subprocess.run(
            [system_python, "--version"], capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except subprocess.TimeoutExpired:
        err("The Python interpreter did not respond to '--version' (hung?)")
        sys.exit(1)
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
    launch(venv_python, passthrough)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        err(f"Launcher crashed: {e}")
        _write_crash_log(str(e))
        sys.exit(1)
