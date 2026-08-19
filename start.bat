@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   Task Manager - Setup and Launch Script
echo ============================================
echo.

:: Проверка наличия Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git не найден! Пожалуйста, установите Git:
    echo https://git-scm.com/download/win
    pause
    exit /b 1
)

:: Обновление проекта из Git
echo [1/4] Проверка обновлений проекта...
git fetch origin >nul 2>&1
if %errorlevel% equ 0 (
    git diff --quiet HEAD origin/main 2>nul
    if %errorlevel% neq 0 (
        echo Найдены обновления! Загрузка...
        git pull origin main
        if %errorlevel% neq 0 (
            echo [WARNING] Не удалось обновить проект, продолжаем с текущей версией
        )
    ) else (
        echo Проект актуален
    )
) else (
    echo [WARNING] Не удалось подключиться к репозиторию, пропускаем обновление
)
echo.

:: Проверка наличия Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [2/4] Python не найден! Начинаем установку...
    
    :: Создаем временную папку для загрузчика
    set "TEMP_DIR=%TEMP%\python_installer"
    mkdir "%TEMP_DIR%" 2>nul
    
    :: Скачиваем Python installer (версия 3.11.9)
    echo Скачивание Python 3.11.9...
    curl -L -o "%TEMP_DIR%\python-installer.exe" ^
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    
    if !errorlevel! neq 0 (
        echo [ERROR] Не удалось скачать Python installer
        rmdir /s /q "%TEMP_DIR%" 2>nul
        pause
        exit /b 1
    )
    
    :: Тихая установка Python
    echo Установка Python...
    start /wait "" "%TEMP_DIR%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    rmdir /s /q "%TEMP_DIR%" 2>nul
    
    :: Обновляем переменные окружения для текущей сессии
    echo Обновление переменных окружения...
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%b"
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSTEM_PATH=%%b"
    set "PATH=%USER_PATH%;%SYSTEM_PATH%"
    
    :: Проверяем установку
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Не удалось установить Python. Установите вручную:
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo Python успешно установлен!
) else (
    echo [2/4] Python найден
)
echo.

:: Создание виртуального окружения
echo [3/4] Настройка виртуального окружения...
if not exist "venv" (
    echo Создание виртуального окружения...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
) else (
    echo Виртуальное окружение уже существует
)

:: Активация виртуального окружения
call venv\Scripts\activate.bat

:: Обновление pip
echo Обновление pip...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Не удалось обновить pip
)

:: Установка зависимостей
echo Установка зависимостей...
pip install -r requirements.txt --upgrade --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Некоторые зависимости могли установиться с ошибками
)
echo.

:: Запуск проверки обновлений через Python (надежнее чем парсинг в bat)
echo [INFO] Проверка обновлений приложения...
python -c "from src.utils.updater import check_updates; check_updates('LgbtBsod', 'task_manager')"
if %errorlevel% neq 0 (
    echo [WARNING] Не удалось проверить обновления, продолжаем запуск...
)
echo.

:: Запуск приложения
echo [4/4] Запуск приложения...
echo ============================================
python main.py

:: Если приложение завершилось с ошибкой
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Приложение завершилось с кодом ошибки: %errorlevel%
    pause
)

endlocal
