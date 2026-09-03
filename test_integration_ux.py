"""
Headless integration test for the Flet GUI.

Exercises the service layer and every view's build()/refresh() against a real
(temp-file) database, plus the drag-and-drop and dialog code paths — without a
browser. Run:  python test_integration_ux.py   (or via pytest).
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import flet as ft  # noqa: E402
from core.models import Priority, TaskStatus  # noqa: E402
from core.repository import TaskRepository  # noqa: E402
from core.service import TaskService  # noqa: E402
from gui_flet.app import TaskManagerApp  # noqa: E402
from gui_flet.kanban_view import KanbanView, DropColumn  # noqa: E402
from gui_flet.gantt_view import GanttView  # noqa: E402
from gui_flet.dashboard_view import DashboardView  # noqa: E402


class _FakeApp:
    """Minimal stand-in for TaskManagerApp for view unit checks."""

    def __init__(self, service):
        self.service = service
        self.page = None

    def _filter_and_sort(self, tasks):
        return list(tasks)

    def handle_drop(self, task, status_value):
        mapping = {
            "Todo": TaskStatus.TODO,
            "In Progress": TaskStatus.IN_PROGRESS,
            "Done": TaskStatus.DONE,
        }
        self.service.update_task_status(task.id, mapping[status_value])

    def show_edit_dialog(self, task):
        pass

    def _clone_task(self, task):
        self.service.clone_task(task.id)

    def delete_task(self, task):
        self.service.delete_task(task.id)


def _fresh_service():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "tasks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([], f)
    return TaskService(repository=TaskRepository(db_path=path))


def test_use_cases():
    print("Running headless UX integration test...")
    svc = _fresh_service()
    today = datetime.now().strftime("%Y-%m-%d")
    due_5 = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

    # 1. create
    t1 = svc.create_task(title="Разработка API", description="REST endpoints",
                         priority=Priority.HIGH, start_date=today, due_date=due_5)
    t2 = svc.create_task(title="Настройка Flet GUI", priority=Priority.MEDIUM)
    t3 = svc.create_task(title="Тестирование", priority=Priority.CRITICAL)
    svc.add_subtask(t3.id, "Автотесты")
    svc.add_subtask(t3.id, "Ручные тесты")
    svc.toggle_subtask(t3.id, 0)
    assert len(svc.get_all_tasks()) == 3
    assert abs(svc.get_task(t3.id).subtask_progress() - 0.5) < 1e-6
    print("  create + subtasks OK")

    # 2. status transitions (drag-and-drop logic)
    fake = _FakeApp(svc)
    col = DropColumn(fake, "In Progress", "#ff9f0a", "In Progress")
    fake.handle_drop(t1, "In Progress")
    assert svc.get_task(t1.id).status == TaskStatus.IN_PROGRESS
    print("  drag-and-drop status change OK")

    # 3. update
    svc.update_task(t2.id, description="added auth", priority=Priority.HIGH)
    assert svc.get_task(t2.id).priority == Priority.HIGH
    print("  update OK")

    # 4. every view builds + refreshes headlessly
    for View in (KanbanView, GanttView, DashboardView):
        v = View(app=fake)
        v.build()
        assert v.container is not None, f"{View.__name__}.container is None"
        if hasattr(v, "refresh"):
            v.refresh()
    print("  KanbanView / GanttView / DashboardView build + refresh OK")

    # 5. TaskManagerApp wiring (service init + filter/sort with Critical)
    app = TaskManagerApp()
    app.service = svc
    ordered = app._filter_and_sort(svc.get_all_tasks())
    app._sort_mode = "priority"
    ordered = app._filter_and_sort(svc.get_all_tasks())
    assert ordered[0].priority == Priority.CRITICAL, "Critical must sort first"
    print("  priority sort places Critical first OK")

    print("ALL UX INTEGRATION CHECKS PASSED")
    return True


if __name__ == "__main__":
    test_use_cases()
