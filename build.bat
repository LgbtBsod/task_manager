@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================
REM Task Manager - Build EXE Script
REM ============================================
REM Этот скрипт создает исполняемый файл (.exe)
REM из проекта Task Manager с использованием PyInstaller.
REM 
REM Особенности:
REM - Данные хранятся в папке data/db рядом с exe
REM - При первом запуске автоматически создается tasks.json
REM - Пользовательские данные не теряются при обновлении
REM ============================================

echo ╔════════════════════════════════════════════╗
echo ║   Task Manager - Создание EXE файла       ║
echo ╚════════════════════════════════════════════╝
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден! Установите Python 3.8+
    pause
    exit /b 1
)

echo [✓] Python найден
python --version
echo.

REM Проверка наличия PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Установка PyInstaller...
    pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Не удалось установить PyInstaller
        pause
        exit /b 1
    )
    echo [✓] PyInstaller установлен
) else (
    echo [✓] PyInstaller найден
)
echo.

REM Очистка предыдущих сборок
if exist "build" (
    echo [INFO] Очистка временных файлов сборки...
    rmdir /s /q build
)

if exist "dist" (
    echo [INFO] Очистка предыдущей версии dist...
    rmdir /s /q dist
)

if exist "*.spec" (
    echo [INFO] Удаление старых spec файлов...
    del /q *.spec
)

echo.
echo ╔════════════════════════════════════════════╗
echo ║   Начало сборки...                        ║
echo ╚════════════════════════════════════════════╝
echo.

REM Сборка EXE с помощью PyInstaller
REM --onefile: один исполняемый файл
REM --windowed: без консольного окна
REM --icon: иконка приложения (если есть)
REM --add-data: включаем дополнительные файлы
REM --hidden-import: импорты которые не обнаруживаются автоматически

echo [BUILD] Запуск PyInstaller...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "TaskManager" ^
    --hidden-import flet ^
    --hidden-import customtkinter ^
    --hidden-import packaging.version ^
    --collect-all flet ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Ошибка сборки! Проверьте логи выше.
    pause
    exit /b 1
)

echo.
echo ╔════════════════════════════════════════════╗
echo ║   Сборка завершена успешно!               ║
echo ╚════════════════════════════════════════════╝
echo.

REM Проверка результата
if exist "dist\TaskManager.exe" (
    echo [✓] EXE файл создан: dist\TaskManager.exe
    
    REM Создаем структуру папок для тестирования
    echo.
    echo [INFO] Создание тестовой структуры...
    
    if not exist "dist\data\db" (
        mkdir "dist\data\db"
        echo [✓] Создана папка: dist\data\db
    )
    
    echo.
    echo ╔════════════════════════════════════════════╗
    echo ║   Важно!                                  ║
    echo ╚════════════════════════════════════════════╝
    echo.
    echo При первом запуске TaskManager.exe:
    echo 1. Автоматически создастся папка data\db
    echo 2. В ней появится файл tasks.json с данными
    echo 3. Все ваши задачи будут храниться там
    echo.
    echo Папка data НЕ удаляется при обновлении!
    echo.
    echo Готовый к распространению: dist\TaskManager.exe
    echo.
) else (
    echo [ERROR] Файл TaskManager.exe не найден!
    pause
    exit /b 1
)

echo ════════════════════════════════════════════
echo [SUCCESS] Все готово!
echo ════════════════════════════════════════════
echo.
pause
