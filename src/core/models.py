import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from enum import Enum, StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from .datetimeutil import date_part, parse_dt
from .strings import ERR

# Type aliases for better type hints
TaskID = str
DateStr = str  # YYYY-MM-DD format


def _short_id() -> str:
    """8-char id used as the default primary key for every entity."""
    return str(uuid.uuid4())[:8]


def _now_iso() -> str:
    """Current timestamp in ISO format — the default for every ``created_at``."""
    return datetime.now().isoformat()


class _DataclassJSON:
    """``to_dict`` / ``from_dict`` for a flat dataclass of JSON-native fields.

    ``from_dict`` ignores unknown keys and drops ``None`` values so the
    dataclass's own defaults / ``default_factory`` fill them in (ids, timestamps).
    Entities with enums or nested dataclasses (``Task``) override this.
    """

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known and v is not None})


class TaskStatus(StrEnum):
    """Task statuses for Kanban board. ``StrEnum`` so a member *is* its stored
    string — ``asdict`` / ``json.dumps`` serialize it with no special-casing."""
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"

    @property
    def order(self) -> int:
        """Sort rank for board / Gantt listings: active work first."""
        return {"In Progress": 0, "Todo": 1, "Done": 2}[self.value]


class Priority(StrEnum):
    """Task priorities with colour and sort rank."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    @property
    def color(self) -> str:
        # SAP Horizon severity ramp (positive -> critical -> negative).
        return {
            "Low": "#36a41d", "Medium": "#e76500",
            "High": "#f53232", "Critical": "#d20a0a",
        }[self.value]

    @property
    def sort_index(self) -> int:
        """Sort rank: most urgent first (Critical=0 … Low=3)."""
        return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}[self.value]


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
class Sprint(_DataclassJSON):
    """Jira-style Sprint: a time-boxed iteration for a set of tasks."""
    name: str = ""
    goal: str = ""
    status: str = SprintStatus.PLANNING.value
    start_date: str | None = None
    end_date: str | None = None
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)

    def is_active(self) -> bool:
        return self.status == SprintStatus.ACTIVE.value

    def days_remaining(self) -> int | None:
        if not self.end_date or self.status != SprintStatus.ACTIVE.value:
            return None
        try:
            delta = datetime.strptime(self.end_date, "%Y-%m-%d") - datetime.now()
            return max(0, delta.days)
        except ValueError:
            return None


@dataclass
class SubTask(_DataclassJSON):
    """A checklist item within a task."""
    title: str = ""
    done: bool = False
    id: str = field(default_factory=_short_id)


@dataclass
class TaskComment(_DataclassJSON):
    """A comment on a task (Jira-style)."""
    id: str = field(default_factory=_short_id)
    author: str = ""
    text: str = ""
    created_at: str = field(default_factory=_now_iso)


@dataclass
class TaskLink(_DataclassJSON):
    """A relationship between two tasks."""
    target_task_id: str = ""
    link_type: str = LinkType.RELATES_TO.value


@dataclass
class HistoryEntry(_DataclassJSON):
    """A single change record in the task audit log."""
    field_name: str = ""
    old_value: str = ""
    new_value: str = ""
    timestamp: str = field(default_factory=_now_iso)


class TaskModel(BaseModel):
    """Pydantic model for task data validation."""
    id: TaskID | None = Field(default=None, description="Unique task identifier")
    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: str = Field(default="", max_length=5000, description="Task description")
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: Priority = Field(default=Priority.MEDIUM)
    due_date: DateStr | None = Field(default=None, description="Due date in YYYY-MM-DD format")
    start_date: DateStr | None = Field(default=None, description="Start date in YYYY-MM-DD format")
    time_spent: float = Field(default=0.0, ge=0, description="Time spent in hours")
    created_at: str | None = Field(default=None, description="Creation timestamp (ISO format)")
    updated_at: str | None = Field(default=None, description="Last update timestamp (ISO format)")
    tags: list[str] = Field(default_factory=list, max_length=10, description="Tags for categorization")
    assignee: str | None = Field(default=None, max_length=100, description="Assigned person")
    story_points: int | None = Field(default=None, ge=0, le=100, description="Agile story points")
    task_type: str = Field(default=TaskType.TASK.value, description="Task type (Task/Bug/Story/Epic)")

    @field_validator('due_date', 'start_date')
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if parse_dt(v) is None:
            raise ValueError(ERR.DATE_FORMAT)
        return v.strip()

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
            start_dt = parse_dt(self.start_date)
            due_dt = parse_dt(self.due_date)
            if start_dt and due_dt and due_dt < start_dt:
                raise ValueError(ERR.DUE_BEFORE_START)
        return self

    def to_task(self) -> 'Task':
        # TaskModel's fields are a subset of Task's; the rest take dataclass
        # defaults. model_dump() keeps enum members (no use_enum_values).
        return Task(**self.model_dump())

    @classmethod
    def from_task(cls, task: 'Task') -> 'TaskModel':
        return cls.model_validate(task, from_attributes=True)


def _normalize_tags(tags: list[str]) -> list[str]:
    """Strip / lowercase / drop-empty / order-preserving dedupe, cap at 10."""
    return list(dict.fromkeys(s for t in tags if (s := t.strip().lower())))[:10]


@dataclass
class Task(_DataclassJSON):
    """Domain model representing a task in the Kanban board.

    Supports Jira-like features: tags, subtasks, comments, task links,
    assignee, story points, task type, and full audit history.

    ``to_dict`` is the inherited ``asdict`` — ``status``/``priority`` are
    ``StrEnum`` so they serialize as their string value. ``from_dict`` is
    overridden below (enum coercion + nested objects).
    """
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    due_date: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str | None = None
    id: str | None = None
    time_spent: float = 0.0
    start_date: str | None = None
    tags: list[str] = field(default_factory=list)
    subtasks: list[SubTask] = field(default_factory=list)
    comments: list[TaskComment] = field(default_factory=list)
    links: list[TaskLink] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    assignee: str | None = None
    story_points: int | None = None
    task_type: str = TaskType.TASK.value
    urgency: str = Urgency.NORMAL.value
    watchers: list[str] = field(default_factory=list)
    epic_link: str | None = None
    resolution: str | None = None
    sprint_id: str | None = None
    components: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    version_id: str | None = None
    original_estimate: float = 0.0  # hours
    category_id: str | None = None
    recurring_task_id: str | None = None
    rank: int = 0

    def __post_init__(self):
        if self.id is None:
            self.id = _short_id()
        now = _now_iso()
        # Backfill timestamps that are missing or explicitly null (legacy data).
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        # Normalize tags
        self.tags = _normalize_tags(self.tags)
        # Validate using Pydantic
        try:
            TaskModel.from_task(self)
        except Exception as e:
            raise ValueError(f"Task validation failed: {e}") from e

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        # Keep only keys the dataclass knows about (tolerate legacy / extra keys).
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in known}

        # Enums: tolerate a missing key or an unknown value by falling back.
        try:
            data['status'] = TaskStatus(data.get('status') or TaskStatus.TODO.value)
        except ValueError:
            data['status'] = TaskStatus.TODO
        try:
            data['priority'] = Priority(data.get('priority') or Priority.MEDIUM.value)
        except ValueError:
            data['priority'] = Priority.MEDIUM

        # Deserialize nested objects
        data['subtasks'] = [SubTask.from_dict(s) for s in data.get('subtasks', [])]
        data['comments'] = [TaskComment.from_dict(c) for c in data.get('comments', [])]
        data['links'] = [TaskLink.from_dict(l) for l in data.get('links', [])]
        data['history'] = [HistoryEntry.from_dict(h) for h in data.get('history', [])]

        # Drop explicit nulls so dataclass defaults / __post_init__ apply.
        for key in ('id', 'created_at', 'updated_at'):
            if data.get(key) is None:
                data.pop(key, None)

        # Validation runs once, in __post_init__ (TaskModel.from_task).
        return cls(**data)

    def _due_dt(self):
        return parse_dt(self.due_date)

    def is_overdue(self) -> bool:
        if not self.due_date or self.status == TaskStatus.DONE:
            return False
        dt = self._due_dt()
        return dt is not None and dt < datetime.now()

    def days_until_due(self) -> int | None:
        dt = self._due_dt()
        if dt is None:
            return None
        return (dt - datetime.now()).days

    def seconds_until_due(self) -> float | None:
        """Signed seconds to the deadline (negative once overdue)."""
        dt = self._due_dt()
        if dt is None:
            return None
        return (dt - datetime.now()).total_seconds()

    def due_has_time(self) -> bool:
        from .datetimeutil import has_time
        return has_time(self.due_date)

    def update_timestamp(self):
        self.updated_at = _now_iso()

    def get_gantt_start(self) -> str:
        d = date_part(self.start_date)
        if d:
            return d
        return (self.created_at or datetime.now().isoformat())[:10]

    def get_gantt_end(self) -> str:
        if self.status == TaskStatus.DONE and self.updated_at:
            end_date = self.updated_at[:10]
        elif date_part(self.due_date):
            end_date = date_part(self.due_date)
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
class ActivityEntry(_DataclassJSON):
    """A single entry in the global activity feed."""
    id: str = field(default_factory=_short_id)
    timestamp: str = field(default_factory=_now_iso)
    action: str = ""  # e.g. "created", "status_changed", "comment_added"
    task_id: str | None = None
    task_title: str = ""
    author: str = ""
    details: str = ""


# ── Workflow Transitions ──

# Allowed status transitions per task type.
# Each value is a dict: from_status -> list of allowed to_statuses.
# '*' means all statuses.
WORKFLOW_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    # Todo <-> In Progress <-> Done (any direction). Keyed by task type;
    # "*" is the fallback and currently the only rule.
    "*": {
        TaskStatus.TODO.value: [TaskStatus.IN_PROGRESS.value],
        TaskStatus.IN_PROGRESS.value: [TaskStatus.TODO.value, TaskStatus.DONE.value],
        TaskStatus.DONE.value: [TaskStatus.IN_PROGRESS.value],
    },
}


@dataclass
class VersionRelease(_DataclassJSON):
    """Jira-style Version / Release: groups tasks that ship together."""
    name: str = ""
    description: str = ""
    status: str = "Unreleased"  # Unreleased | Released | Archived
    release_date: str | None = None  # YYYY-MM-DD
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)

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
class TaskTemplate(_DataclassJSON):
    """Reusable task template for quick task creation.

    Stores default field values. When creating a task from a template,
    these values become the task's initial state (except id, timestamps, history).
    """
    name: str = ""
    description: str = ""
    task_type: str = TaskType.TASK.value
    priority: str = Priority.MEDIUM.value
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    story_points: int | None = None
    original_estimate: float = 0.0
    assignee: str | None = None
    urgency: str = Urgency.NORMAL.value
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)


@dataclass
class Category(_DataclassJSON):
    """A project/category for grouping tasks (higher-level than epics)."""
    name: str = ""
    description: str = ""
    color: str = "#0a84ff"  # hex color
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)


# Default colour for a freshly-registered tag — a Horizon neutral (same as the
# "Task" type accent) so a tag reads as neutral until the user recolours it.
TAG_DEFAULT_COLOR = "#788fa6"


@dataclass
class Tag(_DataclassJSON):
    """A named, colour-coded label from the tag registry.

    Tasks reference a tag by ``name`` — the same lower-cased string stored in
    ``Task.tags`` (see :func:`_normalize_tags`). The registry adds a colour, an
    optional description and analytics; renaming/deleting a tag rewrites every
    referencing task (``TagService``).
    """
    name: str = ""                       # canonical, lower-case
    color: str = TAG_DEFAULT_COLOR        # hex "#rrggbb"
    description: str = ""
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)

    @classmethod
    def from_dict(cls, data: dict) -> "Tag":
        obj = super().from_dict(data)
        obj.name = obj.name.strip().lower()
        return obj


@dataclass
class Notification(_DataclassJSON):
    """A notification/alert for the user (overdue, due soon, etc.)."""
    id: str = field(default_factory=_short_id)
    created_at: str = field(default_factory=_now_iso)
    ntype: str = "info"  # info | warning | error | success
    title: str = ""
    message: str = ""
    task_id: str | None = None
    is_read: bool = False


@dataclass
class RecurringTask(_DataclassJSON):
    """A recurring task that auto-generates child tasks on a schedule.

    When the generated task is marked Done, the next occurrence is
    calculated from the base_due_date + N * frequency.
    """
    title: str = ""
    description: str = ""
    frequency: str = RecurrenceFrequency.WEEKLY.value
    base_due_date: str | None = None  # YYYY-MM-DD, the reference date
    task_type: str = TaskType.TASK.value
    priority: str = Priority.MEDIUM.value
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    estimate_hours: float = 0.0
    is_active: bool = True
    last_generated_date: str | None = None  # YYYY-MM-DD of last auto-gen
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=_short_id)

    _STEP = {
        RecurrenceFrequency.DAILY.value: timedelta(days=1),
        RecurrenceFrequency.WEEKLY.value: timedelta(weeks=1),
        RecurrenceFrequency.BIWEEKLY.value: timedelta(weeks=2),
        RecurrenceFrequency.MONTHLY.value: timedelta(days=30),
        RecurrenceFrequency.QUARTERLY.value: timedelta(days=90),
    }

    def next_due_date(self, after_date: str | None = None) -> str | None:
        """The first occurrence on or after ``after_date`` (or today).
        YYYY-MM-DD, or None if ``base_due_date`` is unset/invalid.
        """
        if not self.base_due_date:
            return None
        try:
            base = datetime.strptime(self.base_due_date, "%Y-%m-%d")
            after = datetime.strptime(after_date, "%Y-%m-%d") if after_date else datetime.now()
        except ValueError:
            return None
        step = self._STEP.get(self.frequency, timedelta(weeks=1))
        occ = base
        while occ < after:
            occ += step
        return occ.strftime("%Y-%m-%d")

    def due_occurrence(self, today: str, after: str | None = None) -> str | None:
        """The *latest* occurrence that has come due (``<= today``) and is
        strictly after ``after`` (the last one already generated), or None.

        Latest-not-earliest: if the app was closed for three weekly cycles you
        want one "do it now" task, not three backlog items. Drives auto-generation.
        """
        if not self.base_due_date:
            return None
        try:
            base = datetime.strptime(self.base_due_date, "%Y-%m-%d")
            limit = datetime.strptime(today, "%Y-%m-%d")
            floor = datetime.strptime(after, "%Y-%m-%d") if after else None
        except ValueError:
            return None
        step = self._STEP.get(self.frequency, timedelta(weeks=1))
        occ, result = base, None
        while occ <= limit:
            if floor is None or occ > floor:
                result = occ.strftime("%Y-%m-%d")
            occ += step
        return result


__all__ = [
    'Task', 'TaskStatus', 'Priority', 'TaskModel', 'TaskType', 'LinkType',
    'SubTask', 'TaskComment', 'TaskLink', 'HistoryEntry', '_normalize_tags',
    'TaskID', 'DateStr', 'Urgency', 'Resolution', 'SprintStatus', 'Sprint',
    'ActivityEntry', 'VersionRelease', 'WORKFLOW_TRANSITIONS',
    'RecurrenceFrequency', 'TaskTemplate', 'Category', 'Notification', 'RecurringTask',
    'Tag', 'TAG_DEFAULT_COLOR',
]
