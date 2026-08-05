"""
Task Manager - Modern Kanban Board
Core Domain Models
Python 3.14+ Compatible

Using Pydantic for validation (DRTTW - Don't Reinvent The Wheel)
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import ValidationError

# Type alias for task ID
TaskID = str


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
        match self:
            case Priority.LOW:
                return "#4CAF50"      # Green
            case Priority.MEDIUM:
                return "#FF9800"      # Orange
            case Priority.HIGH:
                return "#F44336"      # Red


class TaskModel(BaseModel):
    """
    Pydantic модель для валидации данных задачи.
    
    Принципы:
    - DRTTW: Используем готовую библиотеку Pydantic вместо самописных валидаторов
    - SRP: Отдельный класс только для валидации
    - DRY: Переиспользуем встроенные возможности Pydantic
    - YAGNI: Не создаём избыточные правила валидации
    """
    
    title: str = Field(..., min_length=1, max_length=200, description="Заголовок задачи")
    description: str = Field(default="", max_length=5000, description="Описание задачи")
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: Priority = Field(default=Priority.MEDIUM)
    due_date: Optional[str] = Field(default=None, description="Дедлайн (YYYY-MM-DD)")
    start_date: Optional[str] = Field(default=None, description="Дата начала (YYYY-MM-DD)")
    time_spent: float = Field(default=0.0, ge=0, description="Затраченное время в часах")
    
    @field_validator('due_date', 'start_date')
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        """Валидация формата даты через Pydantic (DRTTW)."""
        match v:
            case None:
                return v
            case date_str:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    raise ValueError("Invalid date format. Use YYYY-MM-DD")
    
    @model_validator(mode='after')
    def validate_dates_consistency(self) -> 'TaskModel':
        """Проверка согласованности дат."""
        match (self.start_date, self.due_date):
            case (start, due) if start and due:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                due_dt = datetime.strptime(due, "%Y-%m-%d")
                if due_dt < start_dt:
                    raise ValueError("Due date must be after start date")
        return self
    
    def to_task(self) -> 'Task':
        """Конвертация в Task dataclass."""
        return Task(
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            due_date=self.due_date,
            start_date=self.start_date,
            time_spent=self.time_spent
        )
    
    @classmethod
    def from_task(cls, task: 'Task') -> 'TaskModel':
        """Создание из Task dataclass."""
        return cls(
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            start_date=task.start_date,
            time_spent=task.time_spent
        )


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
        match self.id:
            case None:
                self.id = str(uuid.uuid4())[:8]
            case _:
                pass
        
        match self.updated_at:
            case None:
                self.updated_at = datetime.now().isoformat()
            case _:
                pass
        
        # Валидация через Pydantic при создании (DRTTW)
        try:
            model = TaskModel.from_task(self)
        except ValidationError as e:
            raise ValueError(f"Task validation failed: {e}")

    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Десериализация из словаря с валидацией."""
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        
        # Валидация через Pydantic перед созданием (DRTTW)
        try:
            model = TaskModel(**data)
            return model.to_task()
        except ValidationError as e:
            raise ValueError(f"Task validation failed: {e}")

    def is_overdue(self) -> bool:
        """Проверка просрочки дедлайна."""
        match (self.due_date, self.status):
            case (None, _) | (_, TaskStatus.DONE):
                return False
            case (due, _):
                try:
                    due_date = datetime.strptime(due, "%Y-%m-%d")
                    return due_date < datetime.now()
                except ValueError:
                    return False

    def days_until_due(self) -> int | None:
        """Дней до дедлайна."""
        match self.due_date:
            case None:
                return None
            case due:
                try:
                    due_date = datetime.strptime(due, "%Y-%m-%d")
                    delta = due_date - datetime.now()
                    return delta.days
                except ValueError:
                    return None

    def update_timestamp(self):
        """Обновление временной метки изменения."""
        self.updated_at = datetime.now().isoformat()

    def get_gantt_start(self) -> str:
        """Получить дату начала для диаграммы Ганта."""
        match self.start_date:
            case start if start:
                return start
            case _:
                # Если нет start_date, используем дату создания
                return self.created_at[:10]

    def get_gantt_end(self) -> str:
        """Получить дату окончания для диаграммы Ганта."""
        from datetime import timedelta
        
        match self.status:
            case TaskStatus.DONE if self.updated_at:
                end_date = self.updated_at[:10]
            case _ if self.due_date:
                end_date = self.due_date
            case _:
                start = self.get_gantt_start()
                try:
                    start_dt = datetime.strptime(start, "%Y-%m-%d")
                    end_date = (start_dt + timedelta(days=7)).isoformat()[:10]
                except ValueError:
                    end_date = (datetime.now().date() + timedelta(days=7)).isoformat()
        
        # Гарантируем, что end_date >= start_date
        start_date = self.get_gantt_start()
        return start_date if end_date < start_date else end_date
