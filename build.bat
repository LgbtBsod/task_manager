@echo off
chcp 65001 >nul 2>&1
echo ============================================
echo   Task Manager - EXE Builder (PyInstaller)
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
    pause
    exit /b 1
)

:: Install/upgrade PyInstaller
echo [1/4] Installing PyInstaller...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

:: Install project dependencies
echo [2/4] Installing project dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [WARN] Some dependencies failed. Continuing anyway...
)

:: Build EXE
echo [3/4] Building EXE (this may take a minute)...
pyinstaller --noconfirm --onefile --windowed --name "TaskManager" ^
    --icon "NONE" ^
    --add-data "src;src" ^
    --hidden-import "core" ^
    --hidden-import "core.models" ^
    --hidden-import "core.repository" ^
    --hidden-import "core.service" ^
    --hidden-import "core.events" ^
    --hidden-import "core.interfaces" ^
    --hidden-import "gui_flet" ^
    --hidden-import "gui_flet.app" ^
    --hidden-import "gui_flet.kanban_view" ^
    --hidden-import "gui_flet.gantt_view" ^
    --hidden-import "gui_flet.dashboard_view" ^
    --hidden-import "gui_flet.task_dialog" ^
    --hidden-import "gui" ^
    --hidden-import "gui.main_window" ^
    --hidden-import "gui.components" ^
    --hidden-import "gui.gantt_view" ^
    --hidden-import "utils" ^
    --hidden-import "utils.logger" ^
    --hidden-import "utils.error_handler" ^
    --hidden-import "utils.helpers" ^
    --hidden-import "utils.updater" ^
    --hidden-import "utils._version" ^
    --hidden-import "flet" ^
    --hidden-import "pydantic" ^
    --hidden-import "workalendar" ^
    --collect-all "flet" ^
    --collect-all "workalendar" ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check output above.
    pause
    exit /b 1
)

:: Copy version file next to EXE
echo [4/4] Finalizing...
if exist "dist\TaskManager.exe" (
    if exist "version.txt" copy "version.txt" "dist\version.txt" >nul
    echo.
    echo ============================================
    echo   BUILD SUCCESS!
    echo ============================================
    echo.
    echo   Output: dist\TaskManager.exe
    echo.
    echo   Data storage:
    echo     When you run TaskManager.exe, it creates
    echo     a 'data\db' folder next to itself.
    echo     All tasks are stored in:
    echo       data\db\tasks.json
    echo       data\db\tasks_sprints.json
    echo       data\db\tasks_versions.json
    echo.
    echo   To update: replace TaskManager.exe only.
    echo   The 'data' folder is NEVER touched.
    echo ============================================
) else (
    echo.
    echo [ERROR] TaskManager.exe not found in dist\
    echo Check PyInstaller output above.
)

pause
