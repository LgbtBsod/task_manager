"""Version / Release lifecycle + reporting. Composed into :class:`TaskService`."""
import logging
from datetime import datetime
from typing import Optional, List

from ._util import apply_kwargs
from .models import VersionRelease, Task, TaskStatus, TaskType
from .repository import TaskRepository

log = logging.getLogger(__name__)


class VersionService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def create_version(self, name: str, description: str = "") -> VersionRelease:
        version = VersionRelease(name=name.strip(), description=description.strip())
        self.repo.add_version(version)
        log.info("Version created: %s - %s", version.id, version.name)
        return version

    def get_all_versions(self) -> List[VersionRelease]:
        return self.repo.get_all_versions()

    def get_version(self, version_id: str) -> Optional[VersionRelease]:
        return self.repo.get_version_by_id(version_id)

    def update_version(self, version_id: str, **kwargs) -> Optional[VersionRelease]:
        version = self.repo.get_version_by_id(version_id)
        if not version:
            return None
        log.info("Version updated: %s", version_id)
        return self.repo.update_version(apply_kwargs(version, kwargs))

    def release_version(self, version_id: str,
                        release_date: Optional[str] = None) -> Optional[VersionRelease]:
        return self.update_version(
            version_id, status="Released",
            release_date=release_date or datetime.now().strftime("%Y-%m-%d"))

    def archive_version(self, version_id: str) -> Optional[VersionRelease]:
        return self.update_version(version_id, status="Archived")

    def delete_version(self, version_id: str) -> bool:
        result = self.repo.delete_version(version_id)
        if result:
            for t in self.repo.get_all():
                if t.version_id == version_id:
                    t.version_id = None
                    t.update_timestamp()
                    self.repo.update(t)
            log.info("Version deleted: %s", version_id)
        return result

    def get_version_tasks(self, version_id: str) -> List[Task]:
        return [t for t in self.repo.get_all() if t.version_id == version_id]

    def assign_task_to_version(self, task_id: str, version_id: Optional[str]) -> Optional[Task]:
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        if version_id and not self.repo.get_version_by_id(version_id):
            raise ValueError(f"Version {version_id} not found")
        task.record_change("version_id", task.version_id or "", version_id or "")
        task.version_id = version_id
        task.update_timestamp()
        log.info("Task %s assigned to version %s", task_id, version_id)
        return self.repo.update(task)

    def get_version_report(self, version_id: str) -> dict:
        version = self.repo.get_version_by_id(version_id)
        if not version:
            return {}
        tasks = self.get_version_tasks(version_id)
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return {
            "version_id": version_id,
            "version_name": version.name,
            "status": version.status,
            "release_date": version.release_date,
            "total_tasks": total,
            "done_tasks": done,
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
            "total_story_points": sum(t.story_points or 0 for t in tasks),
            "completed_story_points": sum(t.story_points or 0 for t in tasks
                                          if t.status == TaskStatus.DONE),
            "bug_count": sum(1 for t in tasks if t.task_type == TaskType.BUG.value),
        }
