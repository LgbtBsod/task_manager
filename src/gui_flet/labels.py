"""Russian display labels.

The domain layer stores enum *values* in English ("Todo", "High", "Bug", …)
so the data schema and every status/priority map keep working. The GUI shows
these labels instead; each accessor falls back to the raw value when unknown.
"""

APP_TITLE = "Менеджер задач"

NAV = {
    "kanban": "Доска",
    "gantt": "Гант",
    "dashboard": "Обзор",
}

STATUS = {
    "Todo": "К выполнению",
    "In Progress": "В работе",
    "Done": "Готово",
}

PRIORITY = {
    "Low": "Низкий",
    "Medium": "Средний",
    "High": "Высокий",
    "Critical": "Критический",
}

TASK_TYPE = {
    "Task": "Задача",
    "Bug": "Ошибка",
    "Story": "История",
    "Epic": "Эпик",
    "Sub-task": "Подзадача",
}

URGENCY = {
    "Low": "Низкая",
    "Normal": "Обычная",
    "High": "Высокая",
    "Urgent": "Срочная",
}

# status value -> (Material icon name, COLORS key). Used by the board columns,
# the gantt rows and the dashboard "по статусу" bars so they stay in step.
STATUS_STYLE = {
    "Todo":        ("radio_button_unchecked", "accent_blue"),
    "In Progress": ("pending",                "accent_orange"),
    "Done":        ("check_circle",            "accent_green"),
}

# task-type value -> chip / bar colour (hex, theme-independent).
TYPE_COLOR = {
    "Task": "#86868b", "Bug": "#ff453a", "Story": "#bf5af2",
    "Epic": "#ff9f0a", "Sub-task": "#30d158",
}

# Short unit labels used on cards / gantt bars
UNIT_DAYS = "дн."
UNIT_HOURS = "ч"
UNIT_MINUTES = "мин"
STORY_POINTS = "ОИ"  # очки истории (Story Points)


def format_duration(hours: float) -> str:
    """A span of hours as a short RU label: ``45мин`` / ``2ч`` / ``1ч 30мин``."""
    if hours < 1:
        return f"{int(hours * 60)}{UNIT_MINUTES}"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}{UNIT_HOURS}" if m == 0 else f"{h}{UNIT_HOURS} {m}{UNIT_MINUTES}"

def status(value: str) -> str:
    return STATUS.get(value, value)


def priority(value: str) -> str:
    return PRIORITY.get(value, value)


def task_type(value: str) -> str:
    return TASK_TYPE.get(value, value)


def urgency(value: str) -> str:
    return URGENCY.get(value, value)


def status_style(value: str) -> tuple[str, str]:
    """(Material icon name, COLORS key) for a status value."""
    return STATUS_STYLE.get(value, ("radio_button_unchecked", "text_secondary"))


def type_color(value: str) -> str:
    return TYPE_COLOR.get(value, "#86868b")
