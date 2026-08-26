@echo off
chcp 65001 >nul
:: Quick launch - Flet GUI (opens in browser at http://localhost:8550)
python "%~dp0launcher.py" --gui flet --no-update %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with code %errorlevel%
    pause
)
