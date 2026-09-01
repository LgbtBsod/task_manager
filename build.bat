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

:: Install/upgrade PyInstaller and dependencies
echo [1/4] Installing PyInstaller and dependencies...
pip install --upgrade pyinstaller flet pydantic workalendar
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Build EXE with improved options for Flet
echo [2/4] Building EXE (this may take a minute)...
pyinstaller --noconfirm --onefile --windowed --name "TaskManager" ^
    --icon "NONE" ^
    --add-data "src;src" ^
    --add-data "tasks.json;." ^
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
    --hidden-import "flet.web" ^
    --hidden-import "pydantic" ^
    --hidden-import "workalendar" ^
    --collect-all "flet" ^
    --collect-all "flet_web" ^
    --collect-all "workalendar" ^
    --collect-all "pydantic" ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check output above.
    pause
    exit /b 1
)

:: Copy version file next to EXE
echo [3/4] Copying version file...
if exist "dist\TaskManager.exe" (
    if exist "version.txt" copy "version.txt" "dist\version.txt" >nul
)

:: Create launcher batch file for updates
echo [4/4] Creating update launcher...
if exist "dist\TaskManager.exe" (
    (
        echo @echo off
        echo chcp 65001 ^>nul
        echo setlocal
        echo set "APP_DIR=%%~dp0"
        echo cd /d "%%APP_DIR%%"
        echo.
        echo REM Check for updates on startup
        echo if exist "TaskManager.exe" (
        echo     start "" "TaskManager.exe" --no-update
        echo ) else (
        echo     echo TaskManager.exe not found!
        echo     pause
        echo )
    ) > "dist\run.bat"
    
    echo.
    echo ============================================
    echo   BUILD SUCCESS!
    echo ============================================
    echo.
    echo   Output: dist\TaskManager.exe
    echo   Launcher: dist\run.bat
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
