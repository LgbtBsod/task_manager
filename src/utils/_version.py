"""
Task Manager - Version File
Auto-generated version information
Version is now stored in version.txt file
"""

import os

# Путь к файлу версии (относительно этого файла)
VERSION_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'version.txt')


def get_version() -> str:
    """Получить текущую версию из файла version.txt.
    
    Returns:
        str: Текущая версия приложения.
    """
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                return version if version else "unknown"
        else:
            return "unknown"
    except Exception:
        return "unknown"


def get_build_info() -> str:
    """Получить информацию о сборке.
    
    Returns:
        str: Информация о сборке.
    """
    return "auto-updated"


# Для обратной совместимости
__version__ = get_version()
__build__ = get_build_info()
