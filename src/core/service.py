"""Task Manager - Business Logic Service Layer

Full Jira-like service: CRUD, tags, subtasks, comments, task links,
audit history, bulk operations, search, clone, assignee management.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Optional, List

from .models import (
    Task, TaskStatus, Priority, TaskModel, SubTask,
    LinkType, TaskType, Urgency,
    Resolution, Sprint, SprintStatus,
    VersionRelease, WORKFLOW_TRANSITIONS,
    TaskTemplate, Category, Notification, RecurringTask, RecurrenceFrequency,
)
from .repository import TaskRepository

log = logging.getLogger(__name__)


class TaskService:
    """Business logic service for task management."""

    def __init__(self, repository: Optional[TaskRepository] = None):
        self.repo = repository or TaskRepository()
        from .service_sprints import SprintService
        from .service_versions import VersionService
        self.sprints = SprintService(self.repo)
        self.versions = VersionService(self.repo)
        self._collaborators = (self.sprints, self.versions)

    def __getattr__(self, name: str):
        # Delegate sprint/version/… calls to the composed services without a
        # wall of one-line forwarders. Only fires for names not on TaskService.
        for collab in self.__dict__.get("_collaborators", ()):
            member = getattr(collab, name, None)
            if member is not None:
                return member
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")

    def _edit(self, task_id: str, mutate: Callable[[Task], object]) -> Optional[Task]:
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
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        tags: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        task_type: str = TaskType.TASK.value,
        time_spent: float = 0.0,
        urgency: str = Urgency.NORMAL.value,
        watchers: Optional[List[str]] = None,
        epic_link: Optional[str] = None,
        components: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        version_id: Optional[str] = None,
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
            raise ValueError(f"Validation failed: {e}")

        created = self.repo.add(task)
        log.info(f"Task created: id={created.id}")
        return created

    def get_all_tasks(self) -> List[Task]:
        return self.repo.get_all()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.repo.get_by_id(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
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
        return updated

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date: Optional[str] = None,
        time_spent: Optional[float] = None,
        start_date: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        tags: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        task_type: Optional[str] = None,
        urgency: Optional[str] = None,
        watchers: Optional[List[str]] = None,
    ) -> Optional[Task]:
        task = self.repo.get_by_id(task_id)
        if not task:
            log.warning(f"update_task: task {task_id} not found")
            return None

        old_status = task.status

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
            raise ValueError(f"Validation failed: {e}")

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

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        return self.repo.get_by_status(status)

    def get_statistics(self) -> dict:
        return self.repo.get_statistics()

    def get_overdue_tasks(self) -> List[Task]:
        return [t for t in self.get_all_tasks() if t.is_overdue()]

    # ── Tags ──

    def get_tasks_by_tag(self, tag: str) -> List[Task]:
        """Find tasks by tag (case-insensitive)."""
        tag_lower = tag.strip().lower()
        return [t for t in self.get_all_tasks() if tag_lower in t.tags]

    def get_all_tags(self) -> List[str]:
        """Get all unique tags across all tasks, sorted alphabetically."""
        tag_set = set()
        for t in self.get_all_tasks():
            tag_set.update(t.tags)
        return sorted(tag_set)

    # ── Subtasks ──

    def add_subtask(self, task_id: str, title: str) -> Optional[Task]:
        """Add a subtask to a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        title = title.strip()

        def m(task: Task):
            task.subtasks.append(SubTask(title=title))
            task.record_change("subtask_added", "", title)

        return self._edit(task_id, m)

    def toggle_subtask(self, task_id: str, index: int) -> Optional[Task]:
        """Toggle subtask completion."""
        def m(task: Task):
            if not task.toggle_subtask(index):
                return False
            sub = task.subtasks[index]
            task.record_change("subtask_toggled", sub.title, "done" if sub.done else "undone")

        return self._edit(task_id, m)

    def delete_subtask(self, task_id: str, index: int) -> Optional[Task]:
        """Delete a subtask by index."""
        def m(task: Task):
            if not (0 <= index < len(task.subtasks)):
                return False
            task.record_change("subtask_deleted", task.subtasks.pop(index).title, "")

        return self._edit(task_id, m)

    # ── Comments ──

    def add_comment(self, task_id: str, author: str, text: str) -> Optional[Task]:
        """Add a comment to a task."""
        author, text = author.strip(), text.strip()

        def m(task: Task):
            task.add_comment(author, text)
            task.record_change("comment_added", "", f"by {author}: {text[:50]}")

        return self._edit(task_id, m)

    def delete_comment(self, task_id: str, comment_id: str) -> Optional[Task]:
        """Delete a comment from a task."""
        def m(task: Task):
            if not task.delete_comment(comment_id):
                return False
            task.record_change("comment_deleted", comment_id, "")

        return self._edit(task_id, m)

    # ── Task Links ──

    def add_task_link(self, task_id: str, target_task_id: str, link_type: str = "relates_to") -> Optional[Task]:
        """Link two tasks."""
        if task_id == target_task_id:
            raise ValueError("Cannot link a task to itself")
        # Validate target exists
        if not self.repo.get_by_id(target_task_id):
            raise ValueError(f"Target task {target_task_id} not found")
        # Validate link type
        valid_types = {lt.value for lt in LinkType}
        if link_type not in valid_types:
            raise ValueError(f"Invalid link_type. Must be one of: {valid_types}")

        task = self.repo.get_by_id(task_id)
        if not task:
            return None

        # Check for duplicate link
        for existing in task.links:
            if existing.target_task_id == target_task_id and existing.link_type == link_type:
                return task  # Already linked

        link = task.add_link(target_task_id, link_type)
        # Auto-add reverse link for symmetric types
        if link_type == LinkType.RELATES_TO.value or link_type == LinkType.DUPLICATES.value or link_type == LinkType.CLONES.value:
            target = self.repo.get_by_id(target_task_id)
            if target:
                reverse = link_type  # symmetric
                target.add_link(task_id, reverse)
                target.update_timestamp()
                self.repo.update(target)

        task.record_change("link_added", "", f"{link_type} -> {target_task_id}")
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Link added: {task_id} {link_type} -> {target_task_id}")
        return updated

    def remove_task_link(self, task_id: str, target_task_id: str) -> Optional[Task]:
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

    def bulk_delete(self, task_ids: List[str]) -> int:
        """Delete multiple tasks. Returns count of deleted tasks."""
        count = 0
        for tid in task_ids:
            if self.delete_task(tid):
                count += 1
        log.info(f"Bulk delete: {count}/{len(task_ids)} tasks")
        return count

    def bulk_status_change(self, task_ids: List[str], status: TaskStatus) -> int:
        """Change status of multiple tasks. Returns count of updated tasks."""
        count = 0
        for tid in task_ids:
            if self.update_task_status(tid, status):
                count += 1
        log.info(f"Bulk status change to {status.value}: {count}/{len(task_ids)} tasks")
        return count

    # ── Search ──

    def search_tasks(self, query: str) -> List[Task]:
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

    def get_tasks_by_assignee(self, assignee: str) -> List[Task]:
        """Get all tasks assigned to a person."""
        name = assignee.strip().lower()
        return [t for t in self.get_all_tasks()
                if t.assignee and t.assignee.lower() == name]

    def get_all_assignees(self) -> List[str]:
        """Get all unique assignees."""
        names = {t.assignee for t in self.get_all_tasks() if t.assignee}
        return sorted(names)

    # ── Filters (Jira-style) ──

    def filter_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[Priority] = None,
        assignee: Optional[str] = None,
        tag: Optional[str] = None,
        task_type: Optional[str] = None,
        urgency: Optional[str] = None,
        is_overdue: Optional[bool] = None,
        query: Optional[str] = None,
    ) -> List[Task]:
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

    def move_task(self, task_id: str, direction: str = "forward") -> Optional[Task]:
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

    def add_watcher(self, task_id: str, watcher: str) -> Optional[Task]:
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

    def remove_watcher(self, task_id: str, watcher: str) -> Optional[Task]:
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

    def get_all_watchers(self) -> List[str]:
        """Get all unique watchers across all tasks."""
        names = set()
        for t in self.get_all_tasks():
            names.update(t.watchers)
        return sorted(names)

    # ── Epic Link ──

    def set_epic_link(self, task_id: str, epic_task_id: Optional[str]) -> Optional[Task]:
        """Set or clear the epic link for a task."""
        def m(task: Task):
            if epic_task_id and epic_task_id != task.epic_link:
                epic = self.repo.get_by_id(epic_task_id)
                if not epic:
                    raise ValueError(f"Epic task {epic_task_id} not found")
                if epic.task_type != TaskType.EPIC.value:
                    raise ValueError(f"Task {epic_task_id} is not an Epic")
            task.record_change("epic_link", task.epic_link or "", epic_task_id or "")
            task.epic_link = epic_task_id

        return self._edit(task_id, m)

    def get_epic_children(self, epic_id: str) -> List[Task]:
        """Get all tasks linked to an epic."""
        return [t for t in self.get_all_tasks() if t.epic_link == epic_id]

    # ── Time Tracking ──

    def log_time(self, task_id: str, hours: float) -> Optional[Task]:
        """Add time spent to a task."""
        if hours <= 0:
            raise ValueError("Hours must be positive")

        def m(task: Task):
            old = task.time_spent
            task.time_spent = round(old + hours, 2)
            task.record_change("time_spent", str(old), str(task.time_spent))

        return self._edit(task_id, m)

    # ── Team Workload ──

    def get_team_workload(self) -> List[dict]:
        """Get workload summary per assignee.

        Returns list of dicts: {assignee, total, by_status, total_time, story_points_sum}
        """
        workload = defaultdict(lambda: {
            "total": 0, "todo": 0, "in_progress": 0, "done": 0,
            "total_time": 0.0, "story_points_sum": 0,
        })
        for t in self.get_all_tasks():
            name = t.assignee or "Unassigned"
            w = workload[name]
            w["total"] += 1
            if t.status == TaskStatus.TODO:
                w["todo"] += 1
            elif t.status == TaskStatus.IN_PROGRESS:
                w["in_progress"] += 1
            elif t.status == TaskStatus.DONE:
                w["done"] += 1
            w["total_time"] += t.time_spent
            if t.story_points:
                w["story_points_sum"] += t.story_points

        result = []
        for name, w in sorted(workload.items()):
            result.append({"assignee": name, **w})
        return result

    # ── Clone ──

    def clone_task(self, task_id: str, new_title: Optional[str] = None) -> Optional[Task]:
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

    def get_task_history(self, task_id: str) -> List[dict]:
        """Get change history for a task."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return []
        return [h.to_dict() for h in task.history]

    # ── Components ──

    def get_all_components(self) -> List[str]:
        """Get all unique components across all tasks."""
        comps = set()
        for t in self.get_all_tasks():
            comps.update(t.components)
        return sorted(comps)

    def get_tasks_by_component(self, component: str) -> List[Task]:
        """Get all tasks with a specific component."""
        c = component.strip().lower()
        return [t for t in self.get_all_tasks() if c in [x.lower() for x in t.components]]

    # ── Task Ranking ──

    def set_task_rank(self, task_id: str, rank: int) -> Optional[Task]:
        """Set manual rank for a task (lower = higher priority in backlog)."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        old_rank = task.rank
        task.rank = max(0, rank)
        task.record_change("rank", str(old_rank), str(task.rank))
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Task {task_id} rank: {old_rank} -> {task.rank}")
        return updated

    def get_backlog(self) -> List[Task]:
        """Get all Todo tasks sorted by rank (backlog view)."""
        return sorted(
            [t for t in self.get_all_tasks() if t.status == TaskStatus.TODO],
            key=lambda t: t.rank,
        )

    def reorder_backlog(self, task_ids: List[str]) -> bool:
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

    # ── Swimlanes ──

    def get_swimlanes(self, group_by: str = "assignee") -> dict:
        """Group tasks into swimlanes.

        Args:
            group_by: 'assignee', 'priority', 'task_type', or 'urgency'.

        Returns:
            Dict mapping lane_key -> {"todo": [...], "in_progress": [...], "done": [...]}
        """
        lanes: dict = {}
        for t in self.get_all_tasks():
            if group_by == "assignee":
                key = t.assignee or "Unassigned"
            elif group_by == "priority":
                key = t.priority.value
            elif group_by == "task_type":
                key = t.task_type
            elif group_by == "urgency":
                key = t.urgency
            else:
                key = t.assignee or "Unassigned"

            if key not in lanes:
                lanes[key] = {"todo": [], "in_progress": [], "done": []}

            if t.status == TaskStatus.TODO:
                lanes[key]["todo"].append(t)
            elif t.status == TaskStatus.IN_PROGRESS:
                lanes[key]["in_progress"].append(t)
            elif t.status == TaskStatus.DONE:
                lanes[key]["done"].append(t)

        return lanes

    # ── Sprint Velocity ──

    def get_sprint_velocity(self, last_n: int = 5) -> List[dict]:
        """Calculate velocity from completed sprints.

        Returns list of dicts sorted by completion, each with:
        - sprint_id, sprint_name
        - completed_points, completed_tasks
        - total_time_spent
        """
        completed = [s for s in self.repo.get_all_sprints()
                      if s.status == SprintStatus.COMPLETED.value]
        # Sort by created_at descending, take last N
        completed.sort(key=lambda s: s.created_at, reverse=True)
        completed = completed[:last_n]

        velocities = []
        for sprint in completed:
            tasks = self.get_sprint_tasks(sprint.id)
            done_tasks = [t for t in tasks if t.status == TaskStatus.DONE]
            velocities.append({
                "sprint_id": sprint.id,
                "sprint_name": sprint.name,
                "completed_points": sum(t.story_points or 0 for t in done_tasks),
                "completed_tasks": len(done_tasks),
                "total_time_spent": round(sum(t.time_spent for t in tasks), 2),
            })
        return velocities

    def get_average_velocity(self, last_n: int = 5) -> float:
        """Get average story points completed per sprint."""
        velocities = self.get_sprint_velocity(last_n)
        if not velocities:
            return 0.0
        points = [v["completed_points"] for v in velocities]
        return round(sum(points) / len(points), 1)

    # ── Activity Feed ──

    def get_activity_feed(self, limit: int = 50) -> List[dict]:
        """Get global activity feed from all task histories.

        Returns list of dicts sorted by timestamp descending.
        """
        feed = []
        for t in self.get_all_tasks():
            for h in t.history:
                feed.append({
                    "id": "",
                    "timestamp": h.timestamp,
                    "action": h.field_name,
                    "task_id": t.id,
                    "task_title": t.title,
                    "author": "",
                    "details": f"{h.old_value} -> {h.new_value}",
                })
            for c in t.comments:
                feed.append({
                    "id": c.id,
                    "timestamp": c.created_at,
                    "action": "comment_added",
                    "task_id": t.id,
                    "task_title": t.title,
                    "author": c.author,
                    "details": c.text[:100],
                })
        feed.sort(key=lambda x: x["timestamp"], reverse=True)
        return feed[:limit]

    # ── Resolution ──

    def set_resolution(self, task_id: str, resolution: str) -> Optional[Task]:
        """Set resolution for a task (Jira-style)."""
        valid = {r.value for r in Resolution}
        if resolution not in valid:
            raise ValueError(f"Invalid resolution. Must be one of: {valid}")
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        old_res = task.resolution or ""
        task.resolution = resolution
        task.record_change("resolution", old_res, resolution)
        # Auto-set status to Done if resolution is set
        old_status = task.status.value
        if task.status != TaskStatus.DONE:
            task.status = TaskStatus.DONE
            task.record_change("status", old_status, TaskStatus.DONE.value)
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Resolution for {task_id}: {resolution}")
        return updated

    def clear_resolution(self, task_id: str) -> Optional[Task]:
        """Clear resolution and move task back to In Progress."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        old_res = task.resolution or ""
        task.resolution = None
        task.record_change("resolution", old_res, "")
        if task.status == TaskStatus.DONE:
            task.status = TaskStatus.IN_PROGRESS
            task.record_change("status", TaskStatus.DONE.value, TaskStatus.IN_PROGRESS.value)
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Resolution cleared for {task_id}")
        return updated

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
        with open(file_path, 'r', encoding='utf-8') as f:
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

    def get_allowed_transitions(self, task_id: str) -> List[str]:
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

    def transition_task(self, task_id: str, new_status: TaskStatus) -> Optional[Task]:
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

    def set_original_estimate(self, task_id: str, hours: float) -> Optional[Task]:
        """Set the original time estimate for a task."""
        if hours < 0:
            raise ValueError("Estimate must be non-negative")
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        old_est = task.original_estimate
        task.original_estimate = round(hours, 2)
        task.record_change("original_estimate", str(old_est), str(task.original_estimate))
        task.update_timestamp()
        updated = self.repo.update(task)
        log.info(f"Estimate for {task_id}: {old_est}h -> {task.original_estimate}h")
        return updated

    def get_time_remaining(self, task_id: str) -> Optional[dict]:
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

    def get_all_labels(self) -> List[str]:
        """Get all unique labels across all tasks, sorted."""
        label_set = set()
        for t in self.get_all_tasks():
            label_set.update(t.labels)
        return sorted(label_set)

    def get_tasks_by_label(self, label: str) -> List[Task]:
        """Find tasks by label (case-insensitive)."""
        lbl = label.strip().lower()
        return [t for t in self.get_all_tasks() if lbl in t.labels]

    def add_label(self, task_id: str, label: str) -> Optional[Task]:
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

    def remove_label(self, task_id: str, label: str) -> Optional[Task]:
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

    # ── Board Data (Kanban columns for GUI) ──

    def get_board_data(self, sprint_id: Optional[str] = None) -> dict:
        """Get board data organized by columns.

        Returns dict: {"columns": [{"id": "todo", "title": "Todo", "tasks": [...]}, ...]}
        Optionally filter by sprint_id.
        """
        tasks = self.get_all_tasks()
        if sprint_id:
            tasks = [t for t in tasks if t.sprint_id == sprint_id]

        columns = [
            {"id": "todo", "title": "Todo", "status": TaskStatus.TODO},
            {"id": "in_progress", "title": "In Progress", "status": TaskStatus.IN_PROGRESS},
            {"id": "done", "title": "Done", "status": TaskStatus.DONE},
        ]

        result = {"columns": []}
        for col in columns:
            col_tasks = [t for t in tasks if t.status == col["status"]]
            result["columns"].append({
                "id": col["id"],
                "title": col["title"],
                "tasks": [t.to_dict() for t in col_tasks],
                "count": len(col_tasks),
            })
        return result

    # ── Personal Dashboard ──

    def get_personal_dashboard(self) -> dict:
        """Get personal dashboard data for a single-user app.

        Returns comprehensive stats: task counts, time tracking,
        recent activity, overdue, priority breakdown, etc.
        """
        all_tasks = self.get_all_tasks()
        total = len(all_tasks)
        todo = sum(1 for t in all_tasks if t.status == TaskStatus.TODO)
        in_progress = sum(1 for t in all_tasks if t.status == TaskStatus.IN_PROGRESS)
        done = sum(1 for t in all_tasks if t.status == TaskStatus.DONE)
        overdue = sum(1 for t in all_tasks if t.is_overdue())

        # Time tracking
        total_time_spent = sum(t.time_spent for t in all_tasks)
        total_original_estimate = sum(t.original_estimate for t in all_tasks)
        total_remaining = sum(
            max(0, t.original_estimate - t.time_spent) for t in all_tasks
        )

        # Priority breakdown
        priority_breakdown = {}
        for p in Priority:
            count = sum(1 for t in all_tasks if t.priority == p)
            if count > 0:
                priority_breakdown[p.value] = count

        # Recent tasks (by updated_at)
        recent = sorted(all_tasks, key=lambda t: t.updated_at or "", reverse=True)[:10]

        # Overdue tasks
        overdue_tasks = [t for t in all_tasks if t.is_overdue()]

        # Completion trend (last 7 days based on updated_at)
        now = datetime.now()
        last_7 = [0] * 7
        for t in all_tasks:
            if t.status == TaskStatus.DONE and t.updated_at:
                try:
                    updated = datetime.fromisoformat(t.updated_at)
                    days_ago = (now - updated).days
                    if 0 <= days_ago < 7:
                        last_7[days_ago] += 1
                except (ValueError, TypeError):
                    pass

        # Story points stats
        total_points = sum(t.story_points or 0 for t in all_tasks)
        done_points = sum(t.story_points or 0 for t in all_tasks if t.status == TaskStatus.DONE)

        # Active sprint info
        active_sprints = [s for s in self.repo.get_all_sprints() if s.is_active()]
        active_sprint_data = None
        if active_sprints:
            sp = active_sprints[0]
            active_sprint_data = self.get_sprint_report(sp.id)

        return {
            "total_tasks": total,
            "todo": todo,
            "in_progress": in_progress,
            "done": done,
            "overdue": overdue,
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
            "total_time_spent": round(total_time_spent, 2),
            "total_original_estimate": round(total_original_estimate, 2),
            "total_remaining_estimate": round(total_remaining, 2),
            "priority_breakdown": priority_breakdown,
            "recent_tasks": [t.to_dict() for t in recent],
            "overdue_tasks": [t.to_dict() for t in overdue_tasks],
            "completion_last_7_days": last_7,
            "total_story_points": total_points,
            "completed_story_points": done_points,
            "active_sprint": active_sprint_data,
            "labels_count": len(self.get_all_labels()),
            "versions_count": len(self.repo.get_all_versions()),
            "categories_count": len(self.repo.get_all_categories()),
        }

    # ── Task Templates ──

    def create_template(self, name: str, description: str = "",
                         task_type: str = TaskType.TASK.value,
                         priority: str = Priority.MEDIUM.value,
                         tags: Optional[List[str]] = None,
                         labels: Optional[List[str]] = None,
                         components: Optional[List[str]] = None,
                         story_points: Optional[int] = None,
                         original_estimate: float = 0.0) -> TaskTemplate:
        """Create a reusable task template."""
        tpl = TaskTemplate(
            name=name.strip(), description=description.strip(),
            task_type=task_type, priority=priority,
            tags=tags or [], labels=labels or [], components=components or [],
            story_points=story_points, original_estimate=original_estimate,
        )
        self.repo.add_template(tpl)
        log.info(f"Template created: {tpl.id} - {name.strip()}")
        return tpl

    def get_all_templates(self) -> List[TaskTemplate]:
        return self.repo.get_all_templates()

    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        return self.repo.get_template_by_id(template_id)

    def update_template(self, template_id: str, **kwargs) -> Optional[TaskTemplate]:
        tpl = self.repo.get_template_by_id(template_id)
        if not tpl:
            return None
        for key, val in kwargs.items():
            if hasattr(tpl, key) and val is not None:
                setattr(tpl, key, val)
        updated = self.repo.update_template(tpl)
        log.info(f"Template updated: {template_id}")
        return updated

    def delete_template(self, template_id: str) -> bool:
        result = self.repo.delete_template(template_id)
        if result:
            log.info(f"Template deleted: {template_id}")
        return result

    def create_task_from_template(self, template_id: str, title_override: Optional[str] = None) -> Task:
        """Create a task from a template. Optionally override the title."""
        tpl = self.repo.get_template_by_id(template_id)
        if not tpl:
            raise ValueError(f"Template {template_id} not found")
        return self.create_task(
            title=title_override or tpl.name,
            description=tpl.description,
            task_type=tpl.task_type,
            priority=Priority(tpl.priority) if tpl.priority in {p.value for p in Priority} else Priority.MEDIUM,
            tags=list(tpl.tags),
            labels=list(tpl.labels),
            components=list(tpl.components),
            story_points=tpl.story_points,
            original_estimate=tpl.original_estimate,
        )

    # ── Categories ──

    def create_category(self, name: str, description: str = "", color: str = "#0a84ff") -> Category:
        """Create a project/category."""
        cat = Category(name=name.strip(), description=description.strip(), color=color)
        self.repo.add_category(cat)
        log.info(f"Category created: {cat.id} - {name.strip()}")
        return cat

    def get_all_categories(self) -> List[Category]:
        return self.repo.get_all_categories()

    def get_category(self, category_id: str) -> Optional[Category]:
        return self.repo.get_category_by_id(category_id)

    def update_category(self, category_id: str, **kwargs) -> Optional[Category]:
        cat = self.repo.get_category_by_id(category_id)
        if not cat:
            return None
        for key, val in kwargs.items():
            if hasattr(cat, key) and val is not None:
                setattr(cat, key, val)
        updated = self.repo.update_category(cat)
        log.info(f"Category updated: {category_id}")
        return updated

    def delete_category(self, category_id: str) -> bool:
        result = self.repo.delete_category(category_id)
        if result:
            for t in self.get_all_tasks():
                if t.category_id == category_id:
                    t.category_id = None
                    t.update_timestamp()
                    self.repo.update(t)
            log.info(f"Category deleted: {category_id}")
        return result

    def get_category_tasks(self, category_id: str) -> List[Task]:
        return [t for t in self.get_all_tasks() if t.category_id == category_id]

    def assign_task_to_category(self, task_id: str, category_id: Optional[str]) -> Optional[Task]:
        """Assign or unassign a task from a category."""
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        if category_id and not self.repo.get_category_by_id(category_id):
            raise ValueError(f"Category {category_id} not found")
        old_cat = task.category_id or ""
        task.category_id = category_id
        task.record_change("category_id", old_cat, category_id or "")
        task.update_timestamp()
        updated = self.repo.update(task)
        return updated

    def get_category_report(self, category_id: str) -> dict:
        cat = self.repo.get_category_by_id(category_id)
        if not cat:
            return {}
        tasks = self.get_category_tasks(category_id)
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return {
            "category_id": category_id,
            "category_name": cat.name,
            "color": cat.color,
            "total_tasks": total,
            "done_tasks": done,
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
        }

    # ── Recurring Tasks ──

    def create_recurring_task(self, title: str, frequency: str = RecurrenceFrequency.WEEKLY.value,
                                base_due_date: Optional[str] = None, description: str = "",
                                task_type: str = TaskType.TASK.value,
                                priority: str = Priority.MEDIUM.value,
                                tags: Optional[List[str]] = None,
                                labels: Optional[List[str]] = None,
                                estimate_hours: float = 0.0) -> RecurringTask:
        valid_freq = {f.value for f in RecurrenceFrequency}
        if frequency not in valid_freq:
            raise ValueError(f"Invalid frequency. Must be one of: {valid_freq}")
        rec = RecurringTask(
            title=title.strip(), description=description.strip(),
            frequency=frequency, base_due_date=base_due_date,
            task_type=task_type, priority=priority,
            tags=tags or [], labels=labels or [],
            estimate_hours=estimate_hours,
        )
        self.repo.add_recurring(rec)
        log.info(f"Recurring task created: {rec.id} - {title.strip()}")
        return rec

    def get_all_recurring(self) -> List[RecurringTask]:
        return self.repo.get_all_recurring()

    def get_recurring(self, rec_id: str) -> Optional[RecurringTask]:
        return self.repo.get_recurring_by_id(rec_id)

    def update_recurring(self, rec_id: str, **kwargs) -> Optional[RecurringTask]:
        rec = self.repo.get_recurring_by_id(rec_id)
        if not rec:
            return None
        for key, val in kwargs.items():
            if hasattr(rec, key) and val is not None:
                setattr(rec, key, val)
        updated = self.repo.update_recurring(rec)
        log.info(f"Recurring task updated: {rec_id}")
        return updated

    def delete_recurring(self, rec_id: str) -> bool:
        result = self.repo.delete_recurring(rec_id)
        if result:
            log.info(f"Recurring task deleted: {rec_id}")
        return result

    def toggle_recurring_active(self, rec_id: str) -> Optional[RecurringTask]:
        rec = self.repo.get_recurring_by_id(rec_id)
        if not rec:
            return None
        rec.is_active = not rec.is_active
        updated = self.repo.update_recurring(rec)
        log.info(f"Recurring task {rec_id} active={rec.is_active}")
        return updated

    def generate_recurring_tasks(self) -> List[Task]:
        """Generate tasks from all active recurring definitions that are due.

        A recurring task is due if next_due_date(today) <= today.
        After generating, updates last_generated_date.
        Returns list of newly created tasks.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        created_tasks = []
        for rec in self.repo.get_all_recurring():
            if not rec.is_active or not rec.base_due_date:
                continue
            next_due = rec.next_due_date(today)
            if next_due and next_due <= today:
                # Skip if already generated on this due date
                if rec.last_generated_date and rec.last_generated_date >= next_due:
                    continue
                task = self.create_task(
                    title=rec.title,
                    description=rec.description,
                    task_type=rec.task_type,
                    priority=Priority(rec.priority) if rec.priority in {p.value for p in Priority} else Priority.MEDIUM,
                    tags=list(rec.tags),
                    labels=list(rec.labels),
                    original_estimate=rec.estimate_hours,
                    due_date=next_due,
                )
                task.recurring_task_id = rec.id
                task.update_timestamp()
                self.repo.update(task)
                # Update last_generated_date
                rec.last_generated_date = today
                self.repo.update_recurring(rec)
                created_tasks.append(task)
                log.info(f"Generated recurring task: {task.id} from {rec.id}")
        return created_tasks

    # ── Notifications ──

    def get_notifications(self, unread_only: bool = False) -> List[Notification]:
        if unread_only:
            return self.repo.get_unread_notifications()
        return self.repo.get_all_notifications()

    def add_notification(self, ntype: str, title: str, message: str,
                         task_id: Optional[str] = None) -> Notification:
        notif = Notification(ntype=ntype, title=title.strip(), message=message.strip(), task_id=task_id)
        self.repo.add_notification(notif)
        return notif

    def mark_notification_read(self, notif_id: str) -> bool:
        return self.repo.mark_notification_read(notif_id)

    def mark_all_notifications_read(self) -> int:
        return self.repo.mark_all_notifications_read()

    def delete_notification(self, notif_id: str) -> bool:
        return self.repo.delete_notification(notif_id)

    def generate_overdue_notifications(self) -> List[Notification]:
        """Create notifications for overdue and due-soon tasks."""
        created = []
        for t in self.get_all_tasks():
            if t.status == TaskStatus.DONE:
                continue
            if t.is_overdue():
                n = self.add_notification(
                    'warning', 'Просрочено',
                    f'{t.title} просрочена ({t.due_date})',
                    task_id=t.id,
                )
                created.append(n)
            elif t.days_until_due() is not None and 0 <= t.days_until_due() <= 2:
                n = self.add_notification(
                    'info', 'Скоро дедлайн',
                    f'{t.title} — через {t.days_until_due()} дн.',
                    task_id=t.id,
                )
                created.append(n)
        # Trim old notifications
        self.repo.clear_old_notifications(100)
        return created
