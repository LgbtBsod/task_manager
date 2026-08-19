@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================
::   Task Manager - Update Script
::   Обновление через временную папку
:: ============================================

echo ============================================
echo   Task Manager - Script Обновления
echo ============================================
echo.

:: Проверка аргументов
if "%~1"=="" (
    echo [ERROR] Не указан URL архива!
    echo Использование: update.bat ^<URL_архива^> ^[версия^]
    pause
    exit /b 1
)

set "ARCHIVE_URL=%~1"
set "VERSION=%~2"
if "!VERSION!"=="" set "VERSION=latest"

echo [INFO] Версия для обновления: !VERSION!
echo [INFO] URL архива: !ARCHIVE_URL!
echo.

:: Создание уникальной временной папки
set "TEMP_BASE=%TEMP%\task_manager_update"
set "TEMP_DIR=%TEMP_BASE%\update_%VERSION%_%RANDOM%"

:: Очистка от старых временных папок с таким же префиксом
for /d %%i in ("%TEMP_BASE%\update_*") do (
    rd /s /q "%%i" 2>nul
)

echo [1/6] Создание временной папки: !TEMP_DIR!
mkdir "!TEMP_DIR!" 2>nul
if !errorlevel! neq 0 (
    echo [ERROR] Не удалось создать временную папку
    pause
    exit /b 1
)

:: Скачивание архива
echo [2/6] Скачивание архива обновлений...
curl -L -o "!TEMP_DIR!\update.zip" "!ARCHIVE_URL!"
if !errorlevel! neq 0 (
    echo [ERROR] Не удалось скачать архив
    rmdir /s /q "!TEMP_DIR!" 2>nul
    pause
    exit /b 1
)

:: Распаковка архива
echo [3/6] Распаковка архива...
powershell -Command "Expand-Archive -Path '!TEMP_DIR!\update.zip' -DestinationPath '!TEMP_DIR!\extracted' -Force"
if !errorlevel! neq 0 (
    echo [ERROR] Не удалось распаковать архив
    rmdir /s /q "!TEMP_DIR!" 2>nul
    pause
    exit /b 1
)

:: Поиск распакованной папки (GitHub добавляет префикс)
set "SOURCE_FOLDER="
for /d %%i in ("!TEMP_DIR!\extracted\*") do set "SOURCE_FOLDER=%%i"
if "!SOURCE_FOLDER!"=="" (
    echo [ERROR] Не найдена распакованная папка
    rmdir /s /q "!TEMP_DIR!" 2>nul
    pause
    exit /b 1
)

echo [INFO] Источник: !SOURCE_FOLDER!
echo.

:: Остановка приложения (если запущено)
echo [4/6] Остановка приложения...
taskkill /F /FI "WINDOWTITLE eq Task Manager*" >nul 2>nul
timeout /t 2 /nobreak >nul

:: Копирование файлов из временной папки в основную
echo [5/6] Копирование файлов обновления...
set "APP_DIR=%~dp0"

:: Создаем список файлов для исключения (заблокированные файлы)
echo venv > "!TEMP_DIR!\exclude.txt"
echo .git >> "!TEMP_DIR!\exclude.txt"
echo __pycache__ >> "!TEMP_DIR!\exclude.txt"
echo *.pyc >> "!TEMP_DIR!\exclude.txt"

:: Копируем все файлы
xcopy "!SOURCE_FOLDER!\*" "!APP_DIR!" /E /I /Y /Q /exclude:"!TEMP_DIR!\exclude.txt"
if !errorlevel! neq 0 (
    echo [WARNING] Некоторые файлы не скопировались, пробуем без исключений...
    xcopy "!SOURCE_FOLDER!\*" "!APP_DIR!" /E /I /Y /Q
)

:: Обновляем version.txt если есть
if exist "!SOURCE_FOLDER!\version.txt" (
    copy /Y "!SOURCE_FOLDER!\version.txt" "!APP_DIR!\version.txt" >nul
    echo [INFO] Файл версии обновлен
)

echo.
echo [6/6] Очистка временных файлов...
rmdir /s /q "!TEMP_DIR!" 2>nul
timeout /t 1 /nobreak >nul

echo.
echo ============================================
echo   Обновление успешно завершено!
echo   Версия: !VERSION!
echo ============================================
echo.

:: Перезапуск start.bat
echo [INFO] Перезапуск приложения...
timeout /t 2 /nobreak >nul

:: Запускаем start.bat в новом окне
start "" "cmd.exe" "/c" "cd /d !APP_DIR! && start.bat"

:: Закрываем текущее окно
exit
