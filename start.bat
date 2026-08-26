@echo off
chcp 65001 >nul
echo.
echo  ============================================
echo   Task Manager Launcher
echo  ============================================
echo.
echo  [1] Flet GUI (web browser) - default
echo  [2] CustomTkinter GUI (desktop window)
echo.
set /p choice="  Choose GUI (1 or 2, default 1): "

if "%choice%"=="2" (
    python "%~dp0launcher.py" --gui ctk %*
) else (
    python "%~dp0launcher.py" --gui flet %*
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with code %errorlevel%
    pause
)