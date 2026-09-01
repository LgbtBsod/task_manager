"""
Task Manager - Build Script for PyInstaller
Replaces build.bat with a pure Python script.

Usage:
    python build.py [--clean] [--onefile|--onedir] [--name TaskManager]
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path


def info(msg: str):
    print(f"[INFO] {msg}")


def warn(msg: str):
    print(f"[WARNING] {msg}")


def err(msg: str):
    print(f"[ERROR] {msg}")


def main():
    app_dir = Path(__file__).parent.resolve()
    os.chdir(str(app_dir))

    print("=" * 60)
    print("  Task Manager - EXE Builder (PyInstaller)")
    print("=" * 60)
    print()

    # Parse arguments
    args = sys.argv[1:]
    clean_build = "--clean" in args
    onedir = "--onedir" in args
    custom_name = None
    if "--name" in args:
        idx = args.index("--name")
        if idx + 1 < len(args):
            custom_name = args[idx + 1]

    # Check Python
    info("Checking Python...")
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True, text=True, timeout=10
        )
        info(f"Python: {result.stdout.strip()}")
    except Exception as e:
        err(f"Python check failed: {e}")
        sys.exit(1)

    # Install/upgrade dependencies
    info("[1/4] Installing PyInstaller and dependencies...")
    deps = ["pyinstaller", "flet", "pydantic", "workalendar"]
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + deps + ["--quiet"],
            timeout=300,
            check=True
        )
        info("Dependencies installed")
    except subprocess.CalledProcessError as e:
        err(f"Failed to install dependencies: {e}")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        err("Dependency installation timed out")
        sys.exit(1)

    # Clean previous build if requested
    dist_dir = app_dir / "dist"
    build_dir = app_dir / "build"
    spec_file = app_dir / "TaskManager.spec"

    if clean_build:
        info("Cleaning previous build...")
        for d in [dist_dir, build_dir]:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        if spec_file.exists():
            spec_file.unlink()

    # Build EXE command
    info("[2/4] Building EXE (this may take a minute)...")
    
    exe_name = custom_name or "TaskManager"
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
    ]
    
    if onedir:
        pyinstaller_cmd.append("--onedir")
    else:
        pyinstaller_cmd.append("--onefile")
    
    pyinstaller_cmd.extend([
        "--name", exe_name,
        "--icon", "NONE",
        "--add-data", f"src{os.pathsep}src",
        "--add-data", f"tasks.json{os.pathsep}.",
        "--hidden-import", "core",
        "--hidden-import", "core.models",
        "--hidden-import", "core.repository",
        "--hidden-import", "core.service",
        "--hidden-import", "core.events",
        "--hidden-import", "core.interfaces",
        "--hidden-import", "gui_flet",
        "--hidden-import", "gui_flet.app",
        "--hidden-import", "gui_flet.kanban_view",
        "--hidden-import", "gui_flet.gantt_view",
        "--hidden-import", "gui_flet.dashboard_view",
        "--hidden-import", "gui_flet.task_dialog",
        "--hidden-import", "gui",
        "--hidden-import", "gui.main_window",
        "--hidden-import", "gui.components",
        "--hidden-import", "gui.gantt_view",
        "--hidden-import", "utils",
        "--hidden-import", "utils.logger",
        "--hidden-import", "utils.error_handler",
        "--hidden-import", "utils.helpers",
        "--hidden-import", "utils.updater",
        "--hidden-import", "utils._version",
        "--hidden-import", "flet",
        "--hidden-import", "flet.web",
        "--hidden-import", "pydantic",
        "--hidden-import", "workalendar",
        "--collect-all", "flet",
        "--collect-all", "flet_web",
        "--collect-all", "workalendar",
        "--collect-all", "pydantic",
        "main.py"
    ])

    try:
        result = subprocess.run(
            pyinstaller_cmd,
            timeout=600,
            capture_output=False
        )
        if result.returncode != 0:
            err("Build failed! Check output above.")
            sys.exit(1)
        info("Build completed")
    except subprocess.TimeoutExpired:
        err("Build timed out")
        sys.exit(1)
    except Exception as e:
        err(f"Build failed: {e}")
        sys.exit(1)

    # Copy version file
    info("[3/4] Copying version file...")
    exe_path = dist_dir / exe_name / f"{exe_name}.exe" if onedir else dist_dir / f"{exe_name}.exe"
    
    if exe_path.exists():
        version_src = app_dir / "version.txt"
        version_dst = dist_dir / "version.txt"
        if version_src.exists():
            shutil.copy2(version_src, version_dst)
        info("Version file copied")
    else:
        warn(f"EXE not found at {exe_path}")

    # Create launcher batch file
    info("[4/4] Creating update launcher...")
    if exe_path.exists():
        run_bat = dist_dir / "run.bat"
        run_bat_content = f'''@echo off
chcp 65001 >nul
setlocal
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

REM Check for updates on startup
if exist "{exe_name}.exe" (
    start "" "{exe_name}.exe" --no-update
) else (
    echo {exe_name}.exe not found!
    pause
)
'''
        run_bat.write_text(run_bat_content, encoding="utf-8")
        info("Launcher created")

        print()
        print("=" * 60)
        print("  BUILD SUCCESS!")
        print("=" * 60)
        print()
        print(f"  Output: {exe_path}")
        print(f"  Launcher: {run_bat}")
        print()
        print("  Data storage:")
        print("    When you run the EXE, it creates")
        print("    a 'data\\db' folder next to itself.")
        print("    All tasks are stored in:")
        print("      data\\db\\tasks.json")
        print("      data\\db\\tasks_sprints.json")
        print("      data\\db\\tasks_versions.json")
        print()
        print("  To update: replace the EXE only.")
        print("  The 'data' folder is NEVER touched.")
        print("=" * 60)
    else:
        err(f"{exe_name}.exe not found in dist\\")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        warn("\nBuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        err(f"Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
