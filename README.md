# 📋 Task Manager - Modern Kanban Board

Современный менеджер задач с визуальной Kanban-доской и дашбордом аналитики.

## ✨ Возможности

- **Kanban-доска** — 3 колонки (Todo → In Progress → Done)
- **Приоритеты** — Low/Medium/High с цветовой индикацией
- **Дедлайны** — отслеживание сроков с подсчётом дней
- **Учёт времени** — фиксация затраченных часов
- **Дашборд** — статистика, графики, прогресс выполнения
- **Offline режим** — работает без интернета
- **JSON-хранилище** — данные сохраняются локально

## 🏗️ Архитектура

```
task_manager/
├── main.py              # Точка входа
├── requirements.txt     # Зависимости
├── src/
│   ├── core/           # Domain Layer
│   │   ├── models.py   # Task, TaskStatus, Priority
│   │   ├── repository.py  # TaskRepository (JSON storage)
│   │   └── service.py  # TaskService (business logic)
│   ├── gui/            # Presentation Layer
│   │   └── main_window.py  # UI компоненты
│   └── utils/          # Utilities
│       └── helpers.py  # Вспомогательные функции
├── data/               # Хранилище задач (tasks.json)
└── dist/               # EXE-билд
    └── TaskManager     # Standalone executable
```

## 🚀 Быстрый старт

### Из исходников:
```bash
pip install -r requirements.txt
python main.py
```

### Из EXE:
```bash
./dist/TaskManager
```

## 📦 Сборка в EXE

```bash
pip install pyinstaller
pyinstaller --onefile --name "TaskManager" main.py
```

Результат: `dist/TaskManager` (~7 MB)

## 🎯 Использование

1. Нажмите **"➕ Новая задача"** для создания
2. Заполните поля: заголовок, описание, приоритет, дедлайн
3. Перемещайте задачи между колонками через редактирование
4. Откройте вкладку **"Дашборд"** для аналитики

## 📊 Метрики проекта

| Показатель | Значение |
|------------|----------|
| Строк кода | 859 |
| Модулей | 8 |
| Классов | 9 |
| EXE размер | 7.0 MB |
| Зависимостей | 4 |

## 🛠️ Технологии

- **customtkinter** — современный GUI
- **matplotlib** — графики и диаграммы
- **pillow** — обработка изображений
- **pyinstaller** — сборка в executable

## ✅ SOLID принципы

- **SRP** — каждый класс отвечает за одну задачу
- **OCP** — легко расширять через наследование
- **LSP** — подтипы заменяемы без нарушений
- **ISP** — минималистичные интерфейсы
- **DIP** — зависимости через абстракции

---
*Версия 1.0 | Python 3.12+ | License: MIT*
