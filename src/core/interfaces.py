"""
Interfaces for Dependency Inversion Principle (DIP).
Defines contracts that concrete implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from .models import Task, TaskID


class ITaskRepository(ABC):
    """Interface for Task Data Access Layer."""
    
    @abstractmethod
    def get_all(self) -> List[Task]:
        pass

    @abstractmethod
    def get_by_id(self, task_id: TaskID) -> Optional[Task]:
        pass

    @abstractmethod
    def add(self, task: Task) -> Task:
        pass

    @abstractmethod
    def update(self, task: Task) -> None:
        pass

    @abstractmethod
    def delete(self, task_id: TaskID) -> bool:
        pass


class IEventBus(ABC):
    """Interface for Event System."""
    
    @abstractmethod
    def subscribe(self, event_type: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def publish(self, event_type: str, data: dict) -> None:
        pass
