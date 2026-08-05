"""
Task Manager - Modern Kanban Board
Business Logic Service Layer
"""
from typing import List, Optional

from .models import Task, TaskStatus, Priority
from .repository import TaskRepository


class TaskService:
    """Сервис бизнес-логики для управления задачами."""
    
    def __init__(self, repository: Optional[TaskRepository] = None):
        self.repo = repository or TaskRepository()
    
    def create_task(
        self,
        title: str,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        due_date: Optional[str] = None
    ) -> Task:
        """Создание новой задачи."""
        if not title.strip():
            raise ValueError("Заголовок задачи не может быть пустым")
        
        task = Task(
            title=title.strip(),
            description=description.strip(),
            priority=priority,
            due_date=due_date
        )
        return self.repo.add(task)
    
    def get_all_tasks(self) -> List[Task]:
        """Получить все задачи."""
        return self.repo.get_all()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Получить задачу по ID."""
        return self.repo.get_by_id(task_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
        """Обновить статус задачи."""
        task = self.repo.get_by_id(task_id)
        if task:
            task.status = status
            return self.repo.update(task)
        return None
    
    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date: Optional[str] = None,
        time_spent: Optional[float] = None
    ) -> Optional[Task]:
        """Обновить задачу полностью."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        
        if title is not None:
            task.title = title.strip()
        if description is not None:
            task.description = description.strip()
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if time_spent is not None:
            task.time_spent = time_spent
        
        return self.repo.update(task)
    
    def delete_task(self, task_id: str) -> bool:
        """Удалить задачу."""
        return self.repo.delete(task_id)
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Получить задачи по статусу."""
        return self.repo.get_by_status(status)
    
    def get_statistics(self) -> dict:
        """Получить статистику для дашборда."""
        return self.repo.get_statistics()
    
    def get_overdue_tasks(self) -> List[Task]:
        """Получить просроченные задачи."""
        all_tasks = self.get_all_tasks()
        return [t for t in all_tasks if t.is_overdue()]
