# 🏗️ Архитектура проекта Task Manager

## Обзор архитектуры

Проект реализует **Clean Architecture** с чётким разделением слоёв и соблюдением принципов SOLID.

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  (src/gui/)                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ main_window  │  │ gantt_view   │  │ components   │       │
│  │ .py          │  │ .py          │  │ .py          │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                   BUSINESS LOGIC LAYER                       │
│  (src/core/)                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ service.py   │  │ events.py    │  │ interfaces.py│       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                   DATA ACCESS LAYER                          │
│  (src/core/)                                                 │
│  ┌──────────────┐                                            │
│  │ repository.py│                                            │
│  └──────────────┘                                            │
├─────────────────────────────────────────────────────────────┤
│                     DOMAIN LAYER                             │
│  (src/core/)                                                 │
│  ┌──────────────┐                                            │
│  │ models.py    │                                            │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

## Принципы проектирования

### ✅ SOLID

#### SRP (Single Responsibility Principle)
Каждый класс имеет одну ответственность:

| Класс | Ответственность |
|-------|----------------|
| `Task` | Хранение данных задачи и методы для работы с ними |
| `TaskRepository` | CRUD операции с хранилищем (JSON) |
| `TaskService` | Бизнес-логика и координация операций |
| `EventBus` | Управление подписками и публикация событий |
| GUI компоненты | Отображение данных и взаимодействие с пользователем |

#### OCP (Open/Closed Principle)
Система открыта для расширения, закрыта для модификации:

```python
# Можно добавлять новые типы событий без изменения ядра
class EventType(Enum):
    TASK_CREATED = auto()
    TASK_UPDATED = auto()
    NEW_EVENT_TYPE = auto()  # Новое событие без изменения существующего кода

# Можно добавлять новых подписчиков без изменения издателей
event_bus.subscribe(EventType.NEW_EVENT_TYPE, new_handler)
```

#### LSP (Liskov Substitution Principle)
Подклассы могут заменять базовые классы:

```python
# Интерфейс
class ITaskRepository(ABC):
    @abstractmethod
    def get_all(self) -> List[Task]: ...
    
# Реализация
class TaskRepository(ITaskRepository):
    def get_all(self) -> List[Task]:
        # Конкретная реализация
        pass

# Mock для тестов
class MockRepository(ITaskRepository):
    def get_all(self) -> List[Task]:
        return []  # Заглушка для тестов
```

#### ISP (Interface Segregation Principle)
Узкоспециализированные интерфейсы:

```python
# ITaskRepository - только 5 методов для работы с задачами
class ITaskRepository(ABC):
    def get_all(self) -> List[Task]: ...
    def get_by_id(self, task_id: str) -> Optional[Task]: ...
    def add(self, task: Task) -> Task: ...
    def update(self, task: Task) -> None: ...
    def delete(self, task_id: str) -> bool: ...

# IEventBus - только 3 метода для работы с событиями
class IEventBus(ABC):
    def subscribe(self, event_type: str, callback: Callable) -> None: ...
    def unsubscribe(self, event_type: str, callback: Callable) -> None: ...
    def publish(self, event_type: str, data: dict) -> None: ...
```

#### DIP (Dependency Inversion Principle)
Зависимость от абстракций, внедрение зависимостей:

```python
class TaskService:
    def __init__(
        self, 
        repository: ITaskRepository,  # Абстракция, а не конкретный класс
        event_bus: IEventBus | None = None
    ):
        self.repo = repository
        self.event_bus = event_bus or EventBus.get_instance()
```

### ✅ Архитектурные принципы

#### SSOT (Single Source of Truth)
Единые источники истины:

- **EventBus** - глобальный singleton для всей системы событий
- **TaskService** - единый источник истины для состояния задач
- **TaskRepository** - единственное место доступа к данным

```python
# Singleton паттерн для EventBus
class EventBus:
    _instance: 'EventBus | None' = None
    
    def __new__(cls) -> 'EventBus':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers = defaultdict(list)
        return cls._instance
```

#### DRY (Don't Repeat Yourself)
Централизованная логика:

- `helpers.py` - переиспользуемые функции (`validate_date`, `get_tasks_for_month`)
- `models.py` - инкапсулированная логика дат (`get_gantt_start`, `get_gantt_end`)
- `components.py` - переиспользуемые UI компоненты

#### YAGNI (You Ain't Gonna Need It)
Нет избыточной функциональности:

```python
# Было (избыточно):
def validate_date(date_str):
    regex = r'^\d{4}-\d{2}-\d{2}$'
    # Сложная логика с regex...

# Стало (просто и достаточно):
def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False
```

#### DRTTW (Don't Reinvent The Wheel)
Используем стандартные решения Python:

- `dataclasses` для моделей данных
- `Enum` для типов событий и статусов
- `ABC` (Abstract Base Classes) для интерфейсов
- Стандартный паттерн Observer/Pub-Sub
- Встроенный `datetime.strptime()` для валидации дат

## Паттерны проектирования

### 1. Repository Pattern
Изоляция доступа к данным:

```python
class TaskRepository:
    """Единственное место для работы с хранилищем."""
    
    def get_all(self) -> List[Task]: ...
    def add(self, task: Task) -> Task: ...
    def update(self, task: Task) -> Task: ...
    def delete(self, task_id: str) -> bool: ...
```

**Преимущества:**
- Легко заменить хранилище (JSON → SQL → NoSQL)
- Упрощённое тестирование (Mock Repository)
- Бизнес-логика не зависит от способа хранения

### 2. Service Layer Pattern
Бизнес-логика отделена от данных:

```python
class TaskService:
    """Координация операций и бизнес-правила."""
    
    def create_task(self, title: str, ...) -> Task:
        # Валидация
        # Создание задачи
        # Публикация события
        
    def update_task_status(self, task_id: str, status: TaskStatus):
        # Проверка прав
        # Обновление статуса
        # Публикация события
```

**Преимущества:**
- Централизованная бизнес-логика
- Транзакционность операций
- Легко тестировать отдельно от GUI

### 3. Observer Pattern (Event-Driven Architecture)
Реактивные обновления через шину событий:

```python
# Публикация события
self.event_bus.publish(Event.task_event(
    EventType.TASK_CREATED,
    task_id=created_task.id
))

# Подписка на событие
event_bus.subscribe(EventType.TASK_CREATED, self._on_task_created)
```

**Типы событий:**
- `TASK_CREATED` - создана новая задача
- `TASK_UPDATED` - обновлена задача
- `TASK_DELETED` - удалена задача
- `STATUS_CHANGED` - изменён статус
- `DATA_REFRESHED` - обновлены данные

**Преимущества:**
- Слабая связанность компонентов
- Автоматическое обновление UI
- Легко добавлять новых подписчиков

### 4. Singleton Pattern
Единый экземпляр шины событий:

```python
bus1 = EventBus()
bus2 = EventBus()
assert bus1 is bus2  # Один экземпляр на всё приложение
```

### 5. Component Pattern
Переиспользуемые UI компоненты:

```python
# components.py
class PrioritySelector(ctk.CTkFrame): ...
class DateEntry(ctk.CTkEntry): ...
class StatusBadge(ctk.CTkLabel): ...
class ActionButton(ctk.CTkButton): ...
```

**Преимущества:**
- Консистентный дизайн
- Переиспользование кода
- Упрощённая поддержка

### 6. Dependency Injection
Внедрение зависимостей через конструктор:

```python
# Внедрение реальных зависимостей
service = TaskService(TaskRepository(), EventBus())

# Внедрение mock для тестов
service = TaskService(MockRepository(), MockEventBus())
```

## Структура проекта

```
src/
├── __init__.py              # Документация архитектуры
├── core/                    # Domain + Business Logic
│   ├── __init__.py          # Экспорт публичного API
│   ├── models.py            # Domain модели (Task, TaskStatus, Priority)
│   ├── repository.py        # Data Access Layer (TaskRepository)
│   ├── service.py           # Business Logic Layer (TaskService)
│   ├── events.py            # Event System (EventBus, Event, EventType)
│   └── interfaces.py        # Абстракции (ITaskRepository, IEventBus)
├── gui/                     # Presentation Layer
│   ├── __init__.py          # Экспорт GUI компонентов
│   ├── main_window.py       # Главное окно приложения
│   ├── gantt_view.py        # Диаграмма Ганта
│   └── components.py        # Переиспользуемые компоненты
└── utils/                   # Utilities
    ├── __init__.py
    └── helpers.py           # Вспомогательные функции
```

## Производительность

### Оптимизации

1. **Селективное обновление**
   - Обновляются только затронутые колонки, а не вся доска
   - Метод `_refresh_affected_columns()` вместо полного `_refresh_board()`

2. **Кэширование ссылок**
   - `self._columns` словарь для быстрого доступа к колонкам
   - Не нужно искать виджеты каждый раз

3. **Отложенные обновления UI**
   - Использование `after(100, ...)` для неблокирующих операций
   - UI не зависает при операциях

4. **Ленивая загрузка**
   - Компоненты создаются только когда нужны
   - Экономия памяти и времени запуска

## Расширяемость

### Добавление нового типа события

```python
# 1. Добавить тип события в events.py
class EventType(Enum):
    TASK_ASSIGNED = auto()  # Новое событие

# 2. Опубликовать событие в service.py
self.event_bus.publish(Event.task_event(
    EventType.TASK_ASSIGNED,
    task_id=task.id,
    assigned_user=user_id
))

# 3. Подписаться в GUI
event_bus.subscribe(EventType.TASK_ASSIGNED, self._on_task_assigned)
```

### Добавление нового хранилища

```python
# 1. Реализовать интерфейс ITaskRepository
class SQLTaskRepository(ITaskRepository):
    def __init__(self, connection_string: str):
        self.conn = create_connection(connection_string)
    
    def get_all(self) -> List[Task]:
        # SQL реализация
        pass
    
    # Остальные методы...

# 2. Внедрить в сервис
repo = SQLTaskRepository("postgresql://...")
service = TaskService(repo, EventBus())
```

### Добавление нового UI компонента

```python
# components.py
class TaskCard(ctk.CTkFrame):
    """Карточка задачи с переиспользуемым дизайном."""
    
    def __init__(self, parent, task: Task, on_click: Callable):
        super().__init__(parent)
        self.task = task
        self.on_click = on_click
        self._render()
```

## Тестирование

### Модульные тесты

```python
def test_create_task_publishes_event():
    mock_repo = MockRepository()
    mock_bus = MockEventBus()
    service = TaskService(mock_repo, mock_bus)
    
    service.create_task("Test Task")
    
    assert mock_bus.published_events
    assert mock_bus.published_events[0].type == EventType.TASK_CREATED
```

### Интеграционные тесты

```python
def test_full_workflow():
    repo = TaskRepository(":memory:")
    service = TaskService(repo)
    
    # Создание
    task = service.create_task("Test")
    assert task.id is not None
    
    # Обновление статуса
    updated = service.update_task_status(task.id, TaskStatus.DONE)
    assert updated.status == TaskStatus.DONE
    
    # Удаление
    result = service.delete_task(task.id)
    assert result is True
```

## Заключение

Архитектура проекта соответствует лучшим практикам разработки ПО:

✅ **SOLID** - все 5 принципов соблюдены  
✅ **SSOT** - единые источники истины  
✅ **DRY** - нет дублирования кода  
✅ **YAGNI** - нет избыточной функциональности  
✅ **DRTTW** - стандартные решения Python  

🎯 **Паттерны**: Repository, Service Layer, Observer, Singleton, Component, DI  
📦 **Слои**: Presentation, Business Logic, Data Access, Domain  
⚡ **Производительность**: селективные обновления, кэширование, ленивая загрузка  

Проект готов к масштабированию и расширению!
