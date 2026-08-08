"""
Task Manager - Modern Kanban Board
Repository Pattern for Data Persistence
Python 3.14+ Compatible

This module implements the Repository pattern to abstract data access,
allowing the business logic layer to work with domain objects without
knowing about storage details.

Principles:
- SRP: Only handles data persistence (load/save)
- DIP: Depends on abstractions (file path), not concrete implementations
- YAGNI: No unnecessary methods or complexity
"""
import json
import os
from pathlib import Path
from typing import Optional

from .models import Task, TaskStatus


class TaskRepository:
    """
    Repository for task data persistence using JSON storage.
    
    Implements the Repository pattern to provide a clean interface
    for CRUD operations on Task entities.
    
    Responsibilities:
    - Loading tasks from JSON file
    - Saving tasks to JSON file
    - Basic querying (by ID, by status)
    
    Not responsible for:
    - Business logic validation (handled by TaskService)
    - Data transformation (handled by TaskModel)
    
    Example usage:
        repo = TaskRepository("tasks.json")
        tasks = repo.get_all()
        task = repo.get_by_id("abc123")
        repo.add(new_task)
        repo.update(updated_task)
        repo.delete(task_id)
    """
    
    def __init__(self, db_path: str = "tasks.json"):
        """Initialize repository with database file path.
        
        Args:
            db_path: Path to JSON file for task storage
        """
        self.db_path = Path(db_path)
        self._ensure_db_exists()
    
    def _ensure_db_exists(self) -> None:
        """Create database file if it doesn't exist."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    def _load_tasks(self) -> list[dict]:
        """Load tasks from JSON file.
        
        Returns:
            List of task dictionaries, empty list if file is invalid/missing
        """
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_tasks(self, tasks: list[dict]) -> None:
        """Save tasks to JSON file.
        
        Args:
            tasks: List of task dictionaries to save
        """
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
    
    def get_all(self) -> list[Task]:
        """Retrieve all tasks from storage.
        
        Returns:
            List of Task domain objects
        """
        data = self._load_tasks()
        return [Task.from_dict(item) for item in data]
    
    def get_by_id(self, task_id: str) -> Optional[Task]:
        """Find task by unique identifier.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Task object if found, None otherwise
        """
        tasks = self.get_all()
        for task in tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_by_status(self, status: TaskStatus) -> list[Task]:
        """Filter tasks by status.
        
        Args:
            status: Task status to filter by
            
        Returns:
            List of tasks matching the status
        """
        tasks = self.get_all()
        return [t for t in tasks if t.status == status]
    
    def add(self, task: Task) -> Task:
        """Persist a new task.
        
        Args:
            task: Task object to add
            
        Returns:
            The added task with preserved ID
        """
        tasks = self._load_tasks()
        task_dict = task.to_dict()
        tasks.append(task_dict)
        self._save_tasks(tasks)
        return task
    
    def update(self, task: Task) -> Task:
        """Update an existing task.
        
        Args:
            task: Task object with updated data
            
        Returns:
            Updated task, or original if not found
        """
        tasks = self._load_tasks()
        for i, t in enumerate(tasks):
            if t['id'] == task.id:
                tasks[i] = task.to_dict()
                break
        self._save_tasks(tasks)
        return task
    
    def delete(self, task_id: str) -> bool:
        """Remove task by ID.
        
        Args:
            task_id: ID of task to delete
            
        Returns:
            True if task was deleted, False if not found
        """
        tasks = self._load_tasks()
        original_len = len(tasks)
        tasks = [t for t in tasks if t['id'] != task_id]
        if len(tasks) < original_len:
            self._save_tasks(tasks)
            return True
        return False
    
    def count(self) -> int:
        """Get total number of tasks.
        
        Returns:
            Number of tasks in storage
        """
        return len(self._load_tasks())
    
    def get_statistics(self) -> dict:
        """Calculate task statistics for dashboard.
        
        Returns:
            Dictionary containing:
            - total: Total task count
            - by_status: Count per status
            - by_priority: Count per priority
            - overdue: Count of overdue tasks
            - completion_rate: Percentage of completed tasks
            - total_time_spent: Sum of time spent on completed tasks
        """
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
        
        # Total time spent on completed tasks
        total_time = sum(t.time_spent for t in tasks if t.status == TaskStatus.DONE)
        
        return {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'overdue': overdue,
            'completion_rate': round(by_status['done'] / total * 100, 1) if total > 0 else 0,
            'total_time_spent': total_time
        }
