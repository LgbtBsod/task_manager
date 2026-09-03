# 📋 Task Manager — Kanban Board

Менеджер задач с Kanban-доской, диаграммой Ганта и дашбордом аналитики.
GUI построен на **[Flet](https://flet.dev)** (Flutter) и работает в браузере.

## ✨ Возможности

- **Kanban-доска** — Todo → In Progress → Done, drag-and-drop
- **Приоритеты** — Low / Medium / High / Critical
- **Дедлайны и учёт времени**
- **Диаграмма Ганта** — задачи во времени
- **Дашборд** — статистика, разбивка по приоритету/типу/статусу, нагрузка на команду
- **Jira-подобные поля** — тип задачи, story points, исполнитель, наблюдатели, теги
- **Offline** — данные лежат локально в `data/db/tasks.json`
- **Авто-обновление** — собранный `.exe` сам проверяет GitHub Releases и обновляется

## 🚀 Запуск из исходников

```bash
pip install -r requirements.txt
python main.py
```

Откроется вкладка браузера на `http://localhost:8550`.

Кросс-платформенный лаунчер (создаёт venv, ставит зависимости, чинит сломанный venv):

```bash
python launcher.py          # или start.bat / start.sh
```

## 📦 Готовый бинарник

Скачайте с [Releases](https://github.com/LgbtBsod/task_manager/releases):

| ОС | Файл |
|----|------|
| Windows | `TaskManager-windows.exe` |
| Linux | `TaskManager-linux` |
| macOS | `TaskManager-macos` |

Просто запустите — Python не нужен. Данные создаются в папке `data/db/` рядом
с исполняемым файлом и **не затрагиваются обновлениями**.

## 🔧 Собрать самому

```bash
python build.py            # onefile для текущей ОС -> dist/
python build.py --onedir   # папка (быстрее холодный старт)
```

Мульти-платформенная сборка и публикация в Releases происходит автоматически
в GitHub Actions при пуше тега `vX.Y.Z` (`.github/workflows/build.yml`).

## 🏗️ Архитектура

```
task_manager/
├── main.py                 # точка входа
├── launcher.py             # venv + зависимости + запуск
├── build.py                # сборка .exe (PyInstaller)
├── requirements.txt        # рантайм-зависимости (Flet, web)
├── requirements-ctk.txt    # опционально: старый CustomTkinter GUI
├── version.txt             # текущая версия (читается апдейтером)
├── src/
│   ├── core/               # модели, репозиторий (JSON), сервис, события
│   ├── gui_flet/           # Flet UI: app, kanban_view, gantt_view, dashboard_view, task_dialog
│   ├── gui/                # легаси CustomTkinter UI (--gui ctk)
│   └── utils/              # logger, error_handler, updater, helpers
└── data/db/                # хранилище задач (не в git)
```

- **Core** не знает про GUI; **GUI** зависит от `TaskService` через конструктор.
- Репозиторий — единственный владелец формата данных (`tasks.json` — JSON-список).
- Запись атомарная (`temp + os.replace`), битый JSON бэкапится, а не молча теряется.

## 🛠️ Технологии

- **flet** `~=0.86` — GUI (Flutter web)
- **pydantic** `v2` — валидация моделей
- **workalendar** — праздники РФ (опционально)
- **pyinstaller** — сборка бинарников

---
*Python 3.11+ (тестируется на 3.14) · License: MIT*
