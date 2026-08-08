"""
Task Manager - Modern Kanban Board
Business Logic Service Layer
Python 3.14+ Compatible

This module implements the Domain Service pattern, orchestrating business logic
between domain models (Task) and data access layer (Repository).

Principles:
- SRP: Only handles business logic, validation delegated to Pydantic
- DRY: Reuses Pydantic for DTO validation instead of custom code
- DRTTW: Uses established Pydantic library
- YAGNI: Removed excessive DTO classes
- DIP: Depends on repository abstraction, not concrete implementation
"""

from typing import Optional

from .models import Task, TaskStatus, Priority, TaskModel
from .repository import TaskRepository
from .events import EventBus, EventType, Event, event_bus


class TaskService:
    """
    Business logic service for task management.
    
    Implements the Domain Service pattern with reactive updates via EventBus.
    
    Responsibilities:
    - Task creation with validation
    - Task status transitions
    - Task updates with validation
    - Task deletion
    - Statistics calculation
    
    Not responsible for:
    - Data persistence (handled by TaskRepository)
    - Data validation schema (handled by TaskModel/Pydantic)
    - UI rendering (handled by GUI components)
    
    Example usage:
        service = TaskService()
        task = service.create_task("My Task", priority=Priority.HIGH)
        service.update_task_status(task.id, TaskStatus.IN_PROGRESS)
        stats = service.get_statistics()
    """
    
    def __init__(self, repository: Optional[TaskRepository] = None, event_bus: Optional[EventBus] = None):
        """Initialize service with optional custom repository and event bus.
        
        Args:
            repository: Custom task repository (default: TaskRepository())
            event_bus: Custom event bus for reactive updates (default: singleton)
        """
        self.repo = repository or TaskRepository()
        # Use provided event_bus or fall back to global singleton
        self.event_bus = event_bus if event_bus is not None else EventBus()
    
    def create_task(
        self, 
        title: str, 
        description: str = "", 
        priority: Priority = Priority.MEDIUM, 
        due_date: Optional[str] = None, 
        start_date: Optional[str] = None
    ) -> Task:
        """Create a new task with validation and event publication.
        
        Args:
            title: Task title (required, will be stripped)
            description: Optional task description
            priority: Task priority level (default: MEDIUM)
            due_date: Optional due date in YYYY-MM-DD format
            start_date: Optional start date for Gantt chart
            
        Returns:
            Created task with generated ID
            
        Raises:
            ValueError: If validation fails
        """
        # Validate using Pydantic (DRTTW)
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
        """Retrieve all tasks from storage.
        
        Returns:
            List of all tasks
        """
        return self.repo.get_all()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Find task by unique identifier.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Task if found, None otherwise
        """
        return self.repo.get_by_id(task_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
        """Update task status with event publication.
        
        Args:
            task_id: ID of task to update
            status: New status value
            
        Returns:
            Updated task if found, None otherwise
        """
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
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date: Optional[str] = None,
        time_spent: Optional[float] = None,
        start_date: Optional[str] = None,
        status: Optional[TaskStatus] = None
    ) -> Optional[Task]:
        """Update task fields with validation and event publication.
        
        Args:
            task_id: ID of task to update
            title: New title (optional)
            description: New description (optional)
            priority: New priority (optional)
            due_date: New due date (optional)
            time_spent: New time spent in hours (optional, must be >= 0)
            start_date: New start date (optional)
            status: New status (optional)
            
        Returns:
            Updated task if found, None otherwise
            
        Raises:
            ValueError: If validation fails after updates
        """
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        
        old_status = task.status
        
        # Update fields
        if title is not None:
            task.title = title.strip()
        if description is not None:
            task.description = description.strip()
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if time_spent is not None:
            task.time_spent = max(0, time_spent)  # Ensure non-negative
        if start_date is not None:
            task.start_date = start_date
        if status is not None:
            task.status = status
        
        # Validate using Pydantic after updates (DRTTW)
        try:
            task_model = TaskModel.from_task(task)
        except Exception as e:
            # Rollback on validation error
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
        """Delete task with event publication.
        
        Args:
            task_id: ID of task to delete
            
        Returns:
            True if deleted, False if not found
        """
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
        """Filter tasks by status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of tasks matching the status
        """
        return self.repo.get_by_status(status)
    
    def get_statistics(self) -> dict:
        """Get dashboard statistics.
        
        Returns:
            Dictionary with task statistics
        """
        return self.repo.get_statistics()
    
    def get_overdue_tasks(self) -> list[Task]:
        """Get all overdue tasks.
        
        Returns:
            List of tasks past their due date
        """
        all_tasks = self.get_all_tasks()
        return [t for t in all_tasks if t.is_overdue()]
