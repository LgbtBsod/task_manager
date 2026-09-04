"""Derived "blocked" state + opt-in auto-advance over the existing task-link
and epic-link graphs — no new relationship model.

Dependencies already had a home: ``Task.links`` + ``LinkType.BLOCKED_BY`` (set
via ``TaskService.add_task_link`` — built, but until now never read by
anything). Likewise a "big task broken into steps" already has a home:
``Task.epic_link`` + ``TaskType.EPIC`` (Jira-style — an Epic's children point
back at it). This module is what actually *uses* both graphs: computing
"is this task blocked", and — only when the caller opts in — starting a
newly-unblocked dependent or closing a finished Epic.

Composed into :class:`TaskService` and reached through the collaborator
facade (``service.is_blocked(task)``, ``service.blocking_tasks(task)``).
"""
import logging

from .models import LinkType, Task, TaskStatus
from .repository import TaskRepository

log = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    # ── derived state (read-only) ──

    def blocking_tasks(self, task: Task) -> list[Task]:
        """Unfinished tasks ``task`` declares itself blocked by."""
        out = []
        for link in task.links:
            if link.link_type != LinkType.BLOCKED_BY.value:
                continue
            blocker = self.repo.get_by_id(link.target_task_id)
            if blocker and blocker.status != TaskStatus.DONE:
                out.append(blocker)
        return out

    def is_blocked(self, task: Task) -> bool:
        return bool(self.blocking_tasks(task))

    def dependents_of(self, task_id: str) -> list[Task]:
        """Tasks that declare themselves blocked by ``task_id``."""
        return [t for t in self.repo.get_all()
                if any(link.link_type == LinkType.BLOCKED_BY.value
                       and link.target_task_id == task_id for link in t.links)]

    # ── opt-in advance, called after a task reaches Done ──

    def plan_after_done(self, done_task: Task) -> dict:
        """What *could* happen now that ``done_task`` is Done — a pure read.
        ``TaskService.update_task_status`` applies whichever parts the caller
        asked for via ``auto_start_unblocked`` / ``auto_close_epic``.
        """
        unblocked = [dep for dep in self.dependents_of(done_task.id)
                    if dep.status == TaskStatus.TODO and not self.is_blocked(dep)]

        epic_to_close = None
        if done_task.epic_link:
            siblings = [t for t in self.repo.get_all() if t.epic_link == done_task.epic_link]
            epic = self.repo.get_by_id(done_task.epic_link)
            if (epic and epic.status != TaskStatus.DONE and siblings
                    and all(t.status == TaskStatus.DONE for t in siblings)):
                epic_to_close = done_task.epic_link

        return {"unblocked": unblocked, "epic_to_close": epic_to_close}
