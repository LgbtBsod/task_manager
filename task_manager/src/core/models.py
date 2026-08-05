"""
Task Manager - Modern Kanban Board
Core Domain Models
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional
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
    due_date: Optional[str] = None
    created_at: str = None
    updated_at: str = None
    id: str = None
    time_spent: float = 0.0  # часы

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())[:8]
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
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

    def days_until_due(self) -> Optional[int]:
        """Дней до дедлайна."""
        if not self.due_date:
            return None
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d")
            delta = due - datetime.now()
            return delta.days
        except ValueError:
            return None
