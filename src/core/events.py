"""
Task Manager - Event System for Reactive Updates
Implements Observer Pattern for decoupled communication
Python 3.14+ Compatible

Note: Using standard library instead of external pub-sub libraries (DRTTW)
- collections.defaultdict for subscriber storage
- dataclasses for Event model
- enum.Enum for type-safe event types
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any, Dict, List
from collections import defaultdict
import logging


# Configure module logger
logger = logging.getLogger(__name__)


class EventType(Enum):
    """Type-safe event types for the application.
    
    Using enum.Enum provides:
    - Autocompletion in IDEs
    - Type safety
    - Prevention of typos
    """
    TASK_CREATED = auto()
    TASK_UPDATED = auto()
    TASK_DELETED = auto()
    STATUS_CHANGED = auto()
    DATA_REFRESHED = auto()


@dataclass
class Event:
    """Immutable event object using dataclass (DRTTW - stdlib).
    
    Attributes:
        type: The type of event that occurred
        data: Additional event payload as dictionary
        task_id: Optional task identifier for task-related events
    """
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None
    
    @classmethod
    def task_event(cls, event_type: EventType, task_id: str, **kwargs) -> 'Event':
        """Factory method to create task-related events.
        
        Args:
            event_type: Type of the event
            task_id: ID of the related task
            **kwargs: Additional event data
            
        Returns:
            New Event instance with task context
        """
        return cls(type=event_type, task_id=task_id, data=kwargs)


class EventBus:
    """
    Event bus implementing Observer/Pub-Sub pattern.
    
    Uses standard library components (DRTTW):
    - defaultdict for subscriber storage
    - Singleton pattern for global event bus
    
    Example usage:
        bus = EventBus()
        bus.subscribe(EventType.TASK_CREATED, handler_func)
        bus.publish(Event.task_event(EventType.TASK_CREATED, "task-123"))
    """
    
    _instance: 'EventBus | None' = None
    
    def __new__(cls) -> 'EventBus':
        """Singleton pattern - single bus instance for the entire application."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: Dict[EventType, List[Callable[[Event], None]]] = defaultdict(list)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'EventBus':
        """Get the singleton instance."""
        return cls()
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Subscribe a callback to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event is published
        """
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Unsubscribe a callback from an event type.
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: Function to remove from subscribers
        """
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
    
    def publish(self, event: Event) -> None:
        """Publish an event to all subscribed callbacks.
        
        Args:
            event: Event object to publish
            
        Note:
            Errors in individual handlers are logged but don't stop
            the event propagation chain.
        """
        for callback in self._subscribers.get(event.type, []):
            try:
                callback(event)
            except Exception as e:
                # Log error but continue processing other handlers
                logger.error(f"Event handler error for {event.type}: {e}", exc_info=True)
    
    def clear(self) -> None:
        """Clear all subscriptions (useful for testing)."""
        self._subscribers.clear()


# Global singleton event bus instance (created on module import)
event_bus = EventBus()


__all__ = ['EventType', 'Event', 'EventBus', 'event_bus']
