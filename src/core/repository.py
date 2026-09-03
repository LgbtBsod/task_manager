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
from typing import Optional, List

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
    """Read a JSON list from *path*, backing up and clearing a corrupt file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _coerce_list(json.load(f))
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        try:
            backup = path.with_name(
                f"{path.stem}.corrupt-{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
            )
            shutil.copy2(path, backup)
            log.error("Corrupt JSON at %s (%s); backed up to %s", path, exc, backup.name)
        except Exception:
            log.error("Corrupt JSON at %s (%s); backup failed", path, exc)
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

    # ── Sprints ──

    def _sprints_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_sprints.json")

    def _load_sprints(self) -> list[dict]:
        path = self._sprints_path()
        return _read_json_list(path)

    def _save_sprints(self, sprints: list[dict]) -> None:
        _write_json_list(self._sprints_path(), sprints)

    def get_all_sprints(self) -> list[Sprint]:
        return _parse_each(self._load_sprints(), Sprint.from_dict, "sprint")

    def get_sprint_by_id(self, sprint_id: str) -> Optional[Sprint]:
        for s in self.get_all_sprints():
            if s.id == sprint_id:
                return s
        return None

    def add_sprint(self, sprint: Sprint) -> Sprint:
        sprints = self._load_sprints()
        sprints.append(sprint.to_dict())
        self._save_sprints(sprints)
        return sprint

    def update_sprint(self, sprint: Sprint) -> Sprint:
        sprints = self._load_sprints()
        for i, s in enumerate(sprints):
            if s['id'] == sprint.id:
                sprints[i] = sprint.to_dict()
                break
        self._save_sprints(sprints)
        return sprint

    def delete_sprint(self, sprint_id: str) -> bool:
        sprints = self._load_sprints()
        original_len = len(sprints)
        sprints = [s for s in sprints if s['id'] != sprint_id]
        if len(sprints) < original_len:
            self._save_sprints(sprints)
            return True
        return False

    # ── Versions / Releases ──

    def _versions_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_versions.json")

    def _load_versions(self) -> list[dict]:
        path = self._versions_path()
        return _read_json_list(path)

    def _save_versions(self, versions: list[dict]) -> None:
        _write_json_list(self._versions_path(), versions)

    def get_all_versions(self) -> list[VersionRelease]:
        return _parse_each(self._load_versions(), VersionRelease.from_dict, "version")

    def get_version_by_id(self, version_id: str) -> Optional[VersionRelease]:
        for v in self.get_all_versions():
            if v.id == version_id:
                return v
        return None

    def add_version(self, version: VersionRelease) -> VersionRelease:
        versions = self._load_versions()
        versions.append(version.to_dict())
        self._save_versions(versions)
        return version

    def update_version(self, version: VersionRelease) -> VersionRelease:
        versions = self._load_versions()
        for i, v in enumerate(versions):
            if v['id'] == version.id:
                versions[i] = version.to_dict()
                break
        self._save_versions(versions)
        return version

    def delete_version(self, version_id: str) -> bool:
        versions = self._load_versions()
        original_len = len(versions)
        versions = [v for v in versions if v['id'] != version_id]
        if len(versions) < original_len:
            self._save_versions(versions)
            return True
        return False

    # ── Templates ──

    def _templates_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_templates.json")

    def _load_templates(self) -> list[dict]:
        path = self._templates_path()
        return _read_json_list(path)

    def _save_templates(self, items: list[dict]) -> None:
        _write_json_list(self._templates_path(), items)

    def get_all_templates(self) -> list[TaskTemplate]:
        return _parse_each(self._load_templates(), TaskTemplate.from_dict, "template")

    def get_template_by_id(self, template_id: str) -> Optional[TaskTemplate]:
        for t in self.get_all_templates():
            if t.id == template_id:
                return t
        return None

    def add_template(self, template: TaskTemplate) -> TaskTemplate:
        items = self._load_templates()
        items.append(template.to_dict())
        self._save_templates(items)
        return template

    def update_template(self, template: TaskTemplate) -> TaskTemplate:
        items = self._load_templates()
        for i, t in enumerate(items):
            if t['id'] == template.id:
                items[i] = template.to_dict()
                break
        self._save_templates(items)
        return template

    def delete_template(self, template_id: str) -> bool:
        items = self._load_templates()
        before = len(items)
        items = [t for t in items if t['id'] != template_id]
        if len(items) < before:
            self._save_templates(items)
            return True
        return False

    # ── Categories ──

    def _categories_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_categories.json")

    def _load_categories(self) -> list[dict]:
        path = self._categories_path()
        return _read_json_list(path)

    def _save_categories(self, items: list[dict]) -> None:
        _write_json_list(self._categories_path(), items)

    def get_all_categories(self) -> list[Category]:
        return _parse_each(self._load_categories(), Category.from_dict, "category")

    def get_category_by_id(self, category_id: str) -> Optional[Category]:
        for c in self.get_all_categories():
            if c.id == category_id:
                return c
        return None

    def add_category(self, category: Category) -> Category:
        items = self._load_categories()
        items.append(category.to_dict())
        self._save_categories(items)
        return category

    def update_category(self, category: Category) -> Category:
        items = self._load_categories()
        for i, c in enumerate(items):
            if c['id'] == category.id:
                items[i] = category.to_dict()
                break
        self._save_categories(items)
        return category

    def delete_category(self, category_id: str) -> bool:
        items = self._load_categories()
        before = len(items)
        items = [c for c in items if c['id'] != category_id]
        if len(items) < before:
            self._save_categories(items)
            return True
        return False

    # ── Recurring Tasks ──

    def _recurring_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_recurring.json")

    def _load_recurring(self) -> list[dict]:
        path = self._recurring_path()
        return _read_json_list(path)

    def _save_recurring(self, items: list[dict]) -> None:
        _write_json_list(self._recurring_path(), items)

    def get_all_recurring(self) -> list[RecurringTask]:
        return _parse_each(self._load_recurring(), RecurringTask.from_dict, "recurring task")

    def get_recurring_by_id(self, rec_id: str) -> Optional[RecurringTask]:
        for r in self.get_all_recurring():
            if r.id == rec_id:
                return r
        return None

    def add_recurring(self, rec: RecurringTask) -> RecurringTask:
        items = self._load_recurring()
        items.append(rec.to_dict())
        self._save_recurring(items)
        return rec

    def update_recurring(self, rec: RecurringTask) -> RecurringTask:
        items = self._load_recurring()
        for i, r in enumerate(items):
            if r['id'] == rec.id:
                items[i] = rec.to_dict()
                break
        self._save_recurring(items)
        return rec

    def delete_recurring(self, rec_id: str) -> bool:
        items = self._load_recurring()
        before = len(items)
        items = [r for r in items if r['id'] != rec_id]
        if len(items) < before:
            self._save_recurring(items)
            return True
        return False

    # ── Notifications ──

    def _notifications_path(self) -> Path:
        return self.db_path.parent / (self.db_path.stem + "_notifications.json")

    def _load_notifications(self) -> list[dict]:
        path = self._notifications_path()
        return _read_json_list(path)

    def _save_notifications(self, items: list[dict]) -> None:
        _write_json_list(self._notifications_path(), items)

    def get_all_notifications(self) -> list[Notification]:
        return _parse_each(self._load_notifications(), Notification.from_dict, "notification")

    def get_unread_notifications(self) -> list[Notification]:
        return [n for n in self.get_all_notifications() if not n.is_read]

    def add_notification(self, notification: Notification) -> Notification:
        items = self._load_notifications()
        items.append(notification.to_dict())
        self._save_notifications(items)
        return notification

    def mark_notification_read(self, notif_id: str) -> bool:
        items = self._load_notifications()
        for n in items:
            if n['id'] == notif_id:
                n['is_read'] = True
                self._save_notifications(items)
                return True
        return False

    def mark_all_notifications_read(self) -> int:
        items = self._load_notifications()
        count = 0
        for n in items:
            if not n['is_read']:
                n['is_read'] = True
                count += 1
        if count > 0:
            self._save_notifications(items)
        return count

    def delete_notification(self, notif_id: str) -> bool:
        items = self._load_notifications()
        before = len(items)
        items = [n for n in items if n['id'] != notif_id]
        if len(items) < before:
            self._save_notifications(items)
            return True
        return False

    def clear_old_notifications(self, max_count: int = 100) -> int:
        """Keep only the last max_count notifications, delete older ones."""
        items = self._load_notifications()
        if len(items) <= max_count:
            return 0
        items = items[-max_count:]
        self._save_notifications(items)
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

    def export_all(self) -> dict:
        """Export all data as a dict for JSON serialization."""
        return {
            "tasks": self._load_tasks(),
            "sprints": self._load_sprints(),
            "versions": self._load_versions(),
            "templates": self._load_templates(),
            "categories": self._load_categories(),
            "recurring": self._load_recurring(),
            "notifications": self._load_notifications(),
            "exported_at": datetime.now().isoformat(),
            "version": "0.0.0.0.1",
        }

    def import_all(self, data: dict, overwrite: bool = False) -> dict:
        """Import all data from a dict (merge or replace).

        Args:
            data: Dict with 'tasks', 'sprints', 'versions', 'templates',
                   'categories', 'recurring', 'notifications'.
            overwrite: If True, replace all existing data.

        Returns:
            Dict with counts per entity imported.
        """
        entity_keys = [
            ("tasks", self._load_tasks, self._save_tasks),
            ("sprints", self._load_sprints, self._save_sprints),
            ("versions", self._load_versions, self._save_versions),
            ("templates", self._load_templates, self._save_templates),
            ("categories", self._load_categories, self._save_categories),
            ("recurring", self._load_recurring, self._save_recurring),
            ("notifications", self._load_notifications, self._save_notifications),
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
