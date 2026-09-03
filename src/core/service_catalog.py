"""Task templates, project categories and recurring-task definitions.

Pure CRUD over the sidecar collections — the orchestrations that *create*
tasks (`create_task_from_template`, `generate_recurring_tasks`) stay on
:class:`TaskService`. Composed in via the collaborator facade.
"""
import logging
from typing import Optional, List

from ._util import apply_kwargs
from .models import (Category, RecurrenceFrequency, RecurringTask, Task,
                     TaskStatus, TaskTemplate, TaskType, Priority)
from .repository import TaskRepository

log = logging.getLogger(__name__)


class TemplateService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def create_template(self, name: str, description: str = "",
                        task_type: str = TaskType.TASK.value,
                        priority: str = Priority.MEDIUM.value,
                        tags: Optional[List[str]] = None,
                        labels: Optional[List[str]] = None,
                        components: Optional[List[str]] = None,
                        story_points: Optional[int] = None,
                        original_estimate: float = 0.0) -> TaskTemplate:
        tpl = TaskTemplate(
            name=name.strip(), description=description.strip(),
            task_type=task_type, priority=priority,
            tags=tags or [], labels=labels or [], components=components or [],
            story_points=story_points, original_estimate=original_estimate,
        )
        self.repo.add_template(tpl)
        log.info("Template created: %s - %s", tpl.id, tpl.name)
        return tpl

    def get_all_templates(self) -> List[TaskTemplate]:
        return self.repo.get_all_templates()

    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        return self.repo.get_template_by_id(template_id)

    def update_template(self, template_id: str, **kwargs) -> Optional[TaskTemplate]:
        tpl = self.repo.get_template_by_id(template_id)
        if not tpl:
            return None
        log.info("Template updated: %s", template_id)
        return self.repo.update_template(apply_kwargs(tpl, kwargs))

    def delete_template(self, template_id: str) -> bool:
        result = self.repo.delete_template(template_id)
        if result:
            log.info("Template deleted: %s", template_id)
        return result


class CategoryService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def create_category(self, name: str, description: str = "",
                        color: str = "#0a84ff") -> Category:
        cat = Category(name=name.strip(), description=description.strip(), color=color)
        self.repo.add_category(cat)
        log.info("Category created: %s - %s", cat.id, cat.name)
        return cat

    def get_all_categories(self) -> List[Category]:
        return self.repo.get_all_categories()

    def get_category(self, category_id: str) -> Optional[Category]:
        return self.repo.get_category_by_id(category_id)

    def update_category(self, category_id: str, **kwargs) -> Optional[Category]:
        cat = self.repo.get_category_by_id(category_id)
        if not cat:
            return None
        log.info("Category updated: %s", category_id)
        return self.repo.update_category(apply_kwargs(cat, kwargs))

    def delete_category(self, category_id: str) -> bool:
        result = self.repo.delete_category(category_id)
        if result:
            for t in self.repo.get_all():
                if t.category_id == category_id:
                    t.category_id = None
                    t.update_timestamp()
                    self.repo.update(t)
            log.info("Category deleted: %s", category_id)
        return result

    def get_category_tasks(self, category_id: str) -> List[Task]:
        return [t for t in self.repo.get_all() if t.category_id == category_id]

    def assign_task_to_category(self, task_id: str, category_id: Optional[str]) -> Optional[Task]:
        task = self.repo.get_by_id(task_id)
        if not task:
            return None
        if category_id and not self.repo.get_category_by_id(category_id):
            raise ValueError(f"Category {category_id} not found")
        task.record_change("category_id", task.category_id or "", category_id or "")
        task.category_id = category_id
        task.update_timestamp()
        return self.repo.update(task)

    def get_category_report(self, category_id: str) -> dict:
        cat = self.repo.get_category_by_id(category_id)
        if not cat:
            return {}
        tasks = self.get_category_tasks(category_id)
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return {
            "category_id": category_id, "category_name": cat.name, "color": cat.color,
            "total_tasks": total, "done_tasks": done,
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
        }


class RecurringService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def create_recurring_task(self, title: str,
                              frequency: str = RecurrenceFrequency.WEEKLY.value,
                              base_due_date: Optional[str] = None, description: str = "",
                              task_type: str = TaskType.TASK.value,
                              priority: str = Priority.MEDIUM.value,
                              tags: Optional[List[str]] = None,
                              labels: Optional[List[str]] = None,
                              estimate_hours: float = 0.0) -> RecurringTask:
        if frequency not in {f.value for f in RecurrenceFrequency}:
            raise ValueError(f"Invalid frequency: {frequency}")
        rec = RecurringTask(
            title=title.strip(), description=description.strip(),
            frequency=frequency, base_due_date=base_due_date,
            task_type=task_type, priority=priority,
            tags=tags or [], labels=labels or [], estimate_hours=estimate_hours,
        )
        self.repo.add_recurring(rec)
        log.info("Recurring task created: %s - %s", rec.id, rec.title)
        return rec

    def get_all_recurring(self) -> List[RecurringTask]:
        return self.repo.get_all_recurring()

    def get_recurring(self, rec_id: str) -> Optional[RecurringTask]:
        return self.repo.get_recurring_by_id(rec_id)

    def update_recurring(self, rec_id: str, **kwargs) -> Optional[RecurringTask]:
        rec = self.repo.get_recurring_by_id(rec_id)
        if not rec:
            return None
        log.info("Recurring task updated: %s", rec_id)
        return self.repo.update_recurring(apply_kwargs(rec, kwargs))

    def delete_recurring(self, rec_id: str) -> bool:
        result = self.repo.delete_recurring(rec_id)
        if result:
            log.info("Recurring task deleted: %s", rec_id)
        return result

    def toggle_recurring_active(self, rec_id: str) -> Optional[RecurringTask]:
        rec = self.repo.get_recurring_by_id(rec_id)
        if not rec:
            return None
        rec.is_active = not rec.is_active
        log.info("Recurring task %s active=%s", rec_id, rec.is_active)
        return self.repo.update_recurring(rec)
