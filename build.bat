@echo off
chcp 65001 >nul
REM Thin wrapper around build.py — all logic lives there.
python "%~dp0build.py" %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed with code %errorlevel%
    pause
    exit /b %errorlevel%
)
pause
