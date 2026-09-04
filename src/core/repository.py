"""
Task Manager - Modern Kanban Board
Repository Pattern for Data Persistence
Python 3.14+ Compatible

This module implements the Repository pattern to abstract data access,
allowing the business logic layer to work with domain objects without
knowing about storage details.

Principles:
- SRP: Only handles data persistence (load/save)
- DIP: Depends on abstractions (file path), not concrete implementations
- YAGNI: No unnecessary methods or complexity
"""
import json
import logging
import shutil
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ._atomic import atomic_write_text
from .models import (
    Category,
    Notification,
    Priority,
    ProjectTemplate,
    RecurringTask,
    Sprint,
    Tag,
    Task,
    TaskStatus,
    TaskTemplate,
    VersionRelease,
)

log = logging.getLogger(__name__)

# Bumped only when the export/import dict shape changes (not the app version).
EXPORT_SCHEMA_VERSION = "1"


def _read_json_list(path: Path) -> list:
    """Read a JSON list from *path*.

    Recovers a file saved in a legacy 8-bit encoding (re-saving it as UTF-8),
    and only as a last resort backs up an unrecoverable file and returns [].
    """
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        return []

    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            parsed = json.loads(raw_bytes.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        data = parsed if isinstance(parsed, list) else []
        if enc != "utf-8":
            log.warning("Re-saving %s from %s to UTF-8", path.name, enc)
            try:
                _write_json_list(path, data)
            except Exception:
                pass
        return data

    try:
        backup = path.with_name(
            f"{path.stem}.corrupt-{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
        )
        shutil.copy2(path, backup)
        log.error("Unrecoverable JSON at %s; backed up to %s", path, backup.name)
    except Exception:
        log.error("Unrecoverable JSON at %s; backup failed", path)
    return []


def _write_json_list(path: Path, items: list) -> None:
    """Atomically write *items* as pretty UTF-8 JSON to *path*."""
    atomic_write_text(path, json.dumps(items, indent=2, ensure_ascii=False))


def _parse_each(records: list, factory, kind: str) -> list:
    """Deserialize *records* one at a time, skipping (and logging) bad ones."""
    out = []
    for rec in records:
        try:
            out.append(factory(rec))
        except Exception as exc:
            log.warning("Skipping unparseable %s %r: %s", kind, rec, exc)
    return out


class _Entity(Protocol):
    id: str
    def to_dict(self) -> dict: ...


class _JsonCollection[T: _Entity]:
    """An id-keyed CRUD store over one sidecar JSON list.

    Every secondary entity (sprints, versions, templates, categories, recurring
    tasks, notifications) is the same list-of-dicts persisted next to the task
    file and keyed by ``id`` — this holds that logic once instead of six times.
    """

    __slots__ = ("path", "_factory", "_kind")

    def __init__(self, path: Path, factory: Callable[[dict], T], kind: str) -> None:
        self.path = path
        self._factory = factory
        self._kind = kind

    def load_raw(self) -> list[dict]:
        return _read_json_list(self.path)

    def save_raw(self, items: list[dict]) -> None:
        _write_json_list(self.path, items)

    def all(self) -> list[T]:
        return _parse_each(self.load_raw(), self._factory, self._kind)

    def by_id(self, item_id: str) -> T | None:
        return next((obj for obj in self.all() if obj.id == item_id), None)

    def add(self, obj: T) -> T:
        items = self.load_raw()
        items.append(obj.to_dict())
        self.save_raw(items)
        return obj

    def update(self, obj: T) -> T:
        items = self.load_raw()
        for i, rec in enumerate(items):
            if rec.get("id") == obj.id:
                items[i] = obj.to_dict()
                break
        self.save_raw(items)
        return obj

    def delete(self, item_id: str) -> bool:
        items = self.load_raw()
        kept = [r for r in items if r.get("id") != item_id]
        if len(kept) == len(items):
            return False
        self.save_raw(kept)
        return True


class TaskRepository:
    """
    Repository for task data persistence using JSON storage.

    Implements the Repository pattern to provide a clean interface
    for CRUD operations on Task entities.

    Responsibilities:
    - Loading tasks from JSON file
    - Saving tasks to JSON file
    - Basic querying (by ID, by status)

    Not responsible for:
    - Business logic validation (handled by TaskService)
    - Data transformation (handled by TaskModel)

    Example usage:
        repo = TaskRepository("tasks.json")
        tasks = repo.get_all()
        task = repo.get_by_id("abc123")
        repo.add(new_task)
        repo.update(updated_task)
        repo.delete(task_id)
    """

    def __init__(self, db_path: str = "tasks.json"):
        """Initialize repository with database file path.

        Args:
            db_path: Path to JSON file for task storage
        """
        self.db_path = Path(db_path)
        self._task_cache: list[dict] | None = None
        # The file is created lazily on first write (atomic_write_text mkdirs);
        # missing reads already fall back to []. AppContext also seeds it via
        # paths.ensure_data_dir().

        # One CRUD store per secondary entity, all sidecar files next to the
        # task DB: ``tasks_sprints.json``, ``tasks_versions.json``, …
        def _side(suffix: str) -> Path:
            return self.db_path.parent / f"{self.db_path.stem}_{suffix}.json"

        # Public collections: each is a full CRUD store on its own (.all(),
        # .by_id(), .add(), .update(), .delete()) — callers use these
        # directly (``repo.sprints.all()``) instead of per-entity forwarder
        # methods, so adding a new secondary entity needs one line here plus
        # one in _collections(), not five new methods on this class.
        self.sprints = _JsonCollection(_side("sprints"), Sprint.from_dict, "sprint")
        self.versions = _JsonCollection(_side("versions"), VersionRelease.from_dict, "version")
        self.templates = _JsonCollection(_side("templates"), TaskTemplate.from_dict, "template")
        self.categories = _JsonCollection(_side("categories"), Category.from_dict, "category")
        self.recurring = _JsonCollection(_side("recurring"), RecurringTask.from_dict, "recurring task")
        self.notifications = _JsonCollection(_side("notifications"), Notification.from_dict, "notification")
        self.tags = _JsonCollection(_side("tags"), Tag.from_dict, "tag")
        self.project_templates = _JsonCollection(
            _side("project_templates"), ProjectTemplate.from_dict, "project template")

    def _load_tasks(self) -> list[dict]:
        """Load raw task dicts from the JSON file (cached in-memory).

        Returns:
            List of task dictionaries, empty list if file is invalid/missing
        """
        if self._task_cache is None:
            self._task_cache = _read_json_list(self.db_path)
        return self._task_cache

    def _save_tasks(self, tasks: list[dict]) -> None:
        """Persist task dicts atomically and refresh the cache."""
        _write_json_list(self.db_path, tasks)
        self._task_cache = tasks

    def get_all(self) -> list[Task]:
        """Retrieve all tasks from storage.

        A single unparseable record is skipped (and logged) rather than
        aborting the whole load.

        Returns:
            List of Task domain objects
        """
        out: list[Task] = []
        for item in self._load_tasks():
            try:
                out.append(Task.from_dict(item))
            except Exception as exc:
                log.warning("Skipping unparseable task %r: %s", item, exc)
        return out

    def get_by_id(self, task_id: str) -> Task | None:
        """Find task by unique identifier.

        Args:
            task_id: Unique task identifier

        Returns:
            Task object if found, None otherwise
        """
        tasks = self.get_all()
        for task in tasks:
            if task.id == task_id:
                return task
        return None

    def get_by_status(self, status: TaskStatus) -> list[Task]:
        """Filter tasks by status.

        Args:
            status: Task status to filter by

        Returns:
            List of tasks matching the status
        """
        tasks = self.get_all()
        return [t for t in tasks if t.status == status]

    def add(self, task: Task) -> Task:
        """Persist a new task.

        Args:
            task: Task object to add

        Returns:
            The added task with preserved ID
        """
        tasks = self._load_tasks()
        task_dict = task.to_dict()
        tasks.append(task_dict)
        self._save_tasks(tasks)
        return task

    def update(self, task: Task) -> Task:
        """Update an existing task.

        Args:
            task: Task object with updated data

        Returns:
            Updated task, or original if not found
        """
        tasks = self._load_tasks()
        for i, t in enumerate(tasks):
            if t['id'] == task.id:
                tasks[i] = task.to_dict()
                break
        self._save_tasks(tasks)
        return task

    def delete(self, task_id: str) -> bool:
        """Remove task by ID.

        Args:
            task_id: ID of task to delete

        Returns:
            True if task was deleted, False if not found
        """
        tasks = self._load_tasks()
        original_len = len(tasks)
        tasks = [t for t in tasks if t['id'] != task_id]
        if len(tasks) < original_len:
            self._save_tasks(tasks)
            return True
        return False

    def count(self) -> int:
        """Get total number of tasks.

        Returns:
            Number of tasks in storage
        """
        return len(self._load_tasks())

    def get_statistics(self) -> dict:
        """Calculate task statistics for dashboard.

        Returns:
            Dictionary containing:
            - total: Total task count
            - by_status: Count per status
            - by_priority: Count per priority
            - overdue: Count of overdue tasks
            - completion_rate: Percentage of completed tasks
            - total_time_spent: Sum of time spent on completed tasks
        """
        tasks = self.get_all()
        total = len(tasks)

        status_counts = Counter(t.status for t in tasks)
        prio_counts = Counter(t.priority for t in tasks)
        by_status = {s.name.lower(): status_counts[s] for s in TaskStatus}
        by_priority = {p.name.lower(): prio_counts[p] for p in Priority}

        overdue = sum(1 for t in tasks if t.is_overdue())
        total_time = sum(t.time_spent for t in tasks if t.status == TaskStatus.DONE)

        return {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'overdue': overdue,
            'completion_rate': round(by_status['done'] / total * 100, 1) if total > 0 else 0,
            'total_time_spent': total_time
        }

    # ── Tag registry ──
    # Bulk-append is the one tag operation _JsonCollection doesn't offer
    # directly (add() is one-at-a-time, each a separate file write).

    def add_tag_defs(self, tags: list[Tag]) -> None:
        """Append several at once — one file write (used by the migration)."""
        if not tags:
            return
        items = self.tags.load_raw()
        items.extend(t.to_dict() for t in tags)
        self.tags.save_raw(items)

    # ── Notifications ──
    # A few read/unread helpers that need raw-dict access beyond plain CRUD.

    def get_unread_notifications(self) -> list[Notification]:
        return [n for n in self.notifications.all() if not n.is_read]

    def mark_notification_read(self, notif_id: str) -> bool:
        items = self.notifications.load_raw()
        for n in items:
            if n['id'] == notif_id:
                n['is_read'] = True
                self.notifications.save_raw(items)
                return True
        return False

    def mark_all_notifications_read(self) -> int:
        items = self.notifications.load_raw()
        count = sum(1 for n in items if not n['is_read'])
        if count:
            for n in items:
                n['is_read'] = True
            self.notifications.save_raw(items)
        return count

    def clear_old_notifications(self, max_count: int = 100) -> int:
        """Keep only the last max_count notifications, delete older ones."""
        items = self.notifications.load_raw()
        if len(items) <= max_count:
            return 0
        items = items[-max_count:]
        self.notifications.save_raw(items)
        return len(items)

    # ── Export / Import ──

    def _collections(self) -> dict[str, "_JsonCollection"]:
        return {
            "sprints": self.sprints,
            "versions": self.versions,
            "templates": self.templates,
            "categories": self.categories,
            "recurring": self.recurring,
            "notifications": self.notifications,
            "tags": self.tags,
            "project_templates": self.project_templates,
        }

    def export_all(self) -> dict:
        """Export all data as a dict for JSON serialization."""
        out = {"tasks": self._load_tasks()}
        out.update({key: coll.load_raw() for key, coll in self._collections().items()})
        out["exported_at"] = datetime.now().isoformat()
        out["schema_version"] = EXPORT_SCHEMA_VERSION
        return out

    def import_all(self, data: dict, overwrite: bool = False) -> dict:
        """Import all data from a dict (merge or replace).

        Args:
            data: Dict with 'tasks', 'sprints', 'versions', 'templates',
                   'categories', 'recurring', 'notifications'.
            overwrite: If True, replace all existing data.

        Returns:
            Dict with counts per entity imported.
        """
        entity_keys = [("tasks", self._load_tasks, self._save_tasks)]
        entity_keys += [
            (key, coll.load_raw, coll.save_raw)
            for key, coll in self._collections().items()
        ]

        result = {}
        for key, loader, saver in entity_keys:
            new_items = data.get(key, [])
            if overwrite:
                saver(new_items)
                result[f"{key}_imported"] = len(new_items)
            else:
                existing = loader()
                existing_ids = {item.get('id') for item in existing if item.get('id')}
                added = [item for item in new_items if item.get('id') not in existing_ids]
                saver(existing + added)
                result[f"{key}_imported"] = len(added)

        return result
