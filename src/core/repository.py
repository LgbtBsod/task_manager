"""
Task Manager - Modern Kanban Board
Repository Pattern for Data Persistence
Python 3.14+ Compatible
"""
import json
import os
from pathlib import Path

from .models import Task, TaskStatus


class TaskRepository:
    """Репозиторий для работы с задачами (JSON-хранилище)."""
    
    def __init__(self, db_path: str = "tasks.json"):
        self.db_path = Path(db_path)
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Создание файла БД если не существует."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    def _load_tasks(self) -> list[dict]:
        """Загрузка задач из файла."""
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_tasks(self, tasks: list[dict]):
        """Сохранение задач в файл."""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
    
    def get_all(self) -> list[Task]:
        """Получить все задачи."""
        data = self._load_tasks()
        return [Task.from_dict(item) for item in data]
    
    def get_by_id(self, task_id: str) -> Task | None:
        """Получить задачу по ID."""
        tasks = self.get_all()
        for task in tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_by_status(self, status: TaskStatus) -> list[Task]:
        """Получить задачи по статусу."""
        tasks = self.get_all()
        return [t for t in tasks if t.status == status]
    
    def add(self, task: Task) -> Task:
        """Добавить новую задачу."""
        tasks = self._load_tasks()
        tasks.append(task.to_dict())
        self._save_tasks(tasks)
        return task
    
    def update(self, task: Task) -> Task:
        """Обновить существующую задачу."""
        tasks = self._load_tasks()
        for i, t in enumerate(tasks):
            if t['id'] == task.id:
                tasks[i] = task.to_dict()
                break
        self._save_tasks(tasks)
        return task
    
    def delete(self, task_id: str) -> bool:
        """Удалить задачу по ID."""
        tasks = self._load_tasks()
        original_len = len(tasks)
        tasks = [t for t in tasks if t['id'] != task_id]
        if len(tasks) < original_len:
            self._save_tasks(tasks)
            return True
        return False
    
    def count(self) -> int:
        """Количество задач."""
        return len(self._load_tasks())
    
    def get_statistics(self) -> dict:
        """Статистика для дашборда."""
        tasks = self.get_all()
        total = len(tasks)
        
        by_status = {
            'todo': len([t for t in tasks if t.status == TaskStatus.TODO]),
            'in_progress': len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            'done': len([t for t in tasks if t.status == TaskStatus.DONE])
        }
        
        by_priority = {
            'low': len([t for t in tasks if t.priority.name == 'LOW']),
            'medium': len([t for t in tasks if t.priority.name == 'MEDIUM']),
            'high': len([t for t in tasks if t.priority.name == 'HIGH'])
        }
        
        overdue = len([t for t in tasks if t.is_overdue()])
        
        # Время выполнения (суммарно по завершённым)
        total_time = sum(t.time_spent for t in tasks if t.status == TaskStatus.DONE)
        
        return {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'overdue': overdue,
            'completion_rate': round(by_status['done'] / total * 100, 1) if total > 0 else 0,
            'total_time_spent': total_time
        }
