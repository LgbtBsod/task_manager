#!/bin/bash

echo "============================================"
echo "  Task Manager - Setup and Launch Script"
echo "============================================"
echo ""

# Проверка наличия Git
if ! command -v git &> /dev/null; then
    echo "[ERROR] Git не найден! Пожалуйста, установите Git:"
    echo "https://git-scm.com/download/linux"
    exit 1
fi

# Обновление проекта из Git
echo "[1/4] Проверка обновлений проекта..."
git fetch origin > /dev/null 2>&1
if [ $? -eq 0 ]; then
    if ! git diff --quiet HEAD origin/main 2>/dev/null; then
        echo "Найдены обновления! Загрузка..."
        git pull origin main
        if [ $? -ne 0 ]; then
            echo "[WARNING] Не удалось обновить проект, продолжаем с текущей версией"
        fi
    else
        echo "Проект актуален"
    fi
else
    echo "[WARNING] Не удалось подключиться к репозиторию, пропускаем обновление"
fi
echo ""

# Проверка наличия Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[2/4] Python не найден!"
    echo "[ERROR] Установите Python вручную:"
    echo "https://www.python.org/downloads/"
    exit 1
else
    echo "[2/4] Python найден"
fi

# Определяем команду python
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
fi

echo ""

# Создание виртуального окружения
echo "[3/4] Настройка виртуального окружения..."
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Не удалось создать виртуальное окружение"
        exit 1
    fi
else
    echo "Виртуальное окружение уже существует"
fi

# Активация виртуального окружения
source venv/bin/activate

# Обновление pip
echo "Обновление pip..."
python -m pip install --upgrade pip --quiet
if [ $? -ne 0 ]; then
    echo "[WARNING] Не удалось обновить pip"
fi

# Установка зависимостей
echo "Установка зависимостей..."
pip install -r requirements.txt --upgrade --quiet
if [ $? -ne 0 ]; then
    echo "[WARNING] Некоторые зависимости могли установиться с ошибками"
fi
echo ""

# Запуск проверки обновлений через Python
echo "[INFO] Проверка обновлений приложения..."
python -c "from src.utils.updater import check_updates; check_updates('LgbtBsod', 'task_manager')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[WARNING] Не удалось проверить обновления, продолжаем запуск..."
fi
echo ""

# Запуск приложения
echo "[4/4] Запуск приложения..."
echo "============================================"
python main.py

# Если приложение завершилось с ошибкой
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Приложение завершилось с кодом ошибки: $?"
fi

deactivate
