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
import itertools
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Protocol

_tmp_counter = itertools.count()
_write_lock = threading.Lock()  # serialize JSON writes (they are short and rare)

from .models import Task, TaskStatus, Sprint, VersionRelease, TaskTemplate, Category, RecurringTask, Notification

log = logging.getLogger(__name__)


def _coerce_list(raw) -> list:
    """Normalize whatever json.load returned into a list of records.

    Tolerates the legacy ``{"tasks": [...], "categories": [...], ...}`` shape
    that older seed code wrote, and anything unexpected -> [].
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        inner = raw.get("tasks")
        return inner if isinstance(inner, list) else []
    return []


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
            data = _coerce_list(json.loads(raw_bytes.decode(enc)))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
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
    """Atomically write *items* as pretty JSON to *path*.

    Writes to a per-writer temp file then ``os.replace`` (atomic on POSIX and
    Windows), so a crash mid-write never leaves a half-written file and
    concurrent writers don't clobber each other's temp file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{next(_tmp_counter)}.tmp")
    with _write_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            # os.replace can transiently fail on Windows (AV / lingering handle).
            for attempt in range(5):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass


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

    def by_id(self, item_id: str) -> Optional[T]:
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
        self._task_cache: Optional[list[dict]] = None
        self._ensure_db_exists()

        # One CRUD store per secondary entity, all sidecar files next to the
        # task DB: ``tasks_sprints.json``, ``tasks_versions.json``, …
        def _side(suffix: str) -> Path:
            return self.db_path.parent / f"{self.db_path.stem}_{suffix}.json"

        self._sprints = _JsonCollection(_side("sprints"), Sprint.from_dict, "sprint")
        self._versions = _JsonCollection(_side("versions"), VersionRelease.from_dict, "version")
        self._templates = _JsonCollection(_side("templates"), TaskTemplate.from_dict, "template")
        self._categories = _JsonCollection(_side("categories"), Category.from_dict, "category")
        self._recurring = _JsonCollection(_side("recurring"), RecurringTask.from_dict, "recurring task")
        self._notifications = _JsonCollection(_side("notifications"), Notification.from_dict, "notification")

    def _ensure_db_exists(self) -> None:
        """Create database file if it doesn't exist."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

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
    
    def get_by_id(self, task_id: str) -> Optional[Task]:
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
        
        by_status = {
            'todo': len([t for t in tasks if t.status == TaskStatus.TODO]),
            'in_progress': len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            'done': len([t for t in tasks if t.status == TaskStatus.DONE])
        }
        
        by_priority = {
            'low': len([t for t in tasks if t.priority.name == 'LOW']),
            'medium': len([t for t in tasks if t.priority.name == 'MEDIUM']),
            'high': len([t for t in tasks if t.priority.name == 'HIGH']),
            'critical': len([t for t in tasks if t.priority.name == 'CRITICAL']),
        }
        
        overdue = len([t for t in tasks if t.is_overdue()])
        
        # Total time spent on completed tasks
        total_time = sum(t.time_spent for t in tasks if t.status == TaskStatus.DONE)
        
        return {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'overdue': overdue,
            'completion_rate': round(by_status['done'] / total * 100, 1) if total > 0 else 0,
            'total_time_spent': total_time
        }

    # ── Secondary entities ─────────────────────────────────────────────
    # Sprints / versions / templates / categories / recurring tasks are all
    # plain id-keyed CRUD; each just forwards to its _JsonCollection.

    def get_all_sprints(self) -> list[Sprint]:
        return self._sprints.all()

    def get_sprint_by_id(self, sprint_id: str) -> Optional[Sprint]:
        return self._sprints.by_id(sprint_id)

    def add_sprint(self, sprint: Sprint) -> Sprint:
        return self._sprints.add(sprint)

    def update_sprint(self, sprint: Sprint) -> Sprint:
        return self._sprints.update(sprint)

    def delete_sprint(self, sprint_id: str) -> bool:
        return self._sprints.delete(sprint_id)

    def get_all_versions(self) -> list[VersionRelease]:
        return self._versions.all()

    def get_version_by_id(self, version_id: str) -> Optional[VersionRelease]:
        return self._versions.by_id(version_id)

    def add_version(self, version: VersionRelease) -> VersionRelease:
        return self._versions.add(version)

    def update_version(self, version: VersionRelease) -> VersionRelease:
        return self._versions.update(version)

    def delete_version(self, version_id: str) -> bool:
        return self._versions.delete(version_id)

    def get_all_templates(self) -> list[TaskTemplate]:
        return self._templates.all()

    def get_template_by_id(self, template_id: str) -> Optional[TaskTemplate]:
        return self._templates.by_id(template_id)

    def add_template(self, template: TaskTemplate) -> TaskTemplate:
        return self._templates.add(template)

    def update_template(self, template: TaskTemplate) -> TaskTemplate:
        return self._templates.update(template)

    def delete_template(self, template_id: str) -> bool:
        return self._templates.delete(template_id)

    def get_all_categories(self) -> list[Category]:
        return self._categories.all()

    def get_category_by_id(self, category_id: str) -> Optional[Category]:
        return self._categories.by_id(category_id)

    def add_category(self, category: Category) -> Category:
        return self._categories.add(category)

    def update_category(self, category: Category) -> Category:
        return self._categories.update(category)

    def delete_category(self, category_id: str) -> bool:
        return self._categories.delete(category_id)

    def get_all_recurring(self) -> list[RecurringTask]:
        return self._recurring.all()

    def get_recurring_by_id(self, rec_id: str) -> Optional[RecurringTask]:
        return self._recurring.by_id(rec_id)

    def add_recurring(self, rec: RecurringTask) -> RecurringTask:
        return self._recurring.add(rec)

    def update_recurring(self, rec: RecurringTask) -> RecurringTask:
        return self._recurring.update(rec)

    def delete_recurring(self, rec_id: str) -> bool:
        return self._recurring.delete(rec_id)

    # ── Notifications ──
    # CRUD plus a few read/unread helpers that need raw-dict access.

    def get_all_notifications(self) -> list[Notification]:
        return self._notifications.all()

    def get_unread_notifications(self) -> list[Notification]:
        return [n for n in self.get_all_notifications() if not n.is_read]

    def add_notification(self, notification: Notification) -> Notification:
        return self._notifications.add(notification)

    def delete_notification(self, notif_id: str) -> bool:
        return self._notifications.delete(notif_id)

    def mark_notification_read(self, notif_id: str) -> bool:
        items = self._notifications.load_raw()
        for n in items:
            if n['id'] == notif_id:
                n['is_read'] = True
                self._notifications.save_raw(items)
                return True
        return False

    def mark_all_notifications_read(self) -> int:
        items = self._notifications.load_raw()
        count = sum(1 for n in items if not n['is_read'])
        if count:
            for n in items:
                n['is_read'] = True
            self._notifications.save_raw(items)
        return count

    def clear_old_notifications(self, max_count: int = 100) -> int:
        """Keep only the last max_count notifications, delete older ones."""
        items = self._notifications.load_raw()
        if len(items) <= max_count:
            return 0
        items = items[-max_count:]
        self._notifications.save_raw(items)
        return len(items)

    # ── Data Integrity ──

    def repair_corrupted_tasks(self) -> dict:
        """Attempt to repair corrupted task data.

        Reads raw JSON, tries to deserialize each task.
        Removes unparseable entries and re-saves.

        Returns dict: {total, valid, removed}
        """
        self._task_cache = None  # force a fresh read from disk
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                raw_items = _coerce_list(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError):
            # File is completely corrupted — reset to empty
            self._save_tasks([])
            return {"total": 0, "valid": 0, "removed": 0, "reset": True}

        valid = []
        removed = 0
        for item in raw_items:
            try:
                Task.from_dict(item)
                valid.append(item)
            except Exception:
                removed += 1

        self._save_tasks(valid)
        return {"total": len(raw_items), "valid": len(valid), "removed": removed}

    # ── Export / Import ──

    def _collections(self) -> dict[str, "_JsonCollection"]:
        return {
            "sprints": self._sprints,
            "versions": self._versions,
            "templates": self._templates,
            "categories": self._categories,
            "recurring": self._recurring,
            "notifications": self._notifications,
        }

    def export_all(self) -> dict:
        """Export all data as a dict for JSON serialization."""
        out = {"tasks": self._load_tasks()}
        out.update({key: coll.load_raw() for key, coll in self._collections().items()})
        out["exported_at"] = datetime.now().isoformat()
        out["version"] = "0.0.0.0.1"
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
