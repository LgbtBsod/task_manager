"""
Task Manager - Modern Kanban Board
Core Domain Models
Python 3.14+ Compatible
"""
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
import uuid


class TaskStatus(Enum):
    """Статусы задачи для Kanban-доски."""
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class Priority(Enum):
    """Приоритеты задач с цветовой индикацией."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @property
    def color(self) -> str:
        """Возвращает цвет для приоритета."""
        colors = {
            Priority.LOW: "#4CAF50",      # Green
            Priority.MEDIUM: "#FF9800",   # Orange
            Priority.HIGH: "#F44336"      # Red
        }
        return colors[self]


@dataclass
class Task:
    """Модель задачи."""
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    due_date: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str | None = None
    id: str | None = None
    time_spent: float = 0.0  # часы
    start_date: str | None = None  # Для диаграммы Ганта

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())[:8]
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Десериализация из словаря."""
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        return cls(**data)

    def is_overdue(self) -> bool:
        """Проверка просрочки дедлайна."""
        if not self.due_date or self.status == TaskStatus.DONE:
            return False
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d")
            return due < datetime.now()
        except ValueError:
            return False

    def days_until_due(self) -> int | None:
        """Дней до дедлайна."""
        if not self.due_date:
            return None
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d")
            delta = due - datetime.now()
            return delta.days
        except ValueError:
            return None

    def update_timestamp(self):
        """Обновление временной метки изменения."""
        self.updated_at = datetime.now().isoformat()

    def get_gantt_start(self) -> str:
        """Получить дату начала для диаграммы Ганта."""
        return self.start_date or self.created_at[:10]

    def get_gantt_end(self) -> str:
        """Получить дату окончания для диаграммы Ганта."""
        if self.status == TaskStatus.DONE:
            return self.updated_at[:10]
        return self.due_date or (datetime.now().date() + timedelta(days=7)).isoformat()
