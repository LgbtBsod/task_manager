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
