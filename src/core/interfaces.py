"""
Interfaces for Dependency Inversion Principle (DIP).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any

from .models import Task


class ITaskRepository(ABC):
    """Interface for Task Data Access Layer."""

    @abstractmethod
    def get_all(self) -> List[Task]:
        pass

    @abstractmethod
    def get_by_id(self, task_id: str) -> Optional[Task]:
        pass

    @abstractmethod
    def get_by_status(self, status: Any) -> List[Task]:
        pass

    @abstractmethod
    def add(self, task: Task) -> Task:
        pass

    @abstractmethod
    def update(self, task: Task) -> Task:
        pass

    @abstractmethod
    def delete(self, task_id: str) -> bool:
        pass

    @abstractmethod
    def count(self) -> int:
        pass

    @abstractmethod
    def get_statistics(self) -> dict:
        pass


class IEventBus(ABC):
    """Interface for Event System."""

    @abstractmethod
    def subscribe(self, event_type: Any, callback: Callable[[Any], None]) -> None:
        pass

    @abstractmethod
    def unsubscribe(self, event_type: Any, callback: Callable[[Any], None]) -> None:
        pass

    @abstractmethod
    def publish(self, event: Any) -> None:
        pass
