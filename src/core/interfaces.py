"""
Interfaces for Dependency Inversion Principle (DIP).
Defines contracts that concrete implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any

from .models import Task


class ITaskRepository(ABC):
    """Interface for Task Data Access Layer."""
    
    @abstractmethod
    def get_all(self) -> List[Task]:
        """Get all tasks."""
        pass

    @abstractmethod
    def get_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        pass

    @abstractmethod
    def add(self, task: Task) -> Task:
        """Add a new task."""
        pass

    @abstractmethod
    def update(self, task: Task) -> Task:
        """Update an existing task."""
        pass

    @abstractmethod
    def delete(self, task_id: str) -> bool:
        """Delete task by ID."""
        pass


class IEventBus(ABC):
    """Interface for Event System."""
    
    @abstractmethod
    def subscribe(self, event_type: Any, callback: Callable[[Any], None]) -> None:
        """Subscribe to an event type."""
        pass

    @abstractmethod
    def unsubscribe(self, event_type: Any, callback: Callable[[Any], None]) -> None:
        """Unsubscribe from an event type."""
        pass

    @abstractmethod
    def publish(self, event: Any) -> None:
        """Publish an event to all subscribers."""
        pass
