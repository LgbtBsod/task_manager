"""
Модуль инициализации данных приложения.
Проверяет и создает необходимую структуру папок и файлов при запуске.
"""
import os
import json
from pathlib import Path

# Базовая директория данных (относительно расположения exe/скрипта)
BASE_DIR = Path(__file__).parent.parent / "data"
DB_DIR = BASE_DIR / "db"
TASKS_FILE = DB_DIR / "tasks.json"

# Шаблон начальных данных для задач
DEFAULT_TASKS_DATA = {
    "tasks": [],
    "categories": [
        {"id": 1, "name": "Работа", "color": "#4CAF50"},
        {"id": 2, "name": "Личное", "color": "#2196F3"},
        {"id": 3, "name": "Покупки", "color": "#FF9800"}
    ],
    "settings": {
        "theme": "light",
        "language": "ru",
        "notifications": True
    }
}


def init_data_structure():
    """
    Инициализирует структуру данных:
    - Создает папку data/db если не существует
    - Создает tasks.json с данными по умолчанию если не существует
    """
    print(f"[INIT] Проверка структуры данных...")
    print(f"[INIT] Базовая директория: {BASE_DIR}")
    
    # Создаем директорию data если нет
    if not BASE_DIR.exists():
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[INIT] ✅ Создана директория: {BASE_DIR}")
    else:
        print(f"[INIT] ✅ Директория существует: {BASE_DIR}")
    
    # Создаем директорию db если нет
    if not DB_DIR.exists():
        DB_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[INIT] ✅ Создана директория: {DB_DIR}")
    else:
        print(f"[INIT] ✅ Директория существует: {DB_DIR}")
    
    # Проверяем наличие файла tasks.json
    if not TASKS_FILE.exists():
        # Создаем файл с данными по умолчанию
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_TASKS_DATA, f, ensure_ascii=False, indent=2)
        print(f"[INIT] ✅ Создан файл задач: {TASKS_FILE}")
    else:
        print(f"[INIT] ✅ Файл задач существует: {TASKS_FILE}")
        
        # Валидация структуры JSON (на случай повреждения)
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверяем обязательные ключи
            required_keys = ["tasks", "categories", "settings"]
            for key in required_keys:
                if key not in data:
                    data[key] = DEFAULT_TASKS_DATA[key]
                    print(f"[INIT] ⚠️ Добавлен отсутствующий ключ: {key}")
            
            # Сохраняем исправленные данные если были изменения
            if data != DEFAULT_TASKS_DATA:
                with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
        except json.JSONDecodeError as e:
            print(f"[INIT] ⚠️ Ошибка чтения JSON: {e}")
            print(f"[INIT] ⚠️ Восстановление из резервной копии...")
            # Создаем резервную копию поврежденного файла
            backup_file = TASKS_FILE.with_suffix('.json.bak')
            TASKS_FILE.rename(backup_file)
            # Создаем новый файл
            with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_TASKS_DATA, f, ensure_ascii=False, indent=2)
            print(f"[INIT] ✅ Файл восстановлен. Поврежденный файл сохранен как: {backup_file}")
    
    print(f"[INIT] ✅ Инициализация данных завершена успешно!")
    return True


def get_tasks_file_path() -> Path:
    """Возвращает полный путь к файлу задач"""
    return TASKS_FILE


def load_tasks_data() -> dict:
    """Загружает данные задач из JSON файла"""
    if not TASKS_FILE.exists():
        init_data_structure()
    
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tasks_data(data: dict) -> bool:
    """Сохраняет данные задач в JSON файл"""
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось сохранить данные: {e}")
        return False


if __name__ == "__main__":
    # Тестовый запуск
    init_data_structure()
