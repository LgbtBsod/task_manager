"""
Task Manager - Modern Kanban Board
Business Logic Service Layer
Python 3.14+ Compatible

Using Pydantic for DTO validation (DRTTW)
"""

from .models import Task, TaskStatus, Priority, TaskModel
from .repository import TaskRepository
from .events import EventBus, EventType, Event, event_bus


class TaskService:
    """Сервис бизнес-логики для управления задачами.
    
    Реализует паттерн Domain Service с реактивными обновлениями через EventBus.
    
    Принципы:
    - SRP: Только бизнес-логика, валидация делегирована Pydantic
    - DRY: Переиспользуем Pydantic вместо самописных DTO
    - DRTTW: Используем готовую библиотеку Pydantic
    - YAGNI: Удалены избыточные DTO классы
    """
    
    def __init__(self, repository: TaskRepository | None = None, event_bus: EventBus | None = None):
        self.repo = repository or TaskRepository()
        # Use provided event_bus or fall back to global singleton
        self.event_bus = event_bus if event_bus is not None else EventBus()
    
    def create_task(self, title: str, description: str = "", priority: Priority = Priority.MEDIUM, due_date: str | None = None, start_date: str | None = None) -> Task:
        """Создание новой задачи с публикацией события и валидацией через Pydantic.
        
        Args:
            title: Заголовок задачи
            description: Описание
            priority: Приоритет
            due_date: Дедлайн (YYYY-MM-DD)
            start_date: Дата начала (YYYY-MM-DD)
        """
        # Валидация через Pydantic (DRTTW)
        try:
            task_model = TaskModel(
                title=title.strip(),
                description=description.strip(),
                priority=priority,
                due_date=due_date,
                start_date=start_date
            )
            task = task_model.to_task()
        except Exception as e:
            raise ValueError(f"Validation failed: {e}")
        
        created_task = self.repo.add(task)
        
        # Publish event for reactive updates
        self.event_bus.publish(Event.task_event(
            EventType.TASK_CREATED, 
            task_id=created_task.id,
            status=created_task.status.value
        ))
        
        return created_task
    
    def get_all_tasks(self) -> list[Task]:
        """Получить все задачи."""
        return self.repo.get_all()
    
    def get_task(self, task_id: str) -> Task | None:
        """Получить задачу по ID."""
        return self.repo.get_by_id(task_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        """Обновить статус задачи с публикацией события."""
        task = self.repo.get_by_id(task_id)
        if task:
            old_status = task.status
            task.status = status
            updated_task = self.repo.update(task)
            
            # Publish event for reactive updates
            self.event_bus.publish(Event.task_event(
                EventType.STATUS_CHANGED,
                task_id=task_id,
                old_status=old_status.value,
                new_status=status.value
            ))
            
            return updated_task
        return None
    
    def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        due_date: str | None = None,
        time_spent: float | None = None,
        start_date: str | None = None,
        status: TaskStatus | None = None
    ) -> Task | None:
        """Обновить задачу с публикацией события и валидацией через Pydantic."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        
        old_status = task.status
        
        # Обновляем поля
        if title is not None:
            task.title = title.strip()
        if description is not None:
            task.description = description.strip()
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if time_spent is not None:
            task.time_spent = max(0, time_spent)  # Неотрицательное значение
        if start_date is not None:
            task.start_date = start_date
        if status is not None:
            task.status = status
        
        # Валидация через Pydantic после обновления (DRTTW)
        try:
            task_model = TaskModel.from_task(task)
        except Exception as e:
            # Откат изменений при ошибке валидации
            raise ValueError(f"Validation failed: {e}")
        
        task.update_timestamp()
        updated_task = self.repo.update(task)
        
        # Publish event for reactive updates
        self.event_bus.publish(Event.task_event(
            EventType.TASK_UPDATED,
            task_id=task_id,
            old_status=old_status.value,
            new_status=status.value if status else old_status.value
        ))
        
        return updated_task
    
    def delete_task(self, task_id: str) -> bool:
        """Удалить задачу с публикацией события."""
        # Get task before deletion to know its status
        task = self.repo.get_by_id(task_id)
        if task:
            result = self.repo.delete(task_id)
            if result:
                # Publish event for reactive updates
                self.event_bus.publish(Event.task_event(
                    EventType.TASK_DELETED,
                    task_id=task_id,
                    status=task.status.value
                ))
            return result
        return False
    
    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Получить задачи по статусу."""
        return self.repo.get_by_status(status)
    
    def get_statistics(self) -> dict:
        """Получить статистику для дашборда."""
        return self.repo.get_statistics()
    
    def get_overdue_tasks(self) -> list[Task]:
        """Получить просроченные задачи."""
        all_tasks = self.get_all_tasks()
        return [t for t in all_tasks if t.is_overdue()]
