# 📋 Менеджер задач — Kanban

Kanban-доска, диаграмма Ганта и дашборд аналитики.
Интерфейс на **[Flet](https://flet.dev)** (Flutter), открывается в браузере.

## ✨ Возможности

- **Доска** — К выполнению → В работе → Готово, drag-and-drop (вся колонка — зона)
- **Приоритеты** — Низкий / Средний / Высокий / Критический
- **Дедлайны с временем** — «ГГГГ-ММ-ДД» или «ГГГГ-ММ-ДД ЧЧ:ММ»
- **Уведомления о сроках** — плашка на карточке за N часов (настройка) + окно при наступлении
- **Диаграмма Ганта** — задачи во времени
- **Дашборд** — статистика, разбивка по приоритету/типу/статусу, нагрузка на команду
- **Jira-поля** — тип, очки истории, исполнитель, наблюдатели, теги
- **Offline** — данные локально в `data/db/tasks.json`
- **Авто-обновление** — бинарник сам проверяет GitHub Releases и обновляется

## 📦 Готовый бинарник

Скачайте под свою ОС с [Releases](https://github.com/LgbtBsod/task_manager/releases):

| ОС | Файл |
|----|------|
| Windows | `TaskManager-windows.exe` |
| Linux | `TaskManager-linux` |
| macOS | `TaskManager-macos` |

Python не нужен. Запуск открывает вкладку браузера на `http://localhost:8550`.
Задачи создаются в `data/db/` рядом с бинарником и **не трогаются обновлениями**.

## 🚀 Запуск из исходников

```bash
pip install -r requirements.txt
python main.py                 # или:  python launcher.py  (сам поднимет venv)
```

Опции: `--port N`, `--no-update` (для собранной версии).

## 🔧 Сборка

```bash
python build.py                # onefile для текущей ОС -> dist/
python build.py --onedir       # папка (быстрее холодный старт)
```

Мульти-платформенная сборка + публикация в Releases — автоматически в GitHub
Actions по пушу тега `vX.Y.Z` (`.github/workflows/build.yml`).

### Как выпустить обновление

```bash
echo 1.0.1 > version.txt
git commit -am "v1.0.1" && git push
git tag v1.0.1 && git push origin v1.0.1
```

CI соберёт бинарники и создаст релиз `v1.0.1`. Установленные `v1.0.0`
обновятся до него при следующем запуске.

## 🏗️ Архитектура

```
task_manager/
├── main.py              # точка входа (self-update -> запуск Flet)
├── launcher.py          # venv + зависимости + запуск (для исходников)
├── build.py             # PyInstaller
├── version.txt          # текущая версия (её читает апдейтер)
├── src/
│   ├── core/            # models, repository (JSON), service, settings, events, datetimeutil
│   ├── gui_flet/        # app, kanban_view, gantt_view, dashboard_view, task_dialog, labels
│   └── utils/           # logger, error_handler, updater, helpers, _version
└── data/db/             # задачи + настройки (не в git)
```

- **core** ничего не знает про GUI; **gui_flet** получает `TaskService` в конструкторе.
- `TaskRepository` — единственный владелец формата (`tasks.json` — JSON-список).
  Запись атомарная, битый / не в той кодировке JSON восстанавливается, а не теряется.
- Каждая вкладка браузера — свой `TaskManagerApp`; общий только слой данных.

## 🛠️ Стек

- **flet** `~=0.86` — GUI (Flutter web, рендерер CanvasKit)
- **pydantic** `v2` — валидация моделей
- **pyinstaller** — бинарники

---
*Python 3.13+ (тестируется на 3.14) · MIT*
