"""
Task Manager - Modern Kanban Board
Core Domain Models
Python 3.14+ Compatible

Using Pydantic for validation (DRTTW - Don't Reinvent The Wheel)

Principles:
- SRP: Separate classes for validation (TaskModel) and domain logic (Task)
- DRY: Reuse Pydantic's built-in validation capabilities
- DRTTW: Use established library instead of custom validators
- YAGNI: No excessive validation rules
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
from typing import Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator


# Type aliases for better type hints
TaskID = str
DateStr = str  # YYYY-MM-DD format


class TaskStatus(Enum):
    """Task statuses for Kanban board.
    
    Values are human-readable for UI display.
    """
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class Priority(Enum):
    """Task priorities with color coding.
    
    Attributes:
        LOW: Low priority tasks (green)
        MEDIUM: Medium priority tasks (orange)  
        HIGH: High priority tasks (red)
    """
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @property
    def color(self) -> str:
        """Return hex color code for priority level."""
        colors: dict[Priority, str] = {
            Priority.LOW: "#4CAF50",      # Green
            Priority.MEDIUM: "#FF9800",   # Orange
            Priority.HIGH: "#F44336",     # Red
        }
        return colors[self]


class TaskModel(BaseModel):
    """
    Pydantic model for task data validation.
    
    Responsible for:
    - Data validation on creation/update
    - Schema enforcement
    - Type coercion
    
    Not responsible for:
    - Business logic (handled by TaskService)
    - Data persistence (handled by TaskRepository)
    """
    
    id: Optional[TaskID] = Field(default=None, description="Unique task identifier")
    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: str = Field(default="", max_length=5000, description="Task description")
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: Priority = Field(default=Priority.MEDIUM)
    due_date: Optional[DateStr] = Field(default=None, description="Due date in YYYY-MM-DD format")
    start_date: Optional[DateStr] = Field(default=None, description="Start date in YYYY-MM-DD format")
    time_spent: float = Field(default=0.0, ge=0, description="Time spent in hours")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp (ISO format)")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp (ISO format)")
    
    @field_validator('due_date', 'start_date')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format using Pydantic validator (DRTTW)."""
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
    
    @model_validator(mode='after')
    def validate_dates_consistency(self) -> Self:
        """Ensure dates are logically consistent."""
        if self.start_date and self.due_date:
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            due_dt = datetime.strptime(self.due_date, "%Y-%m-%d")
            if due_dt < start_dt:
                raise ValueError("Due date must be after start date")
        return self
    
    def to_task(self) -> 'Task':
        """Convert Pydantic model to Task dataclass."""
        return Task(
            id=self.id,
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            due_date=self.due_date,
            start_date=self.start_date,
            time_spent=self.time_spent,
            created_at=self.created_at,
            updated_at=self.updated_at
        )
    
    @classmethod
    def from_task(cls, task: 'Task') -> 'TaskModel':
        """Create Pydantic model from Task dataclass."""
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            start_date=task.start_date,
            time_spent=task.time_spent,
            created_at=task.created_at,
            updated_at=task.updated_at
        )


@dataclass
class Task:
    """
    Domain model representing a task in the Kanban board.
    
    Attributes:
        title: Task title (required, 1-200 chars)
        description: Optional task description (max 5000 chars)
        status: Current task status (TODO, IN_PROGRESS, DONE)
        priority: Task priority level (LOW, MEDIUM, HIGH)
        due_date: Optional due date in YYYY-MM-DD format
        created_at: ISO timestamp of task creation
        updated_at: ISO timestamp of last update
        id: Unique task identifier (auto-generated if not provided)
        time_spent: Hours spent on task (non-negative)
        start_date: Optional start date for Gantt chart
    
    Principles:
        - SRP: Only holds domain data and business logic methods
        - DRY: Delegates validation to TaskModel (Pydantic)
    """
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    due_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    id: Optional[str] = None
    time_spent: float = 0.0
    start_date: Optional[str] = None

    def __post_init__(self):
        """Initialize auto-generated fields and validate."""
        if self.id is None:
            self.id = str(uuid.uuid4())[:8]
        
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
        
        # Validate using Pydantic (DRTTW)
        try:
            model = TaskModel.from_task(self)
        except Exception as e:
            raise ValueError(f"Task validation failed: {e}")

    def to_dict(self) -> dict:
        """Serialize task to dictionary for JSON storage."""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Deserialize task from dictionary with validation."""
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        
        # Validate using Pydantic before creating (DRTTW)
        try:
            model = TaskModel(**data)
            return model.to_task()
        except Exception as e:
            raise ValueError(f"Task validation failed: {e}")

    def is_overdue(self) -> bool:
        """Check if task is past its due date (excluding completed tasks)."""
        if self.due_date is None or self.status == TaskStatus.DONE:
            return False
        
        try:
            due_date = datetime.strptime(self.due_date, "%Y-%m-%d")
            return due_date < datetime.now()
        except ValueError:
            return False

    def days_until_due(self) -> Optional[int]:
        """Get number of days until due date."""
        if self.due_date is None:
            return None
        
        try:
            due_date = datetime.strptime(self.due_date, "%Y-%m-%d")
            delta = due_date - datetime.now()
            return delta.days
        except ValueError:
            return None

    def update_timestamp(self):
        """Update the modified timestamp to current time."""
        self.updated_at = datetime.now().isoformat()

    def get_gantt_start(self) -> str:
        """Get start date for Gantt chart visualization."""
        if self.start_date:
            return self.start_date
        return self.created_at[:10]

    def get_gantt_end(self) -> str:
        """Get end date for Gantt chart visualization."""
        if self.status == TaskStatus.DONE and self.updated_at:
            end_date = self.updated_at[:10]
        elif self.due_date:
            end_date = self.due_date
        else:
            start = self.get_gantt_start()
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_date = (start_dt + timedelta(days=7)).isoformat()[:10]
            except ValueError:
                end_date = (datetime.now().date() + timedelta(days=7)).isoformat()
        
        # Ensure end_date >= start_date
        start_date = self.get_gantt_start()
        return start_date if end_date < start_date else end_date
