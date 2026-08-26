"""
Task Manager - Event System for Reactive Updates
Implements Observer Pattern for decoupled communication.
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any, Dict, List
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Type-safe event types."""
    TASK_CREATED = auto()
    TASK_UPDATED = auto()
    TASK_DELETED = auto()
    STATUS_CHANGED = auto()
    DATA_REFRESHED = auto()
    COMMENT_ADDED = auto()
    COMMENT_DELETED = auto()
    LINK_ADDED = auto()
    LINK_REMOVED = auto()
    SUBTASK_ADDED = auto()
    SUBTASK_TOGGLED = auto()
    SUBTASK_DELETED = auto()
    TASK_CLONED = auto()
    BULK_OPERATION = auto()


@dataclass
class Event:
    """Immutable event object."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None

    @classmethod
    def task_event(cls, event_type: EventType, task_id: str, **kwargs) -> 'Event':
        return cls(type=event_type, task_id=task_id, data=kwargs)


class EventBus:
    """Event bus implementing Observer/Pub-Sub pattern."""

    _instance: 'EventBus | None' = None

    def __new__(cls) -> 'EventBus':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: Dict[EventType, List[Callable[[Event], None]]] = defaultdict(list)
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'EventBus':
        return cls()

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        if callback in self._subscribers.get(event_type, []):
            self._subscribers[event_type].remove(callback)

    def publish(self, event: Event) -> None:
        for callback in self._subscribers.get(event.type, []):
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.type}: {e}", exc_info=True)

    def clear(self) -> None:
        self._subscribers.clear()


event_bus = EventBus()

__all__ = ['EventType', 'Event', 'EventBus', 'event_bus']
