"""Task Manager - Business Logic Service Layer

Full Jira-like service: CRUD, tags, subtasks, comments, task links,
audit history, bulk operations, search, clone, assignee management.
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime

from .models import (
    WORKFLOW_TRANSITIONS,
    LinkType,
    Priority,
    Resolution,
    SubTask,
    Task,
    TaskModel,
    TaskStatus,
    TaskType,
    Urgency,
)
from .repository import TaskRepository

log = logging.getLogger(__name__)


def _to_priority(value: str) -> Priority:
    """A stored priority string → ``Priority``; unknown values fall back to MEDIUM."""
    try:
        return Priority(value)
    except ValueError:
        return Priority.MEDIUM


def _clean_tag_names(tag_names: list[str]) -> set[str]:
    """Lower-cased, blank/``None``-filtered tag names — the one place
    ``bulk_transition_*`` normalizes its ``tag_names`` input."""
    return {n.strip().lower() for n in tag_names if n and n.strip()}


class TaskService:
    """Business logic service for task management."""

    def __init__(self, repository: TaskRepository | None = None):
        self.repo = repository or TaskRepository()
        from .service_catalog import CategoryService, RecurringService, TemplateService
        from .service_notifications import NotificationService
        from .service_sprints import SprintService
        from .service_tags import TagService
        from .service_versions import VersionService
        from .service_workflow import WorkflowService
        self.sprints = SprintService(self.repo)
        self.versions = VersionService(self.repo)
        self.templates = TemplateService(self.repo)
        self.categories = CategoryService(self.repo)
        self.recurring = RecurringService(self.repo)
        self.notifications = NotificationService(self.repo)
        self.tags = TagService(self.repo)
        self.workflow = WorkflowService(self.repo)
        from .analytics import BoardAnalytics
        self.analytics = BoardAnalytics(self.repo, self.sprints)
        self._collaborators = (self.sprints, self.versions, self.templates,
                               self.categories, self.recurring, self.notifications,
                               self.tags, self.workflow, self.analytics)

    def __getattr__(self, name: str):
        # Delegate sprint/version/… calls to the composed services without a
        # wall of one-line forwarders. Only fires for names not on TaskService.
        for collab in self.__dict__.get("_collaborators", ()):
            member = getattr(collab, name, None)
            if member is not None:
                return member
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")

    def _edit(self, task_id: str, mutate: Callable[[Task], object]) -> Task | None:
        """load task → apply ``mutate`` → bump timestamp → save.

        ``mutate`` records its own audit entry and returns ``False`` to abort
        (task not found still returns ``None``).
        """
        task = self.repo.get_by_id(task_id)
        if task is None:
            return None
        if mutate(task) is False:
            return None
        task.update_timestamp()
        return self.repo.update(task)

    # ── Basic CRUD ──

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        due_date: str | None = None,
        start_date: str | None = None,
        tags: list[str] | None = None,
        assignee: str | None = None,
        story_points: int | None = None,
        task_type: str = TaskType.TASK.value,
        time_spent: float = 0.0,
        urgency: str = Urgency.NORMAL.value,
        watchers: list[str] | None = None,
        epic_link: str | None = None,
        components: list[str] | None = None,
        labels: list[str] | None = None,
        version_id: str | None = None,
        original_estimate: float = 0.0,
    ) -> Task:
        log.info(f"Creating task: {title[:50]}")
        try:
            # Task.__post_init__ runs the (single) pydantic validation pass.
            task = Task(
                title=title.strip(),
                description=description.strip(),
                priority=priority, due_date=due_date,
                start_date=start_date, tags=tags or [],
                assignee=assignee, story_points=story_points,
                task_type=task_type, time_spent=time_spent,
            )
            if urgency != Urgency.NORMAL.value:
                task.urgency = urgency
            if watchers:
                task.watchers = list(set(watchers))
            if epic_link:
                task.epic_link = epic_link
            if components:
                task.components = list(set(c.strip() for c in components if c.strip()))
            if labels:
                task.labels = sorted(set(l.strip().lower() for l in labels if l.strip()))
            if version_id:
                task.version_id = version_id
            if original_estimate > 0:
                task.original_estimate = original_estimate
        except (ValueError, TypeError) as e:
            log.error(f"Validation failed for task '{title}': {e}")
            raise ValueError(f"Validation failed: {e}") from e

        created = self.repo.add(task)
        log.info(f"Task created: id={created.id}")
        return created

    def get_all_tasks(self) -> list[Task]:
        return self.repo.get_all()

    def get_task(self, task_id: str) -> Task | None:
        return self.repo.get_by_id(task_id)

    def update_task_status(
        self, task_id: str, status: TaskStatus, *,
        auto_start_unblocked: bool = False, auto_close_epic: bool = False,
    ) -> Task | None:
        """``auto_start_unblocked`` / ``auto_close_epic`` are opt-in workflow
        advances applied once ``status`` lands on Done — see
        ``WorkflowService.plan_after_done``. Both default off; a caller not
        passing them gets today's plain status change."""
        task = self.repo.get_by_id(task_id)
        if not task:
            log.warning(f"update_task_status: task {task_id} not found")
            return None
        old_status = task.status
        task.status = status
        task.record_change("status", old_status.value, status.value)
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Task {task_id}: {old_status.value} -> {status.value}")

        if status == TaskStatus.DONE and (auto_start_unblocked or auto_close_epic):
            plan = self.workflow.plan_after_done(updated)
            if auto_start_unblocked:
                for dep in plan["unblocked"]:
                    self.update_task_status(dep.id, TaskStatus.IN_PROGRESS)
                    log.info("Workflow: %s auto-started (unblocked by %s)", dep.id, task_id)
            if auto_close_epic and plan["epic_to_close"]:
                self.update_task_status(plan["epic_to_close"], TaskStatus.DONE,
                                        auto_start_unblocked=auto_start_unblocked)
                log.info("Workflow: epic %s auto-closed (all children done)",
                        plan["epic_to_close"])
        return updated

    def set_on_hold(self, task_id: str, on_hold: bool) -> Task | None:
        """Pause/resume a task in place — it keeps its column and status;
        the board greys it and its deadline warnings snooze while paused
        (see DeadlineWatcher)."""
        def m(task: Task):
            if task.on_hold == on_hold:
                return False
            task.record_change("on_hold", str(task.on_hold), str(on_hold))
            task.on_hold = on_hold
        return self._edit(task_id, m)

    def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        due_date: str | None = None,
        time_spent: float | None = None,
        start_date: str | None = None,
        status: TaskStatus | None = None,
        tags: list[str] | None = None,
        assignee: str | None = None,
        story_points: int | None = None,
        task_type: str | None = None,
        urgency: str | None = None,
        watchers: list[str] | None = None,
    ) -> Task | None:
        task = self.repo.get_by_id(task_id)
        if not task:
            log.warning(f"update_task: task {task_id} not found")
            return None

        # Track changes for audit
        def _track(field: str, old: str, new_val):
            if str(old) != str(new_val):
                task.record_change(field, str(old), str(new_val))

        if title is not None:
            _track("title", task.title, title.strip())
            task.title = title.strip()
        if description is not None:
            _track("description", task.description[:50], description.strip()[:50])
            task.description = description.strip()
        if priority is not None:
            _track("priority", task.priority.value, priority.value)
            task.priority = priority
        if due_date is not None:
            _track("due_date", task.due_date or "", due_date)
            task.due_date = due_date
        if time_spent is not None:
            _track("time_spent", task.time_spent, max(0, time_spent))
            task.time_spent = max(0, time_spent)
        if start_date is not None:
            _track("start_date", task.start_date or "", start_date)
            task.start_date = start_date
        if status is not None:
            _track("status", task.status.value, status.value)
            task.status = status
        if tags is not None:
            _track("tags", str(task.tags), str(tags))
            task.tags = tags
        if assignee is not None:
            _track("assignee", task.assignee or "", assignee)
            task.assignee = assignee
        if story_points is not None:
            _track("story_points", task.story_points or 0, story_points)
            task.story_points = story_points
        if task_type is not None:
            _track("task_type", task.task_type, task_type)
            task.task_type = task_type
        if urgency is not None:
            _track("urgency", task.urgency, urgency)
            task.urgency = urgency
        if watchers is not None:
            cleaned = sorted({w.strip() for w in watchers if w and w.strip()})
            _track("watchers", str(task.watchers), str(cleaned))
            task.watchers = cleaned

        try:
            TaskModel.from_task(task)
        except Exception as e:
            log.error(f"Validation failed on update for {task_id}: {e}")
            raise ValueError(f"Validation failed: {e}") from e

        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Task updated: {task_id}")
        return updated

    def delete_task(self, task_id: str) -> bool:
        task = self.repo.get_by_id(task_id)
        if not task:
            return False
        result = self.repo.delete(task_id)
        if result:
            log.info(f"Task deleted: {task_id}")
        return result

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        return self.repo.get_by_status(status)

    def get_overdue_tasks(self) -> list[Task]:
        return [t for t in self.get_all_tasks() if t.is_overdue()]

    # ── Tags ──

    def get_tasks_by_tag(self, tag: str) -> list[Task]:
        """Find tasks by tag (case-insensitive)."""
        tag_lower = tag.strip().lower()
        return [t for t in self.get_all_tasks() if tag_lower in t.tags]

    def get_all_tags(self) -> list[str]:
        """Get all unique tags across all tasks, sorted alphabetically."""
        tag_set = set()
        for t in self.get_all_tasks():
            tag_set.update(t.tags)
        return sorted(tag_set)

    # ── Subtasks ──

    def add_subtask(self, task_id: str, title: str) -> Task | None:
        """Add a subtask to a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        title = title.strip()

        def m(task: Task):
            task.subtasks.append(SubTask(title=title))
            task.record_change("subtask_added", "", title)

        return self._edit(task_id, m)

    def toggle_subtask(self, task_id: str, index: int) -> Task | None:
        """Toggle subtask completion."""
        def m(task: Task):
            if not task.toggle_subtask(index):
                return False
            sub = task.subtasks[index]
            task.record_change("subtask_toggled", sub.title, "done" if sub.done else "undone")

        return self._edit(task_id, m)

    def delete_subtask(self, task_id: str, index: int) -> Task | None:
        """Delete a subtask by index."""
        def m(task: Task):
            if not (0 <= index < len(task.subtasks)):
                return False
            task.record_change("subtask_deleted", task.subtasks.pop(index).title, "")

        return self._edit(task_id, m)

    # ── Comments ──

    def add_comment(self, task_id: str, author: str, text: str) -> Task | None:
        """Add a comment to a task."""
        author, text = author.strip(), text.strip()

        def m(task: Task):
            task.add_comment(author, text)
            task.record_change("comment_added", "", f"by {author}: {text[:50]}")

        return self._edit(task_id, m)

    def delete_comment(self, task_id: str, comment_id: str) -> Task | None:
        """Delete a comment from a task."""
        def m(task: Task):
            if not task.delete_comment(comment_id):
                return False
            task.record_change("comment_deleted", comment_id, "")

        return self._edit(task_id, m)

    # ── Task Links ──

    def _blocked_by_reaches(self, start_id: str, goal_id: str, seen: set | None = None) -> bool:
        """True if ``start_id`` transitively depends on ``goal_id`` via the
        existing BLOCKED_BY graph — used to reject a link that would close a
        dependency loop (two tasks permanently blocking each other with no
        way out except manually editing the links back apart)."""
        seen = seen if seen is not None else set()
        if start_id in seen:
            return False
        seen.add(start_id)
        task = self.repo.get_by_id(start_id)
        if not task:
            return False
        for link in task.links:
            if link.link_type != LinkType.BLOCKED_BY.value:
                continue
            if link.target_task_id == goal_id or self._blocked_by_reaches(link.target_task_id, goal_id, seen):
                return True
        return False

    def add_task_link(self, task_id: str, target_task_id: str, link_type: str = "relates_to") -> Task | None:
        """Link two tasks."""
        if task_id == target_task_id:
            raise ValueError("Cannot link a task to itself")
        # Validate target exists
        if not self.repo.get_by_id(target_task_id):
            raise ValueError(f"Target task {target_task_id} not found")
        # Validate link type
        if link_type not in LinkType:                       # Enum value-membership (3.12+)
            raise ValueError(f"Invalid link_type. Must be one of: {[lt.value for lt in LinkType]}")
        if link_type == LinkType.BLOCKED_BY.value and self._blocked_by_reaches(target_task_id, task_id):
            raise ValueError("This would create a dependency cycle")

        task = self.repo.get_by_id(task_id)
        if not task:
            return None

        # Check for duplicate link
        for existing in task.links:
            if existing.target_task_id == target_task_id and existing.link_type == link_type:
                return task  # Already linked

        task.add_link(target_task_id, link_type)
        # Auto-add reverse link for symmetric types
        if link_type in (LinkType.RELATES_TO.value, LinkType.DUPLICATES.value, LinkType.CLONES.value):
            target = self.repo.get_by_id(target_task_id)
            if target:
                target.add_link(task_id, link_type)   # symmetric
                target.update_timestamp()
                self.repo.update(target)

        task.record_change("link_added", "", f"{link_type} -> {target_task_id}")
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Link added: {task_id} {link_type} -> {target_task_id}")
        return updated

    def remove_task_link(self, task_id: str, target_task_id: str) -> Task | None:
        """Remove a link between tasks."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        if not task.remove_link(target_task_id):
            return task  # Link didn't exist
        # Remove reverse link too
        target = self.repo.get_by_id(target_task_id)
        if target:
            target.remove_link(task_id)
            target.update_timestamp()
            self.repo.update(target)

        task.record_change("link_removed", target_task_id, "")
        task.update_timestamp()
        updated = self.repo.update(task)
        return updated

    def get_linked_tasks(self, task_id: str) -> dict:
        """Get all tasks linked to this task. Returns dict by link_type -> [Task]."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return {}
        result = {}
        for link in task.links:
            target = self.repo.get_by_id(link.target_task_id)
            if target:
                result.setdefault(link.link_type, []).append(target)
        return result

    # ── Bulk Operations ──

    def bulk_delete(self, task_ids: list[str]) -> int:
        """Delete multiple tasks. Returns count of deleted tasks."""
        count = 0
        for tid in task_ids:
            if self.delete_task(tid):
                count += 1
        log.info(f"Bulk delete: {count}/{len(task_ids)} tasks")
        return count

    def bulk_status_change(
        self, task_ids: list[str], status: TaskStatus, *,
        auto_start_unblocked: bool = False, auto_close_epic: bool = False,
    ) -> int:
        """Change status of multiple tasks. Returns count of updated tasks."""
        count = 0
        for tid in task_ids:
            if self.update_task_status(tid, status, auto_start_unblocked=auto_start_unblocked,
                                       auto_close_epic=auto_close_epic):
                count += 1
        log.info(f"Bulk status change to {status.value}: {count}/{len(task_ids)} tasks")
        return count

    def bulk_transition_candidates(
        self,
        tag_names: list[str],
        from_statuses: list[TaskStatus],
        to_status: TaskStatus,
        *,
        match_all: bool = False,
    ) -> list[Task]:
        """Tasks that carry the wanted tag(s), sit in one of ``from_statuses``,
        and aren't already in ``to_status``. Pure read — no writes; this is what
        the bulk-transition panel's live preview count is built from, so it must
        never mutate. ``match_all`` False = task has ANY wanted tag; True = ALL.
        Statuses may be ``TaskStatus`` members or their raw string values.
        """
        wanted = _clean_tag_names(tag_names)
        if not wanted or not from_statuses:
            return []
        froms = {TaskStatus(s) for s in from_statuses}
        target = TaskStatus(to_status)
        out = []
        for t in self.get_all_tasks():
            if t.status not in froms or t.status == target:
                continue
            tags = set(t.tags)
            if (wanted <= tags) if match_all else (wanted & tags):
                out.append(t)
        return out

    def bulk_transition_by_tag(
        self,
        tag_names: list[str],
        from_statuses: list[TaskStatus],
        to_status: TaskStatus,
        *,
        match_all: bool = False,
        auto_start_unblocked: bool = False,
        auto_close_epic: bool = False,
    ) -> int:
        """Move every :meth:`bulk_transition_candidates` task to ``to_status``.
        Returns the count actually moved. Each move goes through
        ``update_task_status`` so it records the same ``status`` history entry a
        board drag would — mirrors the board: no ``WORKFLOW_TRANSITIONS`` check.
        """
        target = TaskStatus(to_status)
        cands = self.bulk_transition_candidates(
            tag_names, from_statuses, to_status, match_all=match_all)
        moved = self.bulk_status_change([t.id for t in cands], target,
                                        auto_start_unblocked=auto_start_unblocked,
                                        auto_close_epic=auto_close_epic)
        log.info("bulk_transition_by_tag tags=%s from=%s -> %s: %d moved",
                 sorted(_clean_tag_names(tag_names)),
                 [TaskStatus(s).value for s in from_statuses], target.value, moved)
        return moved

    # ── Search ──

    def search_tasks(self, query: str) -> list[Task]:
        """Full-text search across title, description, tags, assignee."""
        q = query.strip().lower()
        if not q:
            return self.get_all_tasks()
        results = []
        for t in self.get_all_tasks():
            searchable = " ".join([
                t.title, t.description, t.assignee or "",
                " ".join(t.tags),
            ]).lower()
            if q in searchable:
                results.append(t)
        log.debug(f"Search '{query}' returned {len(results)} results")
        return results

    # ── Assignee ──

    def get_tasks_by_assignee(self, assignee: str) -> list[Task]:
        """Get all tasks assigned to a person."""
        name = assignee.strip().lower()
        return [t for t in self.get_all_tasks()
                if t.assignee and t.assignee.lower() == name]

    def get_all_assignees(self) -> list[str]:
        """Get all unique assignees."""
        names = {t.assignee for t in self.get_all_tasks() if t.assignee}
        return sorted(names)

    # ── Filters (Jira-style) ──

    def filter_tasks(
        self,
        status: TaskStatus | None = None,
        priority: Priority | None = None,
        assignee: str | None = None,
        tag: str | None = None,
        task_type: str | None = None,
        urgency: str | None = None,
        is_overdue: bool | None = None,
        query: str | None = None,
    ) -> list[Task]:
        """Jira-style advanced task filtering with multiple criteria."""
        results = self.get_all_tasks()
        if status is not None:
            results = [t for t in results if t.status == status]
        if priority is not None:
            results = [t for t in results if t.priority == priority]
        if assignee is not None:
            name = assignee.strip().lower()
            results = [t for t in results if t.assignee and t.assignee.lower() == name]
        if tag is not None:
            tag_lower = tag.strip().lower()
            results = [t for t in results if tag_lower in t.tags]
        if task_type is not None:
            results = [t for t in results if t.task_type == task_type]
        if urgency is not None:
            results = [t for t in results if t.urgency == urgency]
        if is_overdue is not None:
            results = [t for t in results if t.is_overdue() == is_overdue]
        if query is not None:
            q = query.strip().lower()
            if q:
                results = [t for t in results
                           if q in t.title.lower() or q in t.description.lower()
                           or q in (t.assignee or "").lower()]
        log.debug(f"filter_tasks returned {len(results)} tasks")
        return results

    # ── Move Task (Jira workflow transition) ──

    def move_task(self, task_id: str, direction: str = "forward") -> Task | None:
        """Move task forward or backward through the workflow.

        Args:
            task_id: Task to move.
            direction: 'forward' (Todo->In Progress->Done) or 'backward' (reverse).

        Returns:
            Updated task or None if not found / already at boundary.
        """
        task = self.repo.get_by_id(task_id)
        if not task:
            return None

        workflow = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
        try:
            current_idx = workflow.index(task.status)
        except ValueError:
            return None

        if direction == "forward":
            new_idx = current_idx + 1
        elif direction == "backward":
            new_idx = current_idx - 1
        else:
            raise ValueError(f"Invalid direction: {direction}. Use 'forward' or 'backward'.")

        if 0 <= new_idx < len(workflow):
            return self.update_task_status(task_id, workflow[new_idx])
        return task  # Already at boundary

    # ── Watchers ──

    def add_watcher(self, task_id: str, watcher: str) -> Task | None:
        """Add a watcher to a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        watcher_clean = watcher.strip()
        if watcher_clean and watcher_clean not in task.watchers:
            task.watchers.append(watcher_clean)
            task.record_change("watcher_added", "", watcher_clean)
            task.update_timestamp()
            updated = self.repo.update(task)
            log.info(f"Watcher {watcher_clean} added to {task_id}")
            return updated
        return task

    def remove_watcher(self, task_id: str, watcher: str) -> Task | None:
        """Remove a watcher from a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        watcher_clean = watcher.strip()
        before = len(task.watchers)
        task.watchers = [w for w in task.watchers if w.lower() != watcher_clean.lower()]
        if len(task.watchers) < before:
            task.record_change("watcher_removed", watcher_clean, "")
            task.update_timestamp()
            updated = self.repo.update(task)
            log.info(f"Watcher {watcher_clean} removed from {task_id}")
            return updated
        return task

    def get_all_watchers(self) -> list[str]:
        """Get all unique watchers across all tasks."""
        names = set()
        for t in self.get_all_tasks():
            names.update(t.watchers)
        return sorted(names)

    # ── Epic Link ──

    def _epic_link_reaches(self, start_id: str, goal_id: str, seen: set | None = None) -> bool:
        """True if ``start_id`` transitively reaches ``goal_id`` by following
        epic_link edges — guards against nesting an Epic under one of its own
        descendants (which would make the chain unresolvable)."""
        seen = seen if seen is not None else set()
        if start_id in seen:
            return False
        seen.add(start_id)
        if start_id == goal_id:
            return True
        task = self.repo.get_by_id(start_id)
        if not task or not task.epic_link:
            return False
        return self._epic_link_reaches(task.epic_link, goal_id, seen)

    def set_epic_link(self, task_id: str, epic_task_id: str | None) -> Task | None:
        """Set or clear the epic link for a task. A no-op call (unchanged
        value) skips the write — callers may pass it unconditionally on every
        edit-save without padding history with redundant entries."""
        def m(task: Task):
            if epic_task_id == task.epic_link:
                return False
            if epic_task_id:
                epic = self.repo.get_by_id(epic_task_id)
                if not epic:
                    raise ValueError(f"Epic task {epic_task_id} not found")
                if epic.task_type != TaskType.EPIC.value:
                    raise ValueError(f"Task {epic_task_id} is not an Epic")
                if self._epic_link_reaches(epic_task_id, task_id):
                    raise ValueError("This would create an epic hierarchy cycle")
            task.record_change("epic_link", task.epic_link or "", epic_task_id or "")
            task.epic_link = epic_task_id

        return self._edit(task_id, m)

    def get_epic_children(self, epic_id: str) -> list[Task]:
        """Get all tasks linked to an epic."""
        return [t for t in self.get_all_tasks() if t.epic_link == epic_id]

    # ── Time Tracking ──

    def log_time(self, task_id: str, hours: float) -> Task | None:
        """Add time spent to a task."""
        if hours <= 0:
            raise ValueError("Hours must be positive")

        def m(task: Task):
            old = task.time_spent
            task.time_spent = round(old + hours, 2)
            task.record_change("time_spent", str(old), str(task.time_spent))

        return self._edit(task_id, m)

    # ── Clone ──

    def clone_task(self, task_id: str, new_title: str | None = None) -> Task | None:
        """Clone a task. Copies title (+ '(copy)'), description, priority, tags, assignee, story_points, task_type."""
        original = self.repo.get_by_id(task_id)
        if not original:
            return None
        cloned = self.create_task(
            title=new_title or f"{original.title} (copy)",
            description=original.description,
            priority=original.priority,
            tags=list(original.tags),
            assignee=original.assignee,
            story_points=original.story_points,
            task_type=original.task_type,
        )
        # Copy subtasks (without done state)
        for sub in original.subtasks:
            self.add_subtask(cloned.id, sub.title)
        # Return final state from repo
        cloned = self.repo.get_by_id(cloned.id)
        log.info(f"Task cloned: {task_id} -> {cloned.id}")
        return cloned

    # ── History / Audit ──

    def get_task_history(self, task_id: str) -> list[dict]:
        """Get change history for a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return []
        return [h.to_dict() for h in task.history]

    # ── Components ──

    def get_all_components(self) -> list[str]:
        """Get all unique components across all tasks."""
        comps = set()
        for t in self.get_all_tasks():
            comps.update(t.components)
        return sorted(comps)

    def get_tasks_by_component(self, component: str) -> list[Task]:
        """Get all tasks with a specific component."""
        c = component.strip().lower()
        return [t for t in self.get_all_tasks() if c in [x.lower() for x in t.components]]

    # ── Task Ranking ──

    def set_task_rank(self, task_id: str, rank: int) -> Task | None:
        """Set manual rank for a task (lower = higher priority in backlog)."""
        def m(task: Task):
            old_rank = task.rank
            task.rank = max(0, rank)
            task.record_change("rank", str(old_rank), str(task.rank))
            log.info(f"Task {task_id} rank: {old_rank} -> {task.rank}")

        return self._edit(task_id, m)

    def get_backlog(self) -> list[Task]:
        """Get all Todo tasks sorted by rank (backlog view)."""
        return sorted(
            [t for t in self.get_all_tasks() if t.status == TaskStatus.TODO],
            key=lambda t: t.rank,
        )

    def reorder_backlog(self, task_ids: list[str]) -> bool:
        """Reorder the backlog by assigning ranks based on the provided order.

        Args:
            task_ids: Ordered list of task IDs (first = rank 0).

        Returns:
            True if all tasks were found and reordered.
        """
        for i, tid in enumerate(task_ids):
            task = self.repo.get_by_id(tid)
            if not task:
                return False
            task.rank = i
            task.update_timestamp()
            self.repo.update(task)
        log.info(f"Backlog reordered: {len(task_ids)} tasks")
        return True

    # ── Resolution ──

    def set_resolution(self, task_id: str, resolution: str) -> Task | None:
        """Set a task's resolution (Jira-style); moves it to Done."""
        if resolution not in Resolution:                    # Enum value-membership (3.12+)
            raise ValueError(f"Invalid resolution. Must be one of: {[r.value for r in Resolution]}")

        def m(task: Task):
            task.record_change("resolution", task.resolution or "", resolution)
            task.resolution = resolution
            if task.status != TaskStatus.DONE:
                task.record_change("status", task.status.value, TaskStatus.DONE.value)
                task.status = TaskStatus.DONE
            log.info(f"Resolution for {task_id}: {resolution}")

        return self._edit(task_id, m)

    def clear_resolution(self, task_id: str) -> Task | None:
        """Clear resolution and move a Done task back to In Progress."""
        def m(task: Task):
            task.record_change("resolution", task.resolution or "", "")
            task.resolution = None
            if task.status == TaskStatus.DONE:
                task.record_change("status", TaskStatus.DONE.value, TaskStatus.IN_PROGRESS.value)
                task.status = TaskStatus.IN_PROGRESS
            log.info(f"Resolution cleared for {task_id}")

        return self._edit(task_id, m)

    # ── Export / Import ──

    def export_data(self, file_path: str) -> str:
        """Export all tasks and sprints to a JSON file."""
        data = self.repo.export_all()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"Data exported to {file_path}")
        return file_path

    def import_data(self, file_path: str, overwrite: bool = False) -> dict:
        """Import tasks and sprints from a JSON file."""
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        result = self.repo.import_all(data, overwrite=overwrite)
        log.info(f"Import: {result}")
        return result

    def import_data_from_string(self, json_str: str, overwrite: bool = False) -> dict:
        """Import from a JSON string."""
        data = json.loads(json_str)
        result = self.repo.import_all(data, overwrite=overwrite)
        log.info(f"Import from string: {result}")
        return result

    # ── Workflow Transitions ──

    def get_allowed_transitions(self, task_id: str) -> list[str]:
        """Get list of allowed target statuses for a task based on workflow rules.

        Returns list of TaskStatus.value strings.
        """
        task = self.repo.get_by_id(task_id)
        if not task:
            return []
        # Look up transitions for this task type, fallback to '*'
        type_transitions = WORKFLOW_TRANSITIONS.get(task.task_type)
        if not type_transitions:
            type_transitions = WORKFLOW_TRANSITIONS.get("*")
        if not type_transitions:
            return []
        return type_transitions.get(task.status.value, [])

    def transition_task(self, task_id: str, new_status: TaskStatus) -> Task | None:
        """Move a task through the workflow with validation.

        Raises ValueError if the transition is not allowed.
        """
        allowed = self.get_allowed_transitions(task_id)
        if new_status.value not in allowed:
            task = self.repo.get_by_id(task_id)
            current = task.status.value if task else "unknown"
            raise ValueError(
                f"Transition {current} -> {new_status.value} not allowed for this task type"
            )
        # Clear resolution if moving away from Done
        if new_status != TaskStatus.DONE:
            task = self.repo.get_by_id(task_id)
            if task and task.resolution:
                old_res = task.resolution
                task.resolution = None
                task.record_change("resolution", old_res, "")
                task.update_timestamp()
                self.repo.update(task)
        return self.update_task_status(task_id, new_status)

    # ── Time Estimates ──

    def set_original_estimate(self, task_id: str, hours: float) -> Task | None:
        """Set the original time estimate for a task."""
        if hours < 0:
            raise ValueError("Estimate must be non-negative")

        def m(task: Task):
            old_est = task.original_estimate
            task.original_estimate = round(hours, 2)
            task.record_change("original_estimate", str(old_est), str(task.original_estimate))
            log.info(f"Estimate for {task_id}: {old_est}h -> {task.original_estimate}h")

        return self._edit(task_id, m)

    def get_time_remaining(self, task_id: str) -> dict | None:
        """Get time tracking info: original_estimate, time_spent, remaining, over."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        remaining = max(0, task.original_estimate - task.time_spent)
        over = task.time_spent - task.original_estimate if task.time_spent > task.original_estimate else 0
        return {
            "original_estimate": task.original_estimate,
            "time_spent": task.time_spent,
            "remaining": round(remaining, 2),
            "over": round(over, 2),
        }

    # ── Labels ──

    def get_all_labels(self) -> list[str]:
        """Get all unique labels across all tasks, sorted."""
        label_set = set()
        for t in self.get_all_tasks():
            label_set.update(t.labels)
        return sorted(label_set)

    def get_tasks_by_label(self, label: str) -> list[Task]:
        """Find tasks by label (case-insensitive)."""
        lbl = label.strip().lower()
        return [t for t in self.get_all_tasks() if lbl in t.labels]

    def add_label(self, task_id: str, label: str) -> Task | None:
        """Add a label to a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        lbl = label.strip().lower()
        if lbl and lbl not in task.labels:
            if len(task.labels) >= 20:
                raise ValueError("Maximum 20 labels per task")
            task.labels.append(lbl)
            task.record_change("label_added", "", lbl)
            task.update_timestamp()
            updated = self.repo.update(task)
            return updated
        return task

    def remove_label(self, task_id: str, label: str) -> Task | None:
        """Remove a label from a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        lbl = label.strip().lower()
        before = len(task.labels)
        task.labels = [l for l in task.labels if l != lbl]
        if len(task.labels) < before:
            task.record_change("label_removed", lbl, "")
            task.update_timestamp()
            updated = self.repo.update(task)
            return updated
        return task

    # ── task-creating orchestrations (need self.create_task) ──

    def create_task_from_template(self, template_id: str, title_override: str | None = None) -> Task:
        """Create a task from a template. Optionally override the title."""
        tpl = self.repo.get_template_by_id(template_id)
        if not tpl:
            raise ValueError(f"Template {template_id} not found")
        return self.create_task(
            title=title_override or tpl.name,
            description=tpl.description,
            task_type=tpl.task_type,
            priority=_to_priority(tpl.priority),
            tags=list(tpl.tags),
            labels=list(tpl.labels),
            components=list(tpl.components),
            story_points=tpl.story_points,
            original_estimate=tpl.original_estimate,
        )

    def create_tasks_from_project_template(
        self, template_id: str, *, epic_title: str | None = None,
    ) -> list[Task]:
        """Stamp out every step of a :class:`ProjectTemplate` as a real task —
        "break a complex task into staged, dependent steps" in one action.

        ``epic_title``, if given, creates a new Epic first and links every
        step's ``epic_link`` to it (existing hierarchy mechanism — see
        WorkflowService). Steps marked ``sequential`` (the default) are
        wired ``blocked_by`` the immediately preceding step via the existing
        Task.links graph, so WorkflowService/the task dialog treat them
        exactly like a manually-linked dependency; the first step is never
        blocked (nothing precedes it).
        """
        tpl = self.templates.get_project_template(template_id)
        if not tpl:
            raise ValueError(f"Project template {template_id} not found")
        if not tpl.steps:
            return []

        epic = self.create_task(epic_title.strip(), task_type=TaskType.EPIC.value) \
            if epic_title and epic_title.strip() else None

        created: list[Task] = []
        for step in tpl.steps:
            task = self.create_task(step.title, task_type=step.task_type,
                                    epic_link=epic.id if epic else None)
            if step.sequential and created:
                self.add_task_link(task.id, created[-1].id, LinkType.BLOCKED_BY.value)
            created.append(task)
        log.info("Created %d task(s) from project template %s%s", len(created), template_id,
                 f" under epic {epic.id}" if epic else "")
        # add_task_link() mutates its own fresh copy of `task`, not the object
        # held above — re-fetch so callers see the links that were just added.
        return [self.get_task(t.id) for t in created]

    def generate_recurring_tasks(self) -> list[Task]:
        """Create a task for every active recurring definition that has an
        occurrence due since it was last generated. At most one task per
        definition per call (a launch-time catch-up).
        """
        today = datetime.now().strftime("%Y-%m-%d")
        created: list[Task] = []
        for rec in self.repo.get_all_recurring():
            if not rec.is_active:
                continue
            occ = rec.due_occurrence(today, rec.last_generated_date)
            if occ is None:
                continue
            task = self.create_task(
                title=rec.title, description=rec.description,
                task_type=rec.task_type,
                priority=_to_priority(rec.priority),
                tags=list(rec.tags), labels=list(rec.labels),
                original_estimate=rec.estimate_hours, due_date=occ,
            )
            task.recurring_task_id = rec.id
            task.update_timestamp()
            self.repo.update(task)
            rec.last_generated_date = occ
            self.repo.update_recurring(rec)
            created.append(task)
            log.info("Generated recurring task %s from %s (due %s)", task.id, rec.id, occ)
        return created
