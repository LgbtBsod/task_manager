"""Tests for new features: Versions/Releases, Workflow Transitions, Time Estimates,
Labels, Board Data, Personal Dashboard, Portable EXE path helpers.

Covers:
- VersionRelease model (creation, serialization, is_released)
- Version CRUD (create, get, update, release, archive, delete)
- Version task assignment and reports
- Version deletion clears task.version_id
- Workflow transitions (allowed, blocked, non-existent task)
- Time estimates (set, get remaining, negative rejection)
- Labels (add, remove, get_all, get_by, max 20 limit, dedup, case)
- Board data (columns, counts, sprint filter)
- Personal dashboard (all fields, empty state, with data)
- Task new fields (labels, version_id, original_estimate in serialization)
- Export/Import includes versions
- get_app_dir / get_data_dir / get_db_path
- Integration: full lifecycle version + labels + workflow + estimate
- Edge cases: duplicate version names, version not found, label not found, etc.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.models import (
    WORKFLOW_TRANSITIONS,
    LinkType,
    Priority,
    Resolution,
    Sprint,
    SprintStatus,
    SubTask,
    Task,
    TaskComment,
    TaskStatus,
    TaskType,
    Urgency,
    VersionRelease,
)
from core.repository import TaskRepository
from core.service import TaskService


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f'  PASS  {name}')

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f'  FAIL  {name}: {reason}')

    def summary(self):
        total = self.passed + self.failed
        print(f'\n  Results: {self.passed}/{total} passed, {self.failed} failed')
        if self.errors:
            print('  Failures:')
            for name, reason in self.errors:
                print(f'    - {name}: {reason}')
        return self.failed == 0


TMP_DB = tempfile.mktemp(suffix='.json')


def make_service(db_path=None) -> TaskService:
    p = db_path or TMP_DB
    return TaskService(TaskRepository(p))


def cleanup():
    base = TMP_DB.replace('.json', '')
    for suffix in ['.json', '_sprints.json', '_versions.json']:
        f = base + suffix
        if os.path.exists(f):
            os.unlink(f)


# ═══════════════════════════════════════════════════════════════════════
# VERSION RELEASE MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_version_model_creation(r):
    v = VersionRelease(name="v1.0", description="First release")
    r.ok('version_model_creation') if v.name == "v1.0" and v.status == "Unreleased" and v.id else \
        r.fail('version_model_creation', f'name={v.name}, id={v.id}')


def test_version_model_serialization(r):
    v = VersionRelease(name="v2.0", description="Second")
    d = v.to_dict()
    v2 = VersionRelease.from_dict(d)
    r.ok('version_model_serialization') if v2.name == v.name and v2.id == v.id else \
        r.fail('version_model_serialization', f'{v2.name} != {v.name}')


def test_version_is_released(r):
    v = VersionRelease(name="v1.0", status="Released")
    r.ok('version_is_released') if v.is_released() else \
        r.fail('version_is_released', 'should be True')


def test_version_is_not_released(r):
    v = VersionRelease(name="v1.0", status="Unreleased")
    r.ok('version_is_not_released') if not v.is_released() else \
        r.fail('version_is_not_released', 'should be False')


def test_version_from_dict_defaults(r):
    v = VersionRelease.from_dict({})
    r.ok('version_from_dict_defaults') if v.status == "Unreleased" and v.name == "" else \
        r.fail('version_from_dict_defaults', f'status={v.status}')


# ═══════════════════════════════════════════════════════════════════════
# VERSION CRUD TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_version_crud_full(r):
    svc = make_service()
    v = svc.create_version("v1.0", "First release")
    fetched = svc.get_version(v.id)
    r.ok('version_crud_create') if fetched and fetched.name == "v1.0" else \
        r.fail('version_crud_create', 'not found')

    svc.update_version(v.id, name="v1.1")
    fetched = svc.get_version(v.id)
    r.ok('version_crud_update') if fetched and fetched.name == "v1.1" else \
        r.fail('version_crud_update', f'name={fetched.name if fetched else None}')

    r.ok('version_crud_list') if len(svc.get_all_versions()) == 1 else \
        r.fail('version_crud_list', f'count={len(svc.get_all_versions())}')

    svc.delete_version(v.id)
    r.ok('version_crud_delete') if svc.get_version(v.id) is None else \
        r.fail('version_crud_delete', 'still exists')

    cleanup()


def test_version_lifecycle(r):
    svc = make_service()
    v = svc.create_version("v2.0")
    # Release
    released = svc.release_version(v.id, "2025-01-15")
    r.ok('version_release') if released and released.status == "Released" and released.release_date == "2025-01-15" else \
        r.fail('version_release', f'status={released.status if released else None}')
    # Archive
    archived = svc.archive_version(v.id)
    r.ok('version_archive') if archived and archived.status == "Archived" else \
        r.fail('version_archive', f'status={archived.status if archived else None}')
    # Get non-existent
    r.ok('version_not_found') if svc.get_version("nonexistent") is None else \
        r.fail('version_not_found', 'should be None')
    cleanup()


def test_version_delete_clears_task_version_id(r):
    svc = make_service()
    v = svc.create_version("v1.0")
    t = svc.create_task("Test", version_id=v.id)
    r.ok('version_task_assigned') if t.version_id == v.id else \
        r.fail('version_task_assigned', f'version_id={t.version_id}')
    svc.delete_version(v.id)
    t2 = svc.get_task(t.id)
    r.ok('version_delete_clears') if t2 and t2.version_id is None else \
        r.fail('version_delete_clears', f'version_id={t2.version_id if t2 else None}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# VERSION TASK ASSIGNMENT + REPORT
# ═══════════════════════════════════════════════════════════════════════

def test_version_task_assignment(r):
    svc = make_service()
    v = svc.create_version("v1.0")
    t1 = svc.create_task("T1")
    t2 = svc.create_task("T2")
    svc.assign_task_to_version(t1.id, v.id)
    r.ok('assign_to_version') if svc.get_task(t1.id).version_id == v.id else \
        r.fail('assign_to_version', 'not assigned')
    svc.assign_task_to_version(t1.id, None)
    r.ok('unassign_from_version') if svc.get_task(t1.id).version_id is None else \
        r.fail('unassign_from_version', 'still assigned')
    # Assign with invalid version
    try:
        svc.assign_task_to_version(t2.id, "nonexistent")
        r.fail('assign_invalid_version', 'should raise')
    except ValueError:
        r.ok('assign_invalid_version')
    cleanup()


def test_version_tasks_and_report(r):
    svc = make_service()
    v = svc.create_version("v1.0")
    t1 = svc.create_task("Bug fix", task_type=TaskType.BUG.value, story_points=3)
    t2 = svc.create_task("Feature", story_points=5)
    svc.assign_task_to_version(t1.id, v.id)
    svc.assign_task_to_version(t2.id, v.id)
    svc.update_task_status(t2.id, TaskStatus.DONE)

    tasks = svc.get_version_tasks(v.id)
    r.ok('version_tasks_count') if len(tasks) == 2 else \
        r.fail('version_tasks_count', f'{len(tasks)}')

    report = svc.get_version_report(v.id)
    r.ok('version_report') if report and report["total_tasks"] == 2 and report["done_tasks"] == 1 and report["bug_count"] == 1 else \
        r.fail('version_report', f'{report}')
    r.ok('version_report_points') if report["total_story_points"] == 8 and report["completed_story_points"] == 5 else \
        r.fail('version_report_points', f'{report["total_story_points"]}/{report["completed_story_points"]}')
    cleanup()


def test_version_report_empty(r):
    svc = make_service()
    r.ok('version_report_empty') if svc.get_version_report("nonexistent") == {} else \
        r.fail('version_report_empty', 'should be {}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# WORKFLOW TRANSITIONS TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_workflow_allowed_transitions(r):
    svc = make_service()
    t = svc.create_task("Test")
    allowed = svc.get_allowed_transitions(t.id)
    r.ok('workflow_todo_allowed') if TaskStatus.IN_PROGRESS.value in allowed else \
        r.fail('workflow_todo_allowed', f'{allowed}')
    cleanup()


def test_workflow_transition_success(r):
    svc = make_service()
    t = svc.create_task("Test")
    result = svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    r.ok('workflow_transition_ok') if result and result.status == TaskStatus.IN_PROGRESS else \
        r.fail('workflow_transition_ok', f'{result.status if result else None}')
    cleanup()


def test_workflow_transition_blocked(r):
    svc = make_service()
    t = svc.create_task("Test")
    # Todo -> Done is not allowed directly (must go through In Progress)
    try:
        svc.transition_task(t.id, TaskStatus.DONE)
        r.fail('workflow_blocked', 'should raise ValueError')
    except ValueError:
        r.ok('workflow_blocked')
    cleanup()


def test_workflow_transition_nonexistent(r):
    svc = make_service()
    r.ok('workflow_nonexistent') if svc.get_allowed_transitions("nonexistent") == [] else \
        r.fail('workflow_nonexistent', 'should be []')
    cleanup()


def test_workflow_transition_clears_resolution(r):
    svc = make_service()
    t = svc.create_task("Test")
    svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    svc.set_resolution(t.id, Resolution.FIXED.value)
    # Move back from Done (set_resolution auto-sets Done) to In Progress
    svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    t2 = svc.get_task(t.id)
    r.ok('workflow_clears_resolution') if t2 and t2.resolution is None else \
        r.fail('workflow_clears_resolution', f'resolution={t2.resolution if t2 else None}')
    cleanup()


def test_workflow_full_cycle(r):
    svc = make_service()
    t = svc.create_task("Test")
    svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    svc.transition_task(t.id, TaskStatus.DONE)
    svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    svc.transition_task(t.id, TaskStatus.TODO)
    t2 = svc.get_task(t.id)
    r.ok('workflow_full_cycle') if t2 and t2.status == TaskStatus.TODO else \
        r.fail('workflow_full_cycle', f'status={t2.status if t2 else None}')
    cleanup()


def test_workflow_transitions_dict_structure(r):
    r.ok('workflow_has_default') if "*" in WORKFLOW_TRANSITIONS else \
        r.fail('workflow_has_default', 'missing * key')
    default = WORKFLOW_TRANSITIONS["*"]
    r.ok('workflow_default_has_todo') if TaskStatus.TODO.value in default else \
        r.fail('workflow_default_has_todo', 'missing Todo')
    r.ok('workflow_default_todo_to_ip') if TaskStatus.IN_PROGRESS.value in default[TaskStatus.TODO.value] else \
        r.fail('workflow_default_todo_to_ip', 'missing In Progress')


# ═══════════════════════════════════════════════════════════════════════
# TIME ESTIMATES TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_set_original_estimate(r):
    svc = make_service()
    t = svc.create_task("Test")
    result = svc.set_original_estimate(t.id, 5.0)
    r.ok('set_estimate') if result and result.original_estimate == 5.0 else \
        r.fail('set_estimate', f'est={result.original_estimate if result else None}')
    cleanup()


def test_set_estimate_negative(r):
    svc = make_service()
    t = svc.create_task("Test")
    try:
        svc.set_original_estimate(t.id, -1)
        r.fail('estimate_negative', 'should raise')
    except ValueError:
        r.ok('estimate_negative')
    cleanup()


def test_set_estimate_nonexistent(r):
    svc = make_service()
    r.ok('estimate_nonexistent') if svc.set_original_estimate("nope", 5) is None else \
        r.fail('estimate_nonexistent', 'should be None')
    cleanup()


def test_get_time_remaining(r):
    svc = make_service()
    t = svc.create_task("Test", original_estimate=10.0)
    svc.log_time(t.id, 3.5)
    info = svc.get_time_remaining(t.id)
    r.ok('time_remaining') if info and info["remaining"] == 6.5 and info["over"] == 0 else \
        r.fail('time_remaining', f'{info}')
    cleanup()


def test_get_time_over(r):
    svc = make_service()
    t = svc.create_task("Test", original_estimate=2.0)
    svc.log_time(t.id, 5.0)
    info = svc.get_time_remaining(t.id)
    r.ok('time_over') if info and info["remaining"] == 0 and info["over"] == 3.0 else \
        r.fail('time_over', f'{info}')
    cleanup()


def test_get_time_remaining_no_estimate(r):
    svc = make_service()
    t = svc.create_task("Test")
    info = svc.get_time_remaining(t.id)
    r.ok('time_no_estimate') if info and info["original_estimate"] == 0 and info["remaining"] == 0 else \
        r.fail('time_no_estimate', f'{info}')
    cleanup()


def test_estimate_history_recorded(r):
    svc = make_service()
    t = svc.create_task("Test")
    svc.set_original_estimate(t.id, 8.0)
    svc.set_original_estimate(t.id, 12.0)
    t2 = svc.get_task(t.id)
    est_changes = [h for h in t2.history if h.field_name == "original_estimate"]
    r.ok('estimate_history') if len(est_changes) == 2 else \
        r.fail('estimate_history', f'count={len(est_changes)}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# LABELS TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_add_label(r):
    svc = make_service()
    t = svc.create_task("Test")
    result = svc.add_label(t.id, "BugFix")
    r.ok('add_label') if result and "bugfix" in result.labels else \
        r.fail('add_label', f'labels={result.labels if result else None}')
    cleanup()


def test_add_label_case_lower(r):
    svc = make_service()
    t = svc.create_task("Test")
    result = svc.add_label(t.id, "  FRONTEND  ")
    r.ok('label_lowercase') if result and "frontend" in result.labels else \
        r.fail('label_lowercase', f'labels={result.labels if result else None}')
    cleanup()


def test_add_label_dedup(r):
    svc = make_service()
    t = svc.create_task("Test", labels=["backend"])
    result = svc.add_label(t.id, "backend")
    r.ok('label_dedup') if result and result.labels.count("backend") == 1 else \
        r.fail('label_dedup', f'count={result.labels.count("backend") if result else 0}')
    cleanup()


def test_add_label_max_20(r):
    svc = make_service()
    t = svc.create_task("Test", labels=[f"l{i}" for i in range(20)])
    try:
        svc.add_label(t.id, "extra")
        r.fail('label_max_20', 'should raise')
    except ValueError:
        r.ok('label_max_20')
    cleanup()


def test_remove_label(r):
    svc = make_service()
    t = svc.create_task("Test", labels=["backend", "frontend"])
    result = svc.remove_label(t.id, "frontend")
    r.ok('remove_label') if result and "frontend" not in result.labels else \
        r.fail('remove_label', f'labels={result.labels if result else None}')
    cleanup()


def test_remove_label_not_found(r):
    svc = make_service()
    t = svc.create_task("Test")
    result = svc.remove_label(t.id, "nonexistent")
    r.ok('remove_label_not_found') if result is not None else \
        r.fail('remove_label_not_found', 'should return task')
    cleanup()


def test_get_all_labels(r):
    svc = make_service()
    svc.create_task("T1", labels=["backend", "urgent"])
    svc.create_task("T2", labels=["frontend", "urgent"])
    labels = svc.get_all_labels()
    r.ok('all_labels') if labels == ["backend", "frontend", "urgent"] else \
        r.fail('all_labels', f'{labels}')
    cleanup()


def test_get_tasks_by_label(r):
    svc = make_service()
    t1 = svc.create_task("T1", labels=["backend"])
    t2 = svc.create_task("T2", labels=["frontend"])
    tasks = svc.get_tasks_by_label("backend")
    r.ok('tasks_by_label') if len(tasks) == 1 and tasks[0].id == t1.id else \
        r.fail('tasks_by_label', f'{len(tasks)}')
    cleanup()


def test_label_history(r):
    svc = make_service()
    t = svc.create_task("Test")
    svc.add_label(t.id, "test")
    svc.remove_label(t.id, "test")
    t2 = svc.get_task(t.id)
    label_hist = [h for h in t2.history if "label" in h.field_name]
    r.ok('label_history') if len(label_hist) == 2 else \
        r.fail('label_history', f'count={len(label_hist)}')
    cleanup()


def test_add_label_nonexistent_task(r):
    svc = make_service()
    r.ok('label_nonexistent_task') if svc.add_label("nope", "x") is None else \
        r.fail('label_nonexistent_task', 'should be None')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# BOARD DATA TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_board_data_basic(r):
    svc = make_service()
    svc.create_task("T1")
    svc.create_task("T2")
    svc.create_task("T3")
    svc.update_task_status(svc.get_all_tasks()[0].id, TaskStatus.IN_PROGRESS)
    svc.update_task_status(svc.get_all_tasks()[1].id, TaskStatus.DONE)
    board = svc.get_board_data()
    cols = board["columns"]
    counts = {c["id"]: c["count"] for c in cols}
    r.ok('board_basic') if counts == {"todo": 1, "in_progress": 1, "done": 1} else \
        r.fail('board_basic', f'{counts}')
    cleanup()


def test_board_data_empty(r):
    svc = make_service()
    board = svc.get_board_data()
    total = sum(c["count"] for c in board["columns"])
    r.ok('board_empty') if total == 0 else \
        r.fail('board_empty', f'{total}')
    cleanup()


def test_board_data_sprint_filter(r):
    svc = make_service()
    sp = svc.create_sprint("S1")
    t1 = svc.create_task("T1")
    t2 = svc.create_task("T2")
    svc.assign_task_to_sprint(t1.id, sp.id)
    board = svc.get_board_data(sprint_id=sp.id)
    total = sum(c["count"] for c in board["columns"])
    r.ok('board_sprint_filter') if total == 1 else \
        r.fail('board_sprint_filter', f'{total}')
    cleanup()


def test_board_columns_structure(r):
    svc = make_service()
    board = svc.get_board_data()
    col_ids = [c["id"] for c in board["columns"]]
    r.ok('board_columns') if col_ids == ["todo", "in_progress", "done"] else \
        r.fail('board_columns', f'{col_ids}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# PERSONAL DASHBOARD TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_dashboard_empty(r):
    svc = make_service()
    d = svc.get_personal_dashboard()
    r.ok('dashboard_empty_total') if d["total_tasks"] == 0 else \
        r.fail('dashboard_empty_total', f'{d["total_tasks"]}')
    r.ok('dashboard_empty_rate') if d["completion_rate"] == 0 else \
        r.fail('dashboard_empty_rate', f'{d["completion_rate"]}')
    r.ok('dashboard_empty_time') if d["total_time_spent"] == 0 else \
        r.fail('dashboard_empty_time', f'{d["total_time_spent"]}')
    cleanup()


def test_dashboard_with_data(r):
    svc = make_service()
    svc.create_task("T1", priority=Priority.HIGH)
    svc.create_task("T2", priority=Priority.LOW)
    svc.create_task("T3", story_points=5, original_estimate=8.0)
    svc.update_task_status(svc.get_all_tasks()[0].id, TaskStatus.DONE)
    d = svc.get_personal_dashboard()
    r.ok('dashboard_total') if d["total_tasks"] == 3 else \
        r.fail('dashboard_total', f'{d["total_tasks"]}')
    r.ok('dashboard_done') if d["done"] == 1 else \
        r.fail('dashboard_done', f'{d["done"]}')
    r.ok('dashboard_rate') if d["completion_rate"] == round(1/3*100, 1) else \
        r.fail('dashboard_rate', f'{d["completion_rate"]}')
    r.ok('dashboard_points') if d["total_story_points"] == 5 else \
        r.fail('dashboard_points', f'{d["total_story_points"]}')
    r.ok('dashboard_estimate') if d["total_original_estimate"] == 8.0 else \
        r.fail('dashboard_estimate', f'{d["total_original_estimate"]}')
    r.ok('dashboard_priority') if "High" in d["priority_breakdown"] and "Low" in d["priority_breakdown"] else \
        r.fail('dashboard_priority', f'{d["priority_breakdown"]}')
    r.ok('dashboard_recent') if len(d["recent_tasks"]) <= 10 else \
        r.fail('dashboard_recent', f'{len(d["recent_tasks"])}')
    r.ok('dashboard_7days') if len(d["completion_last_7_days"]) == 7 else \
        r.fail('dashboard_7days', f'{len(d["completion_last_7_days"])}')
    cleanup()


def test_dashboard_overdue(r):
    svc = make_service()
    past = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    svc.create_task("Overdue", due_date=past)
    d = svc.get_personal_dashboard()
    r.ok('dashboard_overdue') if d["overdue"] == 1 else \
        r.fail('dashboard_overdue', f'{d["overdue"]}')
    r.ok('dashboard_overdue_tasks') if len(d["overdue_tasks"]) == 1 else \
        r.fail('dashboard_overdue_tasks', f'{len(d["overdue_tasks"])}')
    cleanup()


def test_dashboard_labels_versions_count(r):
    svc = make_service()
    svc.create_task("T1", labels=["a", "b"])
    svc.create_version("v1.0")
    d = svc.get_personal_dashboard()
    r.ok('dashboard_labels_count') if d["labels_count"] == 2 else \
        r.fail('dashboard_labels_count', f'{d["labels_count"]}')
    r.ok('dashboard_versions_count') if d["versions_count"] == 1 else \
        r.fail('dashboard_versions_count', f'{d["versions_count"]}')
    cleanup()


def test_dashboard_active_sprint(r):
    svc = make_service()
    sp = svc.create_sprint("S1")
    svc.start_sprint(sp.id)
    svc.create_task("T1")
    svc.assign_task_to_sprint(svc.get_all_tasks()[0].id, sp.id)
    d = svc.get_personal_dashboard()
    r.ok('dashboard_active_sprint') if d["active_sprint"] is not None else \
        r.fail('dashboard_active_sprint', 'should have active sprint')
    r.ok('dashboard_sprint_name') if d["active_sprint"]["sprint_name"] == "S1" else \
        r.fail('dashboard_sprint_name', f'{d["active_sprint"]["sprint_name"]}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# TASK NEW FIELDS SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════

def test_task_labels_serialization(r):
    svc = make_service()
    t = svc.create_task("Test", labels=["frontend", "urgent"])
    d = t.to_dict()
    r.ok('task_labels_in_dict') if "labels" in d and d["labels"] == ["frontend", "urgent"] else \
        r.fail('task_labels_in_dict', f'{d.get("labels")}')
    t2 = Task.from_dict(d)
    r.ok('task_labels_from_dict') if t2.labels == ["frontend", "urgent"] else \
        r.fail('task_labels_from_dict', f'{t2.labels}')
    cleanup()


def test_task_version_estimate_serialization(r):
    svc = make_service()
    t = svc.create_task("Test", original_estimate=5.0, version_id="ver123")
    d = t.to_dict()
    r.ok('task_version_in_dict') if d.get("version_id") == "ver123" else \
        r.fail('task_version_in_dict', f'{d.get("version_id")}')
    r.ok('task_estimate_in_dict') if d.get("original_estimate") == 5.0 else \
        r.fail('task_estimate_in_dict', f'{d.get("original_estimate")}')
    t2 = Task.from_dict(d)
    r.ok('task_version_from_dict') if t2.version_id == "ver123" else \
        r.fail('task_version_from_dict', f'{t2.version_id}')
    r.ok('task_estimate_from_dict') if t2.original_estimate == 5.0 else \
        r.fail('task_estimate_from_dict', f'{t2.original_estimate}')
    cleanup()


def test_task_new_fields_defaults(r):
    t = Task(title="Test")
    r.ok('task_default_labels') if t.labels == [] else \
        r.fail('task_default_labels', f'{t.labels}')
    r.ok('task_default_version') if t.version_id is None else \
        r.fail('task_default_version', f'{t.version_id}')
    r.ok('task_default_estimate') if t.original_estimate == 0.0 else \
        r.fail('task_default_estimate', f'{t.original_estimate}')


# ═══════════════════════════════════════════════════════════════════════
# EXPORT/IMPORT INCLUDES VERSIONS
# ═══════════════════════════════════════════════════════════════════════

def test_export_includes_versions(r):
    svc = make_service()
    svc.create_task("T1")
    svc.create_version("v1.0")
    svc.create_version("v2.0")
    tmp = tempfile.mktemp(suffix='.json')
    try:
        svc.export_data(tmp)
        with open(tmp) as f:
            data = json.load(f)
        r.ok('export_has_versions') if "versions" in data and len(data["versions"]) == 2 else \
            r.fail('export_has_versions', f'keys={list(data.keys())}')
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    cleanup()


def test_import_versions_roundtrip(r):
    svc = make_service()
    svc.create_task("T1")
    svc.create_version("v1.0")
    svc.create_sprint("S1")
    tmp = tempfile.mktemp(suffix='.json')
    try:
        svc.export_data(tmp)
        # Import into fresh service
        svc2 = make_service(tempfile.mktemp(suffix='.json'))
        svc2.import_data(tmp, overwrite=True)
        r.ok('import_versions_count') if len(svc2.get_all_versions()) == 1 else \
            r.fail('import_versions_count', f'{len(svc2.get_all_versions())}')
        r.ok('import_sprints_count') if len(svc2.get_all_sprints()) == 1 else \
            r.fail('import_sprints_count', f'{len(svc2.get_all_sprints())}')
        r.ok('import_tasks_count') if len(svc2.get_all_tasks()) == 1 else \
            r.fail('import_tasks_count', f'{len(svc2.get_all_tasks())}')
        # Cleanup svc2
        db2 = svc2.repo.db_path
        for sfx in ['.json', '_sprints.json', '_versions.json']:
            p = db2.parent / (db2.stem + sfx)
            if p.exists():
                p.unlink()
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    cleanup()


def test_import_merge_versions(r):
    svc = make_service()
    svc.create_version("v1.0")
    data_str = json.dumps({
        "tasks": [],
        "versions": [{"id": "v2id", "name": "v2.0", "status": "Unreleased",
                       "release_date": None, "description": "", "created_at": "2025-01-01T00:00:00"}],
    })
    result = svc.import_data_from_string(data_str)
    r.ok('import_merge_versions') if result["versions_imported"] == 1 else \
        r.fail('import_merge_versions', f'{result}')
    r.ok('import_merge_total_versions') if len(svc.get_all_versions()) == 2 else \
        r.fail('import_merge_total_versions', f'{len(svc.get_all_versions())}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# PORTABLE EXE PATH HELPERS
# ═══════════════════════════════════════════════════════════════════════

def test_get_app_dir_normal(r):
    from core import paths
    repo_root = Path(__file__).parent.parent.resolve()
    r.ok('app_dir is repo root') if paths.app_dir == repo_root else \
        r.fail('app_dir', f'{paths.app_dir} != {repo_root}')
    r.ok('not frozen from source') if paths.frozen is False else r.fail('frozen', 'True')


def test_get_data_dir_creates_folder(r):
    from core import paths
    d = paths.ensure_data_dir()
    r.ok('data_dir under app_dir') if d == paths.app_dir / "data" / "db" else \
        r.fail('data_dir', f'{d}')
    r.ok('data_dir exists') if d.exists() else r.fail('data_dir_exists', 'not created')
    r.ok('tasks.json seeded') if paths.db_path.exists() else r.fail('seed', 'missing')


def test_get_db_path(r):
    from core import paths
    db = str(paths.db_path)
    r.ok('db ends tasks.json') if db.endswith("tasks.json") else r.fail('db', db)
    r.ok('db under data/db') if ("data" in db and "db" in db) else r.fail('db_layout', db)
    r.ok('settings sibling of db') if paths.settings_path.parent == paths.db_path.parent \
        else r.fail('settings', str(paths.settings_path))


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_full_lifecycle_version_labels_workflow_estimate(r):
    svc = make_service()
    # Create version
    v = svc.create_version("v1.0", "Release 1")
    # Create task with labels and estimate
    t = svc.create_task("Build API", labels=["backend", "api"], original_estimate=16.0)
    svc.assign_task_to_version(t.id, v.id)
    # Workflow through statuses
    svc.transition_task(t.id, TaskStatus.IN_PROGRESS)
    svc.log_time(t.id, 8.0)
    svc.add_label(t.id, "in-review")
    svc.transition_task(t.id, TaskStatus.DONE)
    svc.set_resolution(t.id, Resolution.DONE.value)
    # Verify
    t2 = svc.get_task(t.id)
    r.ok('integration_status') if t2.status == TaskStatus.DONE else \
        r.fail('integration_status', f'{t2.status}')
    r.ok('integration_labels') if len(t2.labels) == 3 else \
        r.fail('integration_labels', f'{t2.labels}')
    r.ok('integration_estimate') if t2.original_estimate == 16.0 else \
        r.fail('integration_estimate', f'{t2.original_estimate}')
    r.ok('integration_time') if t2.time_spent == 8.0 else \
        r.fail('integration_time', f'{t2.time_spent}')
    r.ok('integration_version') if t2.version_id == v.id else \
        r.fail('integration_version', f'{t2.version_id}')
    # Version report
    report = svc.get_version_report(v.id)
    r.ok('integration_report') if report["done_tasks"] == 1 and report["total_tasks"] == 1 else \
        r.fail('integration_report', f'{report}')
    # Dashboard
    d = svc.get_personal_dashboard()
    r.ok('integration_dashboard') if d["total_tasks"] == 1 and d["done"] == 1 else \
        r.fail('integration_dashboard', f'{d}')
    cleanup()


def test_create_task_with_labels_and_estimate(r):
    svc = make_service()
    t = svc.create_task("Test", labels=["a", "b"], original_estimate=4.0)
    r.ok('create_with_labels') if set(t.labels) == {"a", "b"} else \
        r.fail('create_with_labels', f'{t.labels}')
    r.ok('create_with_estimate') if t.original_estimate == 4.0 else \
        r.fail('create_with_estimate', f'{t.original_estimate}')
    cleanup()


def test_delete_version_nonexistent(r):
    svc = make_service()
    r.ok('delete_version_nonexistent') if not svc.delete_version("nope") else \
        r.fail('delete_version_nonexistent', 'should be False')
    cleanup()


def test_update_version_not_found(r):
    svc = make_service()
    r.ok('update_version_not_found') if svc.update_version("nope", name="x") is None else \
        r.fail('update_version_not_found', 'should be None')
    cleanup()


def test_release_version_auto_date(r):
    svc = make_service()
    v = svc.create_version("v1.0")
    released = svc.release_version(v.id)
    r.ok('release_auto_date') if released and released.release_date is not None else \
        r.fail('release_auto_date', f'{released.release_date if released else None}')
    r.ok('release_status') if released and released.status == "Released" else \
        r.fail('release_status', f'{released.status if released else None}')
    cleanup()


def test_board_data_tasks_are_dicts(r):
    svc = make_service()
    svc.create_task("T1")
    board = svc.get_board_data()
    todo_tasks = [c for c in board["columns"] if c["id"] == "todo"][0]["tasks"]
    r.ok('board_tasks_are_dicts') if len(todo_tasks) == 1 and isinstance(todo_tasks[0], dict) else \
        r.fail('board_tasks_are_dicts', f'{type(todo_tasks[0]) if todo_tasks else "empty"}')
    cleanup()


def test_create_multiple_versions(r):
    svc = make_service()
    svc.create_version("v1.0")
    svc.create_version("v2.0")
    svc.create_version("v3.0")
    r.ok('multiple_versions') if len(svc.get_all_versions()) == 3 else \
        r.fail('multiple_versions', f'{len(svc.get_all_versions())}')
    cleanup()


def test_workflow_done_direct_blocked(r):
    svc = make_service()
    t = svc.create_task("Test")
    try:
        svc.transition_task(t.id, TaskStatus.DONE)
        r.fail('done_direct_blocked', 'should raise')
    except ValueError as e:
        r.ok('done_direct_blocked') if "not allowed" in str(e).lower() else \
            r.fail('done_direct_blocked', f'wrong error: {e}')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    r = TestResults()

    print("\n=== Version Release Model ===")
    test_version_model_creation(r)
    test_version_model_serialization(r)
    test_version_is_released(r)
    test_version_is_not_released(r)
    test_version_from_dict_defaults(r)

    print("\n=== Version CRUD ===")
    test_version_crud_full(r)
    test_version_lifecycle(r)
    test_version_delete_clears_task_version_id(r)

    print("\n=== Version Task Assignment + Report ===")
    test_version_task_assignment(r)
    test_version_tasks_and_report(r)
    test_version_report_empty(r)

    print("\n=== Workflow Transitions ===")
    test_workflow_allowed_transitions(r)
    test_workflow_transition_success(r)
    test_workflow_transition_blocked(r)
    test_workflow_transition_nonexistent(r)
    test_workflow_transition_clears_resolution(r)
    test_workflow_full_cycle(r)
    test_workflow_transitions_dict_structure(r)

    print("\n=== Time Estimates ===")
    test_set_original_estimate(r)
    test_set_estimate_negative(r)
    test_set_estimate_nonexistent(r)
    test_get_time_remaining(r)
    test_get_time_over(r)
    test_get_time_remaining_no_estimate(r)
    test_estimate_history_recorded(r)

    print("\n=== Labels ===")
    test_add_label(r)
    test_add_label_case_lower(r)
    test_add_label_dedup(r)
    test_add_label_max_20(r)
    test_remove_label(r)
    test_remove_label_not_found(r)
    test_get_all_labels(r)
    test_get_tasks_by_label(r)
    test_label_history(r)
    test_add_label_nonexistent_task(r)

    print("\n=== Board Data ===")
    test_board_data_basic(r)
    test_board_data_empty(r)
    test_board_data_sprint_filter(r)
    test_board_columns_structure(r)
    test_board_data_tasks_are_dicts(r)

    print("\n=== Personal Dashboard ===")
    test_dashboard_empty(r)
    test_dashboard_with_data(r)
    test_dashboard_overdue(r)
    test_dashboard_labels_versions_count(r)
    test_dashboard_active_sprint(r)

    print("\n=== Task New Fields Serialization ===")
    test_task_labels_serialization(r)
    test_task_version_estimate_serialization(r)
    test_task_new_fields_defaults(r)

    print("\n=== Export/Import with Versions ===")
    test_export_includes_versions(r)
    test_import_versions_roundtrip(r)
    test_import_merge_versions(r)

    print("\n=== Portable EXE Path Helpers ===")
    test_get_app_dir_normal(r)
    test_get_data_dir_creates_folder(r)
    test_get_db_path(r)

    print("\n=== Integration + Edge Cases ===")
    test_full_lifecycle_version_labels_workflow_estimate(r)
    test_create_task_with_labels_and_estimate(r)
    test_delete_version_nonexistent(r)
    test_update_version_not_found(r)
    test_release_version_auto_date(r)
    test_create_multiple_versions(r)
    test_workflow_done_direct_blocked(r)

    ok = r.summary()
    sys.exit(0 if ok else 1)
