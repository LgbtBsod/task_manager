"""
Task Manager - Modern Kanban Board
Architecture: Clean Architecture + Event-Driven Design
Python 3.14+ Compatible

Project Structure:
├── core/           # Domain Layer (Business Logic)
│   ├── models.py   # Entities (Task, TaskStatus, Priority)
│   ├── repository.py  # Data Access Layer
│   ├── service.py  # Business Logic Layer
│   └── events.py   # Event System (Observer Pattern)
├── gui/            # Presentation Layer
│   ├── main_window.py    # Main Application Window
│   ├── gantt_view.py     # Gantt Chart View
│   └── components.py     # Reusable UI Components
└── utils/          # Infrastructure Layer
    └── helpers.py  # Utility Functions

SOLID Principles Applied:
✓ SRP - Each class has single responsibility
✓ OCP - Open for extension, closed for modification (EventBus)
✓ LSP - Liskov Substitution (not applicable yet)
✓ ISP - Interface Segregation (callbacks in components)
✓ DIP - Dependency Inversion (EventBus injected into Service)

Other Principles:
✓ SSOT - Single Source of Truth (EventBus singleton, TaskService)
✓ DRY - Don't Repeat Yourself (centralized constants, helpers)
✓ YAGNI - You Ain't Gonna Need It (no over-engineering)
✓ DRTTW - Don't Reinvent The Wheel (use standard library)
"""

__version__ = "2.0.0"
__author__ = "Task Manager Team"
