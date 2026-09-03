@echo off
chcp 65001 >nul
echo.
echo  ============================================
echo    Task Manager
echo  ============================================
echo.
echo  Starting... a browser tab will open at http://localhost:8550
echo.
python "%~dp0launcher.py" %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with code %errorlevel%
    pause
)
