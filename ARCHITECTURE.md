# 🏗️ Архитектура Task Manager Project

## 📋 Обзор архитектуры

Проект реализует **Clean Architecture** с чётким разделением слоёв и соблюдением принципов **SOLID**, **YAGNI**, **DRY**, и **DRTTW**.

---

## 🎯 Принципы проектирования

### ✅ SOLID Principles

#### 1. **SRP (Single Responsibility Principle)**
Каждый класс имеет одну ответственность:

| Класс | Ответственность |
|-------|----------------|
| `Task` | Хранение данных задачи |
| `TaskRepository` | CRUD операции с JSON-хранилищем |
| `TaskService` | Бизнес-логика и валидация |
| `EventBus` | Управление подписками на события |
| GUI компоненты | Отображение данных |

#### 2. **OCP (Open/Closed Principle)**
Система открыта для расширения через:
- Добавление новых типов событий в `EventType`
- Подписка новых обработчиков через `EventBus.subscribe()`
- Расширение GUI компонентов без изменения ядра

#### 3. **LSP (Liskov Substitution Principle)**
- `MockEventBus` может заменить `EventBus` для тестирования
- Все реализации следуют контракту интерфейса

#### 4. **ISP (Interface Segregation Principle)**
- Узкие специализированные классы вместо "божественных объектов"
- Каждый компонент решает свою задачу

#### 5. **DIP (Dependency Inversion Principle)**
```python
class TaskService:
    def __init__(self, repository: TaskRepository, event_bus: EventBus):
        self.repo = repository      # Абстракция
        self.event_bus = event_bus  # Абстракция
```
Зависимость от абстракций, а не от конкретных реализаций.

---

### ✅ SSOT (Single Source of Truth)

**EventBus** - глобальный singleton, единый источник истины для событий:

```python
bus1 = EventBus()
bus2 = EventBus()
assert bus1 is bus2  # True - один экземпляр на всё приложение
```

**TaskService** - единый источник истины для состояния задач.

---

### ✅ YAGNI (You Ain't Gonna Need It)

**Упрощения:**
- `validate_date()` использует стандартный `datetime.strptime()` вместо сложного regex
- Нет избыточных абстракций там, где они не нужны
- Минимальный набор методов для решения задач

**До:**
```python
# Сложный regex для валидации даты
pattern = r'^(?:(?:31(\/|-|\.)(?:0?[13578]|1[02]))\1|...)'
```

**После:**
```python
# Простая и надёжная проверка
try:
    datetime.strptime(date_str, "%Y-%m-%d")
    return True
except ValueError:
    return False
```

---

### ✅ DRY (Don't Repeat Yourself)

**Централизованные утилиты:**
- `format_time_spent()` - форматирование времени
- `get_working_days()` - расчёт рабочих дней
- `parse_date()` - парсинг дат
- `get_tasks_for_month()` - фильтрация по месяцам

**Переиспользуемые GUI компоненты:**
- `PrioritySelector` - выбор приоритета
- `DateEntry` - ввод даты
- `StatusBadge` - бейдж статуса
- `ActionButton` - стилизованные кнопки
- `CardFrame` - базовый класс карточек

**Константы:**
- `COLORS`, `FONTS`, `SPACING`, `RADIUS`, `DIMENSIONS` - в одном месте

---

### ✅ DRTTW (Don't Reinvent The Wheel)

Используем стандартные решения Python вместо изобретения велосипедов:

| Задача | Решение |
|--------|---------|
| Валидация дат | `datetime.strptime()` |
| Структуры данных | `dataclasses` |
| Перечисления | `enum.Enum` |
| Паттерн Observer | Собственная реализация Pub-Sub |
| UUID | `uuid.uuid4()` |

---

## 📁 Структура проекта

```
src/
├── __init__.py              # Документация архитектуры
├── core/                    # Domain Layer
│   ├── __init__.py          # Экспорт всех компонентов
│   ├── models.py            # Domain модели (Task, TaskStatus, Priority)
│   ├── repository.py        # Data Access Layer (CRUD)
│   ├── service.py           # Business Logic Layer + Event Publishing
│   └── events.py            # Event System (Observer Pattern)
├── gui/                     # Presentation Layer
│   ├── __init__.py          # Экспорт GUI компонентов
│   ├── main_window.py       # Main Application Window
│   ├── gantt_view.py        # Gantt Chart View
│   └── components.py        # Reusable UI Components
└── utils/                   # Infrastructure Layer
    └── helpers.py           # Utility functions
```

---

## 🔄 Event-Driven Architecture

### Схема взаимодействия

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   GUI       │─────▶│ TaskService  │─────▶│ Repository  │
│  Component  │      │   (Domain)   │      │   (Data)    │
└─────────────┘      └──────┬───────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   EventBus   │
                     │  (Singleton) │
                     └──────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │  Kanban  │  │ Dashboard│  │  Gantt   │
       │  Column  │  │  Widget  │  │   View   │
       └──────────┘  └──────────┘  └──────────┘
```

### Типы событий

```python
class EventType(Enum):
    TASK_CREATED = auto()     # Создание задачи
    TASK_UPDATED = auto()     # Обновление задачи
    TASK_DELETED = auto()     # Удаление задачи
    STATUS_CHANGED = auto()   # Изменение статуса
    DATA_REFRESHED = auto()   # Обновление данных
```

### Пример использования

```python
# Подписка на событие
def on_task_created(event: Event):
    print(f"Новая задача: {event.task_id}")

EventBus().subscribe(EventType.TASK_CREATED, on_task_created)

# Публикация события (внутри TaskService)
self.event_bus.publish(Event.task_event(
    EventType.TASK_CREATED,
    task_id=created_task.id,
    status=created_task.status.value
))
```

---

## 🧩 Паттерны проектирования

### 1. **Repository Pattern**
Изоляция доступа к данным:
```python
class TaskRepository:
    def add(self, task: Task) -> Task: ...
    def update(self, task: Task) -> Task: ...
    def delete(self, task_id: str) -> bool: ...
```

### 2. **Service Layer Pattern**
Бизнес-логика отделена от данных:
```python
class TaskService:
    def create_task(self, title: str, ...) -> Task:
        # Валидация
        # Бизнес-правила
        # Публикация событий
```

### 3. **Observer Pattern (Pub-Sub)**
Реактивные обновления через EventBus:
```python
class EventBus:
    def subscribe(self, event_type: EventType, callback: Callable): ...
    def publish(self, event: Event): ...
    def unsubscribe(self, event_type: EventType, callback: Callable): ...
```

### 4. **Singleton Pattern**
Единый экземпляр EventBus для всего приложения:
```python
class EventBus:
    _instance: 'EventBus | None' = None
    
    def __new__(cls) -> 'EventBus':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

### 5. **Component Pattern**
Переиспользуемые UI компоненты с Dependency Injection:
```python
class PrioritySelector(ctk.CTkFrame):
    def __init__(self, parent, on_change: Callable, initial_value: str):
        # Инкапсуляция логики выбора приоритета
```

---

## ⚡ Перформанс

### Оптимизации

1. **Селективное обновление**
   - Обновляются только затронутые колонки вместо полной перерисовки
   - Метод `_refresh_affected_columns()` вместо `_refresh_board()`

2. **Кэширование ссылок**
   ```python
   self._columns: dict[TaskStatus, KanbanColumn] = {}
   ```

3. **Отложенные обновления UI**
   ```python
   self.after(100, lambda: self._refresh_affected_columns(task_id))
   ```

4. **Ленивая загрузка**
   - Компоненты создаются только при необходимости

---

## 🧪 Тестирование

Все принципы подтверждены тестами:

```bash
✓ SRP: Task отвечает только за данные
✓ SRP: Repository отвечает только за хранение
✓ SRP: Service отвечает только за бизнес-логику
✓ SSOT: EventBus - единый источник истины (singleton)
✓ YAGNI: validate_date упрощён без over-engineering
✓ DRY: format_time_spent переиспользуется
✓ DIP: TaskService принимает абстракцию EventBus
✓ OCP: Система открыта для расширения через подписчиков
✓ Observer Pattern: события публикуются корректно
```

---

## 📊 Метрики качества

| Принцип | Статус | Доказательство |
|---------|--------|----------------|
| **SRP** | ✅ | 5 классов с одной ответственностью |
| **OCP** | ✅ | Расширение через подписчиков |
| **DIP** | ✅ | Внедрение зависимостей через конструктор |
| **SSOT** | ✅ | EventBus singleton |
| **YAGNI** | ✅ | Упрощённая валидация дат |
| **DRY** | ✅ | Централизованные утилиты и компоненты |
| **DRTTW** | ✅ | Стандартные решения Python |

---

## 🚀 Рекомендации для дальнейшего развития

1. **Добавить кэширование** для часто используемых запросов
2. **Внедрить логирование** через `logging` модуль
3. **Добавить аннотации типов** для лучшей IDE поддержки
4. **Расширить тесты** с покрытием > 80%
5. **Добавить CI/CD** пайплайн для автоматического тестирования

---

## 📝 Заключение

Архитектура проекта соответствует лучшим практикам разработки ПО:
- ✅ Чистое разделение слоёв
- ✅ Соблюдение SOLID принципов
- ✅ Реактивная архитектура через EventBus
- ✅ Переиспользуемые компоненты
- ✅ Оптимальная производительность

**Проект готов к масштабированию и расширению функциональности!**
