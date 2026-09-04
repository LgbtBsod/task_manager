"""The one place every user-facing string lives — UI chrome, dialog labels,
notification text, validation messages, unit suffixes.

Rules:
- No f-strings baked into other modules for user text. Templates here take
  ``{placeholders}`` and callers do ``S.SOME_TEXT.format(...)``.
- The domain layer stores enum *values* in English ("Todo", "High", "Bug");
  the ``*_LABEL`` dicts / helpers map those to what the user sees.
- Pure data + tiny helpers only — no Flet / no other project imports — so
  ``core`` and ``gui_flet`` can both import it.
"""

APP_TITLE = "Менеджер задач"

# ── navigation ──
NAV = {
    "kanban": "Доска",
    "gantt": "Гант",
    "dashboard": "Обзор",
}

# ── enum value -> RU label ──
STATUS_LABEL = {
    "Todo": "К выполнению",
    "In Progress": "В работе",
    "Done": "Готово",
}
PRIORITY_LABEL = {
    "Low": "Низкий",
    "Medium": "Средний",
    "High": "Высокий",
    "Critical": "Критический",
}
TASK_TYPE_LABEL = {
    "Task": "Задача",
    "Bug": "Ошибка",
    "Story": "История",
    "Epic": "Эпик",
    "Sub-task": "Подзадача",
}
URGENCY_LABEL = {
    "Low": "Низкая",
    "Normal": "Обычная",
    "High": "Высокая",
    "Urgent": "Срочная",
}

# status value -> (Material icon name, COLORS key) — board columns, gantt rows
# and the dashboard "по статусу" bars read this so they stay in step.
STATUS_STYLE = {
    "Todo":        ("radio_button_unchecked", "accent_blue"),
    "In Progress": ("pending",                "accent_orange"),
    "Done":        ("check_circle",            "accent_green"),
}
# task-type value -> chip / bar colour (SAP Horizon accents, both modes).
TYPE_COLOR = {
    "Task": "#788fa6", "Bug": "#f53232", "Story": "#7858ff",
    "Epic": "#e76500", "Sub-task": "#36a41d",
}

# ── unit suffixes ──
UNIT_DAYS = "дн."
UNIT_HOURS = "ч"
UNIT_MINUTES = "мин"
STORY_POINTS = "ОИ"          # очки истории


class UI:
    """Buttons, field labels, section headers, placeholders, tooltips."""
    ADD = "Добавить"
    SAVE = "Сохранить"
    CANCEL = "Отмена"
    OK = "Понятно"
    SEARCH = "Поиск..."
    SETTINGS = "Настройки"

    NEW_TASK = "Новая задача"
    EDIT_TASK = "Редактирование"

    SORT = {"default": "Без сортировки", "priority": "По приоритету", "due_date": "По дедлайну"}

    # task card actions
    CLONE = "Клонировать"
    EDIT = "Редактировать"
    DELETE = "Удалить"
    CLONED = "Клонировано: {title}"
    DELETE_TASK_TITLE = "Удалить задачу"
    DELETE_TASK_CONFIRM = 'Удалить "{title}"?'

    # task dialog fields
    F_TITLE = "Название"
    F_DESCRIPTION = "Описание"
    F_PRIORITY = "Приоритет"
    F_TYPE = "Тип"
    F_URGENCY = "Срочность"
    F_START_DATE = "Дата начала"
    F_DUE_DATE = "Дедлайн"
    F_TIME = "Время"
    F_TIME_HINT = "ЧЧ:ММ"
    F_TIME_SPENT = "Затрачено (часы)"
    F_TAGS = "Теги (через запятую)"
    F_ASSIGNEE = "Исполнитель"
    F_STORY_POINTS = "Очки истории"
    F_WATCHERS = "Наблюдатели (через запятую)"

    # tags — registry chooser on the task dialog
    F_TAGS_PICK = "Теги"
    F_TAGS_NONE = "Тегов пока нет — добавьте в настройках или ниже"
    F_TAGS_NEW_HINT = "Новый тег…"
    F_TAGS_ADD = "Добавить тег"

    # kanban deadline chips
    D_OVERDUE = "просрочено"
    D_OVERDUE_ON = "Просрочен: {when}"
    D_TODAY = "Сегодня: {when}"
    D_SOON = "Скоро: {when}"
    D_MINUTES = "{n} мин"
    D_HOURS = "{n} ч"
    D_DAYS = "{n} дн."

    # deadline popup
    DEADLINE_POPUP_TITLE = "Наступил срок задач"
    DEADLINE_POPUP_MORE = "\n… и ещё {n}"
    DEADLINE_POPUP_ITEM = "•  {title}"

    # dashboard
    DASH_TOTAL = "Всего"
    DASH_DONE = "Выполнено"
    DASH_IN_PROGRESS = "В работе"
    DASH_OVERDUE = "Просрочено"
    DASH_BY_PRIORITY = "По приоритету"
    DASH_BY_TYPE = "По типу"
    DASH_BY_STATUS = "По статусу"
    DASH_BY_TAG = "По тегам"
    DASH_TAG_EMPTY = "Нет тегов для аналитики"
    DASH_WORKLOAD = "Нагрузка на команду"
    DASH_PROGRESS = "Прогресс выполнения"
    DASH_TIME_SPENT = "Затрачено времени"
    DASH_N_TASKS = "{n} задач"
    DASH_N_IN_PROGRESS = "{n} в работе"

    # gantt
    GANTT_TITLE = "Диаграмма Ганта"
    GANTT_COL_TASK = "Задача"
    GANTT_TODAY = "Сегодня"
    GANTT_EMPTY = "Нет задач с датами для отображения"
    GANTT_EMPTY_HINT = "Добавьте дату начала или дедлайн к задаче"
    GANTT_RANGE = {"all": "Все", "month": "Месяц", "week": "Неделя", "quarter": "Квартал"}
    GANTT_TOOLTIP = "{title} | {priority} | {status} | {start} — {end}"

    # settings dialog
    SET_SECTION_NOTIFY = "Уведомления"
    SET_NOTIFY_ENABLED = "Уведомлять о приближении сроков"
    SET_HOURS_BEFORE = "Часов до срока"
    SET_NOTIFY_HINT = ("Карточки с приближающимся дедлайном подсвечиваются; когда "
                       "срок наступает — появляется окно.")
    SET_THEME = "Тема"
    # theme_mode value -> RU label. "Вечер"/"Утро" == SAP Horizon Evening/Morning.
    THEME_MODE_LABEL = {"dark": "Вечер", "light": "Утро", "system": "Системная"}
    SET_ACCENT = "Акцентный цвет"
    SET_COLORS = "Цвета интерфейса"
    SET_COLORS_HINT = "Пусто — цвет темы. Кликните образец для палитры, или введите #rrggbb."
    SET_COLORS_RESET = "Сбросить все цвета"
    SET_COLOR_DEFAULT = "Цвет темы"
    SET_COLORS_LOW_CONTRAST = "⚠ Текст плохо читается на фоне карточек — увеличьте контраст."
    # tag registry (Settings → "Теги")
    SET_TAGS = "Теги"
    SET_TAGS_HINT = ("Общий список тегов вместо ручного ввода. Кликните образец, "
                     "чтобы изменить цвет; ✎ — переименовать, 🗑 — удалить.")
    SET_TAGS_EMPTY = "Список тегов пуст."
    SET_TAGS_NEW = "Название нового тега"
    SET_TAGS_ADD = "Добавить"
    SET_TAG_USES = "в {n} задач."
    SET_TAG_RENAME = "Переименовать тег"
    SET_TAG_DELETE_TITLE = "Удалить тег"
    SET_TAG_DELETE_CONFIRM = 'Удалить тег «{name}» из {n} задач?'
    SET_TAG_EXISTS = "Тег с таким названием уже есть"

    SET_UPDATES = "Обновления"
    SET_CHECK_ON_START = "Проверять обновления при запуске"
    SET_CHECK_NOW = "Проверить сейчас"
    SET_DATA = "Данные"
    SET_OPEN_DATA_DIR = "Открыть папку с данными"
    SET_SAVED = "Настройки сохранены"

    # theme toggle button tooltip
    THEME_SWITCH = "Тема: {mode} → {next}"   # mode/next pre-localised by the caller

    # status bar
    SB_READY = "Готов"
    SB_TASKS = "Задач: {total}"
    SB_FOUND = "Найдено: {shown} из {total}"


class UPDATE:
    """Self-update prompts / progress (src/gui_flet/update_ui.py)."""
    ONLY_FROZEN = "Обновление доступно только в собранном приложении (.exe)"
    RATE_LIMITED = "GitHub временно ограничил запросы — попробуйте позже"
    NO_SERVER = "Нет доступа к серверу обновлений"
    NOT_READY = "Версия {version} опубликована, но файл сборки ещё не готов"
    UP_TO_DATE = "У вас последняя версия"
    SKIPPED = "Эта версия будет пропущена"
    AVAILABLE_TITLE = "Доступно обновление"
    NEW_VERSION = "Новая версия: {version}"
    CURRENT_VERSION = "Текущая: {current}"
    CONFIRM = "Загрузить и установить? Приложение перезапустится."
    BTN_SKIP = "Пропустить"
    BTN_LATER = "Позже"
    BTN_UPDATE = "Обновить"
    DOWNLOADING = "Загрузка…"
    DOWNLOADING_TO = "Обновление до {version}"
    KB = "{n} КБ"
    INSTALL_FAILED = "Не удалось установить обновление"
    INSTALLED_TITLE = "Обновление установлено"
    INSTALLED_BODY = "Приложение перезапускается…"


class NOTIFY:
    """Notification store (src/core/service_notifications.py)."""
    OVERDUE_TITLE = "Просрочено"
    OVERDUE_BODY = "{title} просрочена ({due})"
    DUE_SOON_TITLE = "Скоро дедлайн"
    DUE_SOON_BODY = "{title} — через {days} дн."


class ERR:
    """Validation / operation error messages."""
    DATE_FORMAT = "Формат даты: ГГГГ-ММ-ДД или ГГГГ-ММ-ДД ЧЧ:ММ"
    DUE_BEFORE_START = "Дедлайн должен быть не раньше даты начала"
    TITLE_REQUIRED = "Название обязательно"
    PICK_START_FIRST = "Сначала выберите дату начала"
    PICK_DUE_FIRST = "Сначала выберите дату дедлайна"
    TIME_FORMAT = "Время в формате ЧЧ:ММ (например 14:30)"
    HOURS_RANGE = "Введите число от 1 до 720"


class APP:
    """Single-instance / port handling (src/gui_flet/app.py)."""
    ALREADY_RUNNING = "Менеджер задач уже запущен: http://127.0.0.1:{port}/"
    KILLED_STALE = "Остановлен зависший экземпляр (PID {pid}) на порту {port}"
    PORT_BUSY = "Порт {port} занят другим приложением, запуск на {alt}"


# ── helpers ──

def status(value: str) -> str:
    return STATUS_LABEL.get(value, value)


def priority(value: str) -> str:
    return PRIORITY_LABEL.get(value, value)


def task_type(value: str) -> str:
    return TASK_TYPE_LABEL.get(value, value)


def urgency(value: str) -> str:
    return URGENCY_LABEL.get(value, value)


def status_style(value: str) -> tuple[str, str]:
    """(Material icon name, COLORS key) for a status value."""
    return STATUS_STYLE.get(value, ("radio_button_unchecked", "text_secondary"))


def type_color(value: str) -> str:
    return TYPE_COLOR.get(value, "#86868b")


def format_duration(hours: float) -> str:
    """A span of hours as a short RU label: ``45мин`` / ``2ч`` / ``1ч 30мин``."""
    if hours < 1:
        return f"{int(hours * 60)}{UNIT_MINUTES}"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}{UNIT_HOURS}" if m == 0 else f"{h}{UNIT_HOURS} {m}{UNIT_MINUTES}"
