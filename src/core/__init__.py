"""
Task Manager - Core Module Init

Архитектура:
- models.py: Domain Entities (Task, TaskStatus, Priority) + Pydantic модель для валидации
- interfaces.py: Абстракции (ITaskRepository, IEventBus)
- repository.py: Data Access Layer
- service.py: Business Logic Layer + Event Publishing
- events.py: Event-Driven Architecture (Observer Pattern)

Принципы:
- DRTTW: Используем Pydantic вместо самописных DTO и валидаторов
- SRP: Каждый класс имеет одну ответственность
- YAGNI: Удалены избыточные модули (dto, validators, factories)
- DRY: Валидация через Pydantic переиспользуется везде
"""
from .models import Task, TaskStatus, Priority, TaskModel
from .repository import TaskRepository
from .service import TaskService
from .events import EventBus, EventType, Event, event_bus
from .interfaces import ITaskRepository, IEventBus

__all__ = [
    # Models
    'Task', 
    'TaskStatus', 
    'Priority',
    'TaskModel',  # Pydantic модель для валидации
    
    # Interfaces
    'ITaskRepository',
    'IEventBus',
    
    # Implementation
    'TaskRepository', 
    'TaskService',
    
    # Events
    'EventBus',
    'EventType',
    'Event',
    'event_bus',
]
