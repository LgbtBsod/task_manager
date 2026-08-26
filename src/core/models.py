from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
from typing import Optional, Self, List, Dict, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# Type aliases for better type hints
TaskID = str
DateStr = str  # YYYY-MM-DD format


class TaskStatus(Enum):
    """Task statuses for Kanban board."""
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class Priority(Enum):
    """Task priorities with color coding."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    @property
    def color(self) -> str:
        colors: dict[Priority, str] = {
            Priority.LOW: "#4CAF50",
            Priority.MEDIUM: "#FF9800",
            Priority.HIGH: "#F44336",
            Priority.CRITICAL: "#FF1744",
        }
        return colors[self]


class TaskType(Enum):
    """Jira-style task types."""
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    EPIC = "Epic"
    SUBTASK = "Sub-task"


class LinkType(Enum):
    """Types of relationships between tasks."""
    BLOCKS = "blocks"
    BLOCKED_BY = "blocked_by"
    DUPLICATES = "duplicates"
    RELATES_TO = "relates_to"
    CLONES = "clones"




class Urgency(Enum):
    """Jira-style urgency levels."""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"


class Resolution(Enum):
    """Jira-style resolution for completed tasks."""
    DONE = "Done"
    WONT_DO = "Won't Do"
    DUPLICATE = "Duplicate"
    CANNOT_REPRODUCE = "Cannot Reproduce"
    FIXED = "Fixed"


class SprintStatus(Enum):
    """Sprint lifecycle states."""
    PLANNING = "Planning"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


@dataclass
class Sprint:
    """Jira-style Sprint: a time-boxed iteration for a set of tasks."""
    name: str = ""
    goal: str = ""
    status: str = SprintStatus.PLANNING.value
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Sprint':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            status=data.get("status", SprintStatus.PLANNING.value),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    def is_active(self) -> bool:
        return self.status == SprintStatus.ACTIVE.value

    def days_remaining(self) -> Optional[int]:
        if not self.end_date or self.status != SprintStatus.ACTIVE.value:
            return None
        try:
            delta = datetime.strptime(self.end_date, "%Y-%m-%d") - datetime.now()
            return max(0, delta.days)
        except ValueError:
            return None


@dataclass
class SubTask:
    """A checklist item within a task."""
    title: str = ""
    done: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, data: dict) -> 'SubTask':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            title=data.get("title", ""),
            done=data.get("done", False),
        )


@dataclass
class TaskComment:
    """A comment on a task (Jira-style)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    author: str = ""
    text: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id, "author": self.author,
            "text": self.text, "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskComment':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            author=data.get("author", ""),
            text=data.get("text", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class TaskLink:
    """A relationship between two tasks."""
    target_task_id: str = ""
    link_type: str = LinkType.RELATES_TO.value

    def to_dict(self) -> dict:
        return {"target_task_id": self.target_task_id, "link_type": self.link_type}

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskLink':
        return cls(
            target_task_id=data.get("target_task_id", ""),
            link_type=data.get("link_type", LinkType.RELATES_TO.value),
        )


@dataclass
class HistoryEntry:
    """A single change record in the task audit log."""
    field_name: str = ""
    old_value: str = ""
    new_value: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name, "old_value": self.old_value,
            "new_value": self.new_value, "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryEntry':
        return cls(
            field_name=data.get("field_name", ""),
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


class TaskModel(BaseModel):
    """Pydantic model for task data validation."""
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
    tags: List[str] = Field(default_factory=list, max_length=10, description="Tags for categorization")
    assignee: Optional[str] = Field(default=None, max_length=100, description="Assigned person")
    story_points: Optional[int] = Field(default=None, ge=0, le=100, description="Agile story points")
    task_type: str = Field(default=TaskType.TASK.value, description="Task type (Task/Bug/Story/Epic)")
    
    @field_validator('due_date', 'start_date')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
    
    @field_validator('task_type')
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        valid = {t.value for t in TaskType}
        if v not in valid:
            raise ValueError(f"Invalid task_type. Must be one of: {valid}")
        return v
    
    @model_validator(mode='after')
    def validate_dates_consistency(self) -> Self:
        if self.start_date and self.due_date:
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            due_dt = datetime.strptime(self.due_date, "%Y-%m-%d")
            if due_dt < start_dt:
                raise ValueError("Due date must be after start date")
        return self
    
    def to_task(self) -> 'Task':
        return Task(
            id=self.id, title=self.title, description=self.description,
            status=self.status, priority=self.priority,
            due_date=self.due_date, start_date=self.start_date,
            time_spent=self.time_spent, created_at=self.created_at,
            updated_at=self.updated_at, tags=self.tags,
            assignee=self.assignee, story_points=self.story_points,
            task_type=self.task_type,
        )
    
    @classmethod
    def from_task(cls, task: 'Task') -> 'TaskModel':
        return cls(
            id=task.id, title=task.title, description=task.description,
            status=task.status, priority=task.priority,
            due_date=task.due_date, start_date=task.start_date,
            time_spent=task.time_spent, created_at=task.created_at,
            updated_at=task.updated_at, tags=task.tags,
            assignee=task.assignee, story_points=task.story_points,
            task_type=task.task_type,
        )


def _normalize_tags(tags: List[str]) -> List[str]:
    """Deduplicate, strip whitespace, lowercase, remove empty, cap at 10."""
    seen = set()
    result = []
    for t in tags:
        cleaned = t.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
            if len(result) >= 10:
                break
    return result


@dataclass
class Task:
    """Domain model representing a task in the Kanban board.

    Supports Jira-like features: tags, subtasks, comments, task links,
    assignee, story points, task type, and full audit history.
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
    tags: List[str] = field(default_factory=list)
    subtasks: List[SubTask] = field(default_factory=list)
    comments: List[TaskComment] = field(default_factory=list)
    links: List[TaskLink] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)
    assignee: Optional[str] = None
    story_points: Optional[int] = None
    task_type: str = TaskType.TASK.value
    urgency: str = Urgency.NORMAL.value
    watchers: List[str] = field(default_factory=list)
    epic_link: Optional[str] = None
    resolution: Optional[str] = None
    sprint_id: Optional[str] = None
    components: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    version_id: Optional[str] = None
    original_estimate: float = 0.0  # hours
    category_id: Optional[str] = None
    recurring_task_id: Optional[str] = None
    rank: int = 0

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())[:8]
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
        # Normalize tags
        self.tags = _normalize_tags(self.tags)
        # Validate using Pydantic
        try:
            TaskModel.from_task(self)
        except Exception as e:
            raise ValueError(f"Task validation failed: {e}")

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        # Deserialize nested objects BEFORE validation
        data['subtasks'] = [SubTask.from_dict(s) for s in data.get('subtasks', [])]
        data['comments'] = [TaskComment.from_dict(c) for c in data.get('comments', [])]
        data['links'] = [TaskLink.from_dict(l) for l in data.get('links', [])]
        data['history'] = [HistoryEntry.from_dict(h) for h in data.get('history', [])]
        # Validate basic fields using Pydantic (only pass fields TaskModel knows)
        try:
            model_fields = {k: v for k, v in data.items() if k in TaskModel.model_fields}
            TaskModel(**model_fields)
        except Exception as e:
            raise ValueError(f"Task validation failed: {e}")
        # Create Task directly with ALL fields (preserving nested objects)
        return cls(**data)

    def is_overdue(self) -> bool:
        if self.due_date is None or self.status == TaskStatus.DONE:
            return False
        try:
            return datetime.strptime(self.due_date, "%Y-%m-%d") < datetime.now()
        except ValueError:
            return False

    def days_until_due(self) -> Optional[int]:
        if self.due_date is None:
            return None
        try:
            delta = datetime.strptime(self.due_date, "%Y-%m-%d") - datetime.now()
            return delta.days
        except ValueError:
            return None

    def update_timestamp(self):
        self.updated_at = datetime.now().isoformat()

    def get_gantt_start(self) -> str:
        if self.start_date:
            return self.start_date
        return self.created_at[:10]

    def get_gantt_end(self) -> str:
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
        start_date = self.get_gantt_start()
        return start_date if end_date < start_date else end_date

    # ── Subtask methods ──

    def subtask_progress(self) -> float:
        """Return 0.0-1.0 subtask completion ratio."""
        if not self.subtasks:
            return 0.0
        done = sum(1 for s in self.subtasks if s.done)
        return done / len(self.subtasks)

    def toggle_subtask(self, index: int) -> bool:
        """Toggle subtask done state. Returns False if index invalid."""
        if 0 <= index < len(self.subtasks):
            self.subtasks[index].done = not self.subtasks[index].done
            return True
        return False

    # ── Comment helpers ──

    def add_comment(self, author: str, text: str) -> TaskComment:
        comment = TaskComment(author=author, text=text)
        self.comments.append(comment)
        return comment

    def delete_comment(self, comment_id: str) -> bool:
        before = len(self.comments)
        self.comments = [c for c in self.comments if c.id != comment_id]
        return len(self.comments) < before

    # ── Link helpers ──

    def add_link(self, target_task_id: str, link_type: str) -> TaskLink:
        link = TaskLink(target_task_id=target_task_id, link_type=link_type)
        self.links.append(link)
        return link

    def remove_link(self, target_task_id: str) -> bool:
        before = len(self.links)
        self.links = [l for l in self.links if l.target_task_id != target_task_id]
        return len(self.links) < before

    # ── History helper ──

    def record_change(self, field_name: str, old_value: str, new_value: str):
        self.history.append(HistoryEntry(
            field_name=field_name, old_value=old_value, new_value=new_value,
        ))


@dataclass
class ActivityEntry:
    """A single entry in the global activity feed."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    action: str = ""  # e.g. "created", "status_changed", "comment_added"
    task_id: Optional[str] = None
    task_title: str = ""
    author: str = ""
    details: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ActivityEntry':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            action=data.get("action", ""),
            task_id=data.get("task_id"),
            task_title=data.get("task_title", ""),
            author=data.get("author", ""),
            details=data.get("details", ""),
        )


# ── Workflow Transitions ──

# Allowed status transitions per task type.
# Each value is a dict: from_status -> list of allowed to_statuses.
# '*' means all statuses.
WORKFLOW_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    # Default: Todo <-> In Progress <-> Done (any direction)
    "*": {
        TaskStatus.TODO.value: [TaskStatus.IN_PROGRESS.value],
        TaskStatus.IN_PROGRESS.value: [TaskStatus.TODO.value, TaskStatus.DONE.value],
        TaskStatus.DONE.value: [TaskStatus.IN_PROGRESS.value],
    },
    # Bug: must go Todo -> In Progress -> Done (no going back from Done)
    TaskType.BUG.value: {
        TaskStatus.TODO.value: [TaskStatus.IN_PROGRESS.value],
        TaskStatus.IN_PROGRESS.value: [TaskStatus.TODO.value, TaskStatus.DONE.value],
        TaskStatus.DONE.value: [TaskStatus.IN_PROGRESS.value],
    },
}


@dataclass
class VersionRelease:
    """Jira-style Version / Release: groups tasks that ship together."""
    name: str = ""
    description: str = ""
    status: str = "Unreleased"  # Unreleased | Released | Archived
    release_date: Optional[str] = None  # YYYY-MM-DD
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'VersionRelease':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=data.get("status", "Unreleased"),
            release_date=data.get("release_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    def is_released(self) -> bool:
        return self.status == "Released"


class RecurrenceFrequency(Enum):
    """Recurrence patterns for recurring tasks."""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass
class TaskTemplate:
    """Reusable task template for quick task creation.

    Stores default field values. When creating a task from a template,
    these values become the task's initial state (except id, timestamps, history).
    """
    name: str = ""
    description: str = ""
    task_type: str = TaskType.TASK.value
    priority: str = Priority.MEDIUM.value
    tags: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    story_points: Optional[int] = None
    original_estimate: float = 0.0
    assignee: Optional[str] = None
    urgency: str = Urgency.NORMAL.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskTemplate':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            task_type=data.get("task_type", TaskType.TASK.value),
            priority=data.get("priority", Priority.MEDIUM.value),
            tags=data.get("tags", []),
            labels=data.get("labels", []),
            components=data.get("components", []),
            story_points=data.get("story_points"),
            original_estimate=data.get("original_estimate", 0.0),
            assignee=data.get("assignee"),
            urgency=data.get("urgency", Urgency.NORMAL.value),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class Category:
    """A project/category for grouping tasks (higher-level than epics)."""
    name: str = ""
    description: str = ""
    color: str = "#0a84ff"  # hex color
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Category':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            color=data.get("color", "#0a84ff"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class Notification:
    """A notification/alert for the user (overdue, due soon, etc.)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ntype: str = "info"  # info | warning | error | success
    title: str = ""
    message: str = ""
    task_id: Optional[str] = None
    is_read: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Notification':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            created_at=data.get("created_at", datetime.now().isoformat()),
            ntype=data.get("ntype", "info"),
            title=data.get("title", ""),
            message=data.get("message", ""),
            task_id=data.get("task_id"),
            is_read=data.get("is_read", False),
        )


@dataclass
class RecurringTask:
    """A recurring task that auto-generates child tasks on a schedule.

    When the generated task is marked Done, the next occurrence is
    calculated from the base_due_date + N * frequency.
    """
    title: str = ""
    description: str = ""
    frequency: str = RecurrenceFrequency.WEEKLY.value
    base_due_date: Optional[str] = None  # YYYY-MM-DD, the reference date
    task_type: str = TaskType.TASK.value
    priority: str = Priority.MEDIUM.value
    tags: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    estimate_hours: float = 0.0
    is_active: bool = True
    last_generated_date: Optional[str] = None  # YYYY-MM-DD of last auto-gen
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RecurringTask':
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            title=data.get("title", ""),
            description=data.get("description", ""),
            frequency=data.get("frequency", RecurrenceFrequency.WEEKLY.value),
            base_due_date=data.get("base_due_date"),
            task_type=data.get("task_type", TaskType.TASK.value),
            priority=data.get("priority", Priority.MEDIUM.value),
            tags=data.get("tags", []),
            labels=data.get("labels", []),
            estimate_hours=data.get("estimate_hours", 0.0),
            is_active=data.get("is_active", True),
            last_generated_date=data.get("last_generated_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    def next_due_date(self, after_date: Optional[str] = None) -> Optional[str]:
        """Calculate the next due date on or after after_date.

        Returns YYYY-MM-DD or None if base_due_date is not set.
        """
        if not self.base_due_date:
            return None
        try:
            base = datetime.strptime(self.base_due_date, "%Y-%m-%d")
            after = datetime.strptime(after_date, "%Y-%m-%d") if after_date else datetime.now()
            delta_map = {
                RecurrenceFrequency.DAILY.value: timedelta(days=1),
                RecurrenceFrequency.WEEKLY.value: timedelta(weeks=1),
                RecurrenceFrequency.BIWEEKLY.value: timedelta(weeks=2),
                RecurrenceFrequency.MONTHLY.value: timedelta(days=30),
                RecurrenceFrequency.QUARTERLY.value: timedelta(days=90),
            }
            step = delta_map.get(self.frequency, timedelta(weeks=1))
            candidate = base
            while candidate < after:
                candidate += step
            return candidate.strftime("%Y-%m-%d")
        except ValueError:
            return None


__all__ = [
    'Task', 'TaskStatus', 'Priority', 'TaskModel', 'TaskType', 'LinkType',
    'SubTask', 'TaskComment', 'TaskLink', 'HistoryEntry', '_normalize_tags',
    'TaskID', 'DateStr', 'Urgency', 'Resolution', 'SprintStatus', 'Sprint',
    'ActivityEntry', 'VersionRelease', 'WORKFLOW_TRANSITIONS',
    'RecurrenceFrequency', 'TaskTemplate', 'Category', 'Notification', 'RecurringTask',
]
