"""Sprint lifecycle + reporting. Composed into :class:`TaskService`."""
import logging

from ._util import apply_kwargs
from .models import Sprint, SprintStatus, Task, TaskStatus
from .repository import TaskRepository

log = logging.getLogger(__name__)


class SprintService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def create_sprint(self, name: str, goal: str = "",
                      start_date: str | None = None,
                      end_date: str | None = None) -> Sprint:
        sprint = Sprint(name=name.strip(), goal=goal.strip(),
                        start_date=start_date, end_date=end_date)
        self.repo.add_sprint(sprint)
        log.info("Sprint created: %s - %s", sprint.id, sprint.name)
        return sprint

    def get_all_sprints(self) -> list[Sprint]:
        return self.repo.get_all_sprints()

    def get_sprint(self, sprint_id: str) -> Sprint | None:
        return self.repo.get_sprint_by_id(sprint_id)

    def update_sprint(self, sprint_id: str, **kwargs) -> Sprint | None:
        sprint = self.repo.get_sprint_by_id(sprint_id)
        if not sprint:
            return None
        log.info("Sprint updated: %s", sprint_id)
        return self.repo.update_sprint(apply_kwargs(sprint, kwargs))

    def start_sprint(self, sprint_id: str) -> Sprint | None:
        return self.update_sprint(sprint_id, status=SprintStatus.ACTIVE.value)

    def complete_sprint(self, sprint_id: str) -> Sprint | None:
        return self.update_sprint(sprint_id, status=SprintStatus.COMPLETED.value)

    def cancel_sprint(self, sprint_id: str) -> Sprint | None:
        return self.update_sprint(sprint_id, status=SprintStatus.CANCELLED.value)

    def delete_sprint(self, sprint_id: str) -> bool:
        result = self.repo.delete_sprint(sprint_id)
        if result:
            log.info("Sprint deleted: %s", sprint_id)
        return result

    def get_sprint_tasks(self, sprint_id: str) -> list[Task]:
        return [t for t in self.repo.get_all() if t.sprint_id == sprint_id]

    def assign_task_to_sprint(self, task_id: str, sprint_id: str | None) -> Task | None:
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        if sprint_id and not self.repo.get_sprint_by_id(sprint_id):
            raise ValueError(f"Sprint {sprint_id} not found")
        task.record_change("sprint_id", task.sprint_id or "", sprint_id or "")
        task.sprint_id = sprint_id
        task.update_timestamp()
        log.info("Task %s assigned to sprint %s", task_id, sprint_id)
        return self.repo.update(task)

    def get_sprint_report(self, sprint_id: str) -> dict:
        sprint = self.repo.get_sprint_by_id(sprint_id)
        if not sprint:
            return {}
        tasks = self.get_sprint_tasks(sprint_id)
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return {
            "sprint_id": sprint_id,
            "sprint_name": sprint.name,
            "status": sprint.status,
            "days_remaining": sprint.days_remaining(),
            "total_tasks": total,
            "done_tasks": done,
            "in_progress_tasks": sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS),
            "todo_tasks": sum(1 for t in tasks if t.status == TaskStatus.TODO),
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
            "total_story_points": sum(t.story_points or 0 for t in tasks),
            "completed_story_points": sum(t.story_points or 0 for t in tasks
                                          if t.status == TaskStatus.DONE),
            "total_time_spent": round(sum(t.time_spent for t in tasks), 2),
        }
