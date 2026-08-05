"""
Task Manager - Event System for Reactive Updates
Implements Observer Pattern for decoupled communication
Python 3.14+ Compatible
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable
from collections import defaultdict


class EventType(Enum):
    """Типы событий в системе."""
    TASK_CREATED = auto()
    TASK_UPDATED = auto()
    TASK_DELETED = auto()
    STATUS_CHANGED = auto()
    DATA_REFRESHED = auto()


@dataclass
class Event:
    """Базовый класс события."""
    type: EventType
    data: dict = field(default_factory=dict)
    task_id: str | None = None
    
    @classmethod
    def task_event(cls, event_type: EventType, task_id: str, **kwargs) -> 'Event':
        """Создать событие связанное с задачей."""
        return cls(type=event_type, task_id=task_id, data=kwargs)


class EventBus:
    """
    Шина событий для реактивных обновлений.
    Реализует паттерн Observer/Pub-Sub.
    
    Пример использования:
        bus = EventBus()
        bus.subscribe(EventType.TASK_CREATED, handler_func)
        bus.publish(Event.task_event(EventType.TASK_CREATED, "task-123"))
    """
    
    _instance: 'EventBus | None' = None
    
    def __new__(cls) -> 'EventBus':
        """Singleton pattern - единая шина для всего приложения."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers = defaultdict(list)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'EventBus':
        """Получить экземпляр singleton."""
        return cls()
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Подписаться на событие."""
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Отписаться от события."""
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
    
    def publish(self, event: Event):
        """Опубликовать событие всем подписчикам."""
        for callback in self._subscribers.get(event.type, []):
            try:
                callback(event)
            except Exception as e:
                # Логирование ошибки но не прерывание цепочки
                import logging
                logging.getLogger(__name__).error(f"Event handler error: {e}")
    
    def clear(self):
        """Очистить все подписки (для тестов)."""
        self._subscribers.clear()


# Глобальный экземпляр шины событий
event_bus = EventBus()


__all__ = ['EventType', 'Event', 'EventBus', 'event_bus']
