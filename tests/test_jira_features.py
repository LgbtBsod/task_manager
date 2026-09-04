"""Tests for new Jira features: Sprints, Resolution, Export/Import, Error Handler.

Covers:
- Sprint CRUD (create, read, update, delete, lifecycle)
- Sprint task assignment and reports
- Resolution set/clear with auto-status transitions
- Export/Import (file and string, merge vs overwrite)
- Error handler (ErrorContext, write_error_log, install_error_handler)
- Task new fields (resolution, sprint_id) in serialization
- Sprint model edge cases (days_remaining, is_active)
- Full integration: sprint + resolution + export round-trip
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import utils.error_handler as _eh
from core.models import (
    Priority,
    Resolution,
    Sprint,
    SprintStatus,
    SubTask,
    Task,
    TaskComment,
    TaskStatus,
    Urgency,
)
from core.repository import TaskRepository
from core.service import TaskService
from utils.error_handler import ErrorContext, install_error_handler, write_error_log


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
    for f in [TMP_DB, TMP_DB.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)


# ═══════════════════════════════════════════════════════════════════════
# SPRINT MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_sprint_model(r):
    s = Sprint(name="Sprint 1", goal="Deliver v2")
    r.ok('sprint created') if s.id and s.name == "Sprint 1" else r.fail('sprint created', 'bad fields')
    r.ok('default status planning') if s.status == SprintStatus.PLANNING.value else r.fail('default status', s.status)
    r.ok('default dates none') if s.start_date is None and s.end_date is None else r.fail('default dates', f'{s.start_date}/{s.end_date}')


def test_sprint_serialization(r):
    s = Sprint(name="S1", goal="G1")
    d = s.to_dict()
    r.ok('to_dict has name') if d['name'] == 'S1' else r.fail('to_dict', 'bad name')
    r.ok('to_dict has goal') if d['goal'] == 'G1' else r.fail('to_dict', 'bad goal')

    s2 = Sprint.from_dict(d)
    r.ok('from_dict round-trip') if s2.id == s.id and s2.name == s.name else r.fail('round-trip', 'mismatch')


def test_sprint_is_active(r):
    r.ok('planning not active') if not Sprint(status=SprintStatus.PLANNING.value).is_active() else r.fail('planning', 'should not be active')
    r.ok('active is active') if Sprint(status=SprintStatus.ACTIVE.value).is_active() else r.fail('active', 'should be active')
    r.ok('completed not active') if not Sprint(status=SprintStatus.COMPLETED.value).is_active() else r.fail('completed', 'should not be active')
    r.ok('cancelled not active') if not Sprint(status=SprintStatus.CANCELLED.value).is_active() else r.fail('cancelled', 'should not be active')


def test_sprint_days_remaining(r):
    future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    past = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

    active_future = Sprint(status=SprintStatus.ACTIVE.value, end_date=future)
    dr = active_future.days_remaining()
    r.ok('active future days_remaining') if dr is not None and dr >= 3 else r.fail('days_remaining', f'got {dr}')

    active_past = Sprint(status=SprintStatus.ACTIVE.value, end_date=past)
    dr2 = active_past.days_remaining()
    r.ok('active past returns 0') if dr2 == 0 else r.fail('days_remaining past', f'got {dr2}')

    r.ok('planning no days') if Sprint(status=SprintStatus.PLANNING.value, end_date=future).days_remaining() is None else r.fail('planning days', 'should be None')
    r.ok('no end_date returns None') if Sprint(status=SprintStatus.ACTIVE.value).days_remaining() is None else r.fail('no end_date', 'should be None')


def test_sprint_days_remaining_invalid_date(r):
    s = Sprint(status=SprintStatus.ACTIVE.value, end_date="not-a-date")
    r.ok('invalid date returns None') if s.days_remaining() is None else r.fail('invalid date', 'should be None')


# ═══════════════════════════════════════════════════════════════════════
# SPRINT CRUD TESTS (Service)
# ═══════════════════════════════════════════════════════════════════════

def test_sprint_crud(r):
    cleanup()
    svc = make_service()

    # Create
    s = svc.create_sprint("Sprint Alpha", goal="Ship MVP")
    r.ok('sprint created via service') if s.id and s.name == "Sprint Alpha" else r.fail('create', 'bad fields')

    # Get
    fetched = svc.get_sprint(s.id)
    r.ok('get sprint by id') if fetched and fetched.goal == "Ship MVP" else r.fail('get', 'not found')
    r.ok('get non-existent returns None') if svc.get_sprint('nonexistent') is None else r.fail('get non-existent', 'should be None')

    # Update
    updated = svc.update_sprint(s.id, name="Sprint Alpha v2", goal="Updated goal")
    r.ok('update sprint') if updated and updated.name == "Sprint Alpha v2" else r.fail('update', 'bad name')
    r.ok('update non-existent returns None') if svc.update_sprint('nonexistent', name='X') is None else r.fail('update non-existent', 'should be None')

    # List all
    svc.create_sprint("Sprint Beta")
    all_sprints = svc.get_all_sprints()
    r.ok('list all sprints') if len(all_sprints) == 2 else r.fail('list', f'got {len(all_sprints)}')

    # Delete
    deleted = svc.delete_sprint(s.id)
    r.ok('delete sprint') if deleted else r.fail('delete', 'failed')
    r.ok('deleted sprint gone') if svc.get_sprint(s.id) is None else r.fail('gone', 'still exists')
    r.ok('delete non-existent returns False') if not svc.delete_sprint('nonexistent') else r.fail('delete non-existent', 'should be False')
    cleanup()


def test_sprint_lifecycle(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Lifecycle Sprint", start_date="2026-01-01", end_date="2026-02-01")

    # Start
    started = svc.start_sprint(s.id)
    r.ok('start_sprint') if started and started.status == SprintStatus.ACTIVE.value else r.fail('start', started.status if started else 'None')

    # Complete
    completed = svc.complete_sprint(s.id)
    r.ok('complete_sprint') if completed and completed.status == SprintStatus.COMPLETED.value else r.fail('complete', completed.status if completed else 'None')

    # Can't get days_remaining from completed
    r.ok('completed days_remaining is None') if completed.days_remaining() is None else r.fail('completed days', 'should be None')

    # New sprint -> cancel
    s2 = svc.create_sprint("Cancel Sprint")
    cancelled = svc.cancel_sprint(s2.id)
    r.ok('cancel_sprint') if cancelled and cancelled.status == SprintStatus.CANCELLED.value else r.fail('cancel', cancelled.status if cancelled else 'None')
    cleanup()


def test_sprint_with_dates(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Dated Sprint", start_date="2026-08-20", end_date="2026-09-20")
    fetched = svc.get_sprint(s.id)
    r.ok('start_date preserved') if fetched.start_date == "2026-08-20" else r.fail('start_date', fetched.start_date)
    r.ok('end_date preserved') if fetched.end_date == "2026-09-20" else r.fail('end_date', fetched.end_date)
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# SPRINT TASK ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════

def test_assign_task_to_sprint(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Sprint X")
    t = svc.create_task("Sprint Task")

    # Assign
    updated = svc.assign_task_to_sprint(t.id, s.id)
    r.ok('assign to sprint') if updated and updated.sprint_id == s.id else r.fail('assign', f'sprint_id={updated.sprint_id if updated else None}')

    # Verify via get_sprint_tasks
    sprint_tasks = svc.get_sprint_tasks(s.id)
    r.ok('sprint has 1 task') if len(sprint_tasks) == 1 and sprint_tasks[0].id == t.id else r.fail('sprint_tasks', f'got {len(sprint_tasks)}')

    # Unassign
    unassigned = svc.assign_task_to_sprint(t.id, None)
    r.ok('unassign from sprint') if unassigned and unassigned.sprint_id is None else r.fail('unassign', f'sprint_id={unassigned.sprint_id if unassigned else None}')

    # Verify empty
    r.ok('sprint has 0 tasks') if len(svc.get_sprint_tasks(s.id)) == 0 else r.fail('empty sprint', 'should be 0')
    cleanup()


def test_assign_nonexistent_sprint(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Task")
    try:
        svc.assign_task_to_sprint(t.id, 'nonexistent')
        r.fail('nonexistent sprint', 'should raise ValueError')
    except ValueError:
        r.ok('raises ValueError for bad sprint')
    r.ok('nonexistent task returns None') if svc.assign_task_to_sprint('bad', 'bad') is None else r.fail('nonexistent task', 'should be None')
    cleanup()


def test_sprint_report(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Report Sprint", start_date="2026-08-01", end_date="2026-09-01")
    svc.start_sprint(s.id)

    t1 = svc.create_task("T1", story_points=5)
    t2 = svc.create_task("T2", story_points=3, priority=Priority.HIGH)
    t3 = svc.create_task("T3", story_points=8)

    svc.assign_task_to_sprint(t1.id, s.id)
    svc.assign_task_to_sprint(t2.id, s.id)
    svc.assign_task_to_sprint(t3.id, s.id)

    svc.update_task_status(t1.id, TaskStatus.DONE)
    svc.log_time(t1.id, 2.5)
    svc.update_task_status(t2.id, TaskStatus.IN_PROGRESS)
    svc.log_time(t2.id, 1.0)

    report = svc.get_sprint_report(s.id)
    r.ok('report has total_tasks=3') if report['total_tasks'] == 3 else r.fail('total_tasks', report.get('total_tasks'))
    r.ok('report done_tasks=1') if report['done_tasks'] == 1 else r.fail('done_tasks', report.get('done_tasks'))
    r.ok('report in_progress=1') if report['in_progress_tasks'] == 1 else r.fail('in_progress', report.get('in_progress_tasks'))
    r.ok('report todo=1') if report['todo_tasks'] == 1 else r.fail('todo_tasks', report.get('todo_tasks'))
    r.ok('report completion_rate') if report['completion_rate'] == 33.3 else r.fail('rate', report.get('completion_rate'))
    r.ok('report total_points=16') if report['total_story_points'] == 16 else r.fail('points', report.get('total_story_points'))
    r.ok('report done_points=5') if report['completed_story_points'] == 5 else r.fail('done_points', report.get('completed_story_points'))
    r.ok('report time_spent=3.5') if report['total_time_spent'] == 3.5 else r.fail('time', report.get('total_time_spent'))
    r.ok('report has days_remaining') if report['days_remaining'] is not None else r.fail('days', 'missing')
    r.ok('report has sprint_name') if report['sprint_name'] == "Report Sprint" else r.fail('name', report.get('sprint_name'))

    # Non-existent sprint
    r.ok('empty report for bad sprint') if svc.get_sprint_report('bad') == {} else r.fail('bad report', 'should be {}')
    cleanup()


def test_empty_sprint_report(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Empty Sprint")
    report = svc.get_sprint_report(s.id)
    r.ok('empty sprint report total=0') if report['total_tasks'] == 0 else r.fail('empty total', report.get('total_tasks'))
    r.ok('empty sprint completion_rate=0') if report['completion_rate'] == 0 else r.fail('empty rate', report.get('completion_rate'))
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_resolution_enum(r):
    r.ok('5 resolution values') if len(Resolution) == 5 else r.fail('count', len(Resolution))
    r.ok('Done in values') if Resolution.DONE.value == 'Done' else r.fail('Done', Resolution.DONE.value)
    r.ok('Wont Do in values') if Resolution.WONT_DO.value == "Won't Do" else r.fail('WontDo', Resolution.WONT_DO.value)
    r.ok('Fixed in values') if Resolution.FIXED.value == 'Fixed' else r.fail('Fixed', Resolution.FIXED.value)


def test_set_resolution(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Bug task", task_type="Bug")

    # Set resolution -> auto-moves to Done
    resolved = svc.set_resolution(t.id, Resolution.FIXED.value)
    r.ok('resolution set') if resolved and resolved.resolution == Resolution.FIXED.value else r.fail('set', resolved.resolution if resolved else None)
    r.ok('auto status Done') if resolved and resolved.status == TaskStatus.DONE else r.fail('auto status', resolved.status if resolved else None)

    # History records
    history = svc.get_task_history(t.id)
    res_entries = [h for h in history if h['field_name'] == 'resolution']
    r.ok('resolution in history') if len(res_entries) == 1 else r.fail('res history', len(res_entries))

    # Non-existent task
    r.ok('nonexistent returns None') if svc.set_resolution('bad', Resolution.DONE.value) is None else r.fail('nonexistent', 'should be None')
    cleanup()


def test_set_resolution_invalid(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Task")
    try:
        svc.set_resolution(t.id, 'InvalidResolution')
        r.fail('invalid resolution', 'should raise ValueError')
    except ValueError as e:
        r.ok('raises ValueError') if 'Invalid resolution' in str(e) else r.fail('msg', str(e))
    cleanup()


def test_clear_resolution(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Task")
    svc.set_resolution(t.id, Resolution.DONE.value)
    # Now clear
    cleared = svc.clear_resolution(t.id)
    r.ok('resolution cleared') if cleared and cleared.resolution is None else r.fail('clear', cleared.resolution if cleared else None)
    r.ok('status back to In Progress') if cleared and cleared.status == TaskStatus.IN_PROGRESS else r.fail('status', cleared.status if cleared else None)

    # Non-existent
    r.ok('nonexistent returns None') if svc.clear_resolution('bad') is None else r.fail('nonexistent', 'should be None')
    cleanup()


def test_set_resolution_already_done(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Task")
    svc.update_task_status(t.id, TaskStatus.DONE)
    resolved = svc.set_resolution(t.id, Resolution.DONE.value)
    r.ok('still Done') if resolved and resolved.status == TaskStatus.DONE else r.fail('still done', resolved.status if resolved else None)
    # Should NOT add a duplicate status change history entry
    status_entries = [h for h in svc.get_task_history(t.id) if h['field_name'] == 'status']
    # Only one status change (the original update_task_status)
    r.ok('no duplicate status history') if len(status_entries) <= 1 else r.fail('dup history', len(status_entries))
    cleanup()


def test_all_resolutions(r):
    cleanup()
    svc = make_service()
    for res in Resolution:
        t = svc.create_task(f"Task {res.value}")
        result = svc.set_resolution(t.id, res.value)
        if not result or result.resolution != res.value:
            r.fail(f'resolution {res.value}', 'failed')
    r.ok(f'all {len(Resolution)} resolutions work')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# EXPORT / IMPORT TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_export_import_file(r):
    cleanup()
    svc = make_service()
    svc.create_task("Export Task 1", priority=Priority.HIGH)
    svc.create_task("Export Task 2", assignee="Alice")

    export_path = tempfile.mktemp(suffix='.json')
    svc.export_data(export_path)
    r.ok('export file created') if os.path.exists(export_path) else r.fail('export file', 'not found')

    with open(export_path) as f:
        data = json.load(f)
    r.ok('export has tasks') if 'tasks' in data and len(data['tasks']) == 2 else r.fail('export tasks', str(data.keys()))
    r.ok('export has sprints') if 'sprints' in data else r.fail('export sprints', 'missing')
    r.ok('export has schema_version') if 'schema_version' in data else r.fail('export version', 'missing')
    r.ok('export has timestamp') if 'exported_at' in data else r.fail('export ts', 'missing')
    os.unlink(export_path)
    cleanup()


def test_import_merge(r):
    cleanup()
    # Create original data
    svc = make_service()
    t1 = svc.create_task("Original Task", assignee="Bob")
    s1 = svc.create_sprint("Sprint 1")

    # Import new data (merge)
    import_data = {
        "tasks": [
            {"id": t1.id, "title": "Original Task", "status": "Todo", "priority": "Medium",
             "description": "", "created_at": t1.created_at, "updated_at": t1.updated_at,
             "tags": [], "subtasks": [], "comments": [], "links": [], "history": [],
             "assignee": "Bob", "story_points": None, "task_type": "Task",
             "time_spent": 0, "start_date": None, "due_date": None,
             "urgency": "Normal", "watchers": [], "epic_link": None,
             "resolution": None, "sprint_id": None},
            {"id": "import1", "title": "Imported Task", "status": "Todo", "priority": "Low",
             "description": "", "created_at": "", "updated_at": "",
             "tags": [], "subtasks": [], "comments": [], "links": [], "history": [],
             "assignee": None, "story_points": None, "task_type": "Task",
             "time_spent": 0, "start_date": None, "due_date": None,
             "urgency": "Normal", "watchers": [], "epic_link": None,
             "resolution": None, "sprint_id": None},
        ],
        "sprints": [
            {"id": "imp_sprint1", "name": "Imported Sprint", "goal": "", "status": "Planning",
             "start_date": None, "end_date": None, "created_at": ""},
        ],
    }

    json_str = json.dumps(import_data)
    result = svc.import_data_from_string(json_str, overwrite=False)
    r.ok('merge import result') if result['tasks_imported'] == 1 and result['sprints_imported'] == 1 else r.fail('merge', result)

    # Verify both tasks exist
    all_tasks = svc.get_all_tasks()
    r.ok('total 2 tasks after merge') if len(all_tasks) == 2 else r.fail('total', len(all_tasks))
    r.ok('original task preserved') if any(t.id == t1.id for t in all_tasks) else r.fail('original', 'missing')
    r.ok('imported task exists') if any(t.id == 'import1' for t in all_tasks) else r.fail('imported', 'missing')
    cleanup()


def test_import_overwrite(r):
    cleanup()
    svc = make_service()
    svc.create_task("Old Task 1")
    svc.create_task("Old Task 2")

    import_data = {
        "tasks": [
            {"id": "new1", "title": "New Task", "status": "Todo", "priority": "Medium",
             "description": "", "created_at": "", "updated_at": "",
             "tags": [], "subtasks": [], "comments": [], "links": [], "history": [],
             "assignee": None, "story_points": None, "task_type": "Task",
             "time_spent": 0, "start_date": None, "due_date": None,
             "urgency": "Normal", "watchers": [], "epic_link": None,
             "resolution": None, "sprint_id": None},
        ],
    }
    json_str = json.dumps(import_data)
    result = svc.import_data_from_string(json_str, overwrite=True)
    r.ok('overwrite result') if result['tasks_imported'] == 1 else r.fail('overwrite', result)

    all_tasks = svc.get_all_tasks()
    r.ok('only 1 task after overwrite') if len(all_tasks) == 1 else r.fail('overwrite count', len(all_tasks))
    r.ok('task is new one') if all_tasks[0].id == 'new1' else r.fail('overwrite task', all_tasks[0].id)
    cleanup()


def test_export_import_roundtrip(r):
    cleanup()
    svc = make_service()
    svc.create_task("RT Task", priority=Priority.CRITICAL, assignee="Charlie", tags=["important"])
    svc.create_sprint("RT Sprint", goal="Round trip test")

    export_path = tempfile.mktemp(suffix='.json')
    svc.export_data(export_path)

    # New service with fresh DB
    import_path = tempfile.mktemp(suffix='.json')
    svc2 = make_service(import_path)
    result = svc2.import_data(export_path, overwrite=True)
    r.ok('roundtrip import OK') if result['tasks_imported'] == 1 else r.fail('roundtrip', result)

    tasks = svc2.get_all_tasks()
    r.ok('roundtrip task exists') if len(tasks) == 1 else r.fail('roundtrip count', len(tasks))
    r.ok('roundtrip title') if tasks[0].title == "RT Task" else r.fail('roundtrip title', tasks[0].title)
    r.ok('roundtrip priority') if tasks[0].priority == Priority.CRITICAL else r.fail('roundtrip priority', tasks[0].priority)
    r.ok('roundtrip assignee') if tasks[0].assignee == "Charlie" else r.fail('roundtrip assignee', tasks[0].assignee)
    r.ok('roundtrip tags') if "important" in tasks[0].tags else r.fail('roundtrip tags', tasks[0].tags)

    sprints = svc2.get_all_sprints()
    r.ok('roundtrip sprint exists') if len(sprints) == 1 else r.fail('roundtrip sprint', len(sprints))
    r.ok('roundtrip sprint goal') if sprints[0].goal == "Round trip test" else r.fail('roundtrip goal', sprints[0].goal)

    os.unlink(export_path)
    for f in [import_path, import_path.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)
    cleanup()


def test_import_empty_data(r):
    cleanup()
    svc = make_service()
    svc.create_task("Existing")
    result = svc.import_data_from_string('{"tasks": [], "sprints": []}', overwrite=False)
    r.ok('empty import 0 tasks') if result['tasks_imported'] == 0 else r.fail('empty', result)
    r.ok('existing task preserved') if len(svc.get_all_tasks()) == 1 else r.fail('preserved', 'should be 1')
    cleanup()


def test_import_with_sprints_and_tasks(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Import Sprint")
    t = svc.create_task("Import Sprint Task")
    svc.assign_task_to_sprint(t.id, s.id)

    export_path = tempfile.mktemp(suffix='.json')
    svc.export_data(export_path)

    # Import into new DB
    import_path = tempfile.mktemp(suffix='.json')
    svc2 = make_service(import_path)
    svc2.import_data(export_path, overwrite=True)

    tasks = svc2.get_all_tasks()
    r.ok('imported task has sprint_id') if tasks and tasks[0].sprint_id == s.id else r.fail('sprint_id', tasks[0].sprint_id if tasks else None)

    os.unlink(export_path)
    for f in [import_path, import_path.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# ERROR HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_error_context(r):
    ctx = ErrorContext()
    ctx.clear()
    ctx.set('gui_mode', 'flet')
    ctx.set('app_dir', '/tmp/test')
    assert ctx.get('gui_mode') == 'flet'
    assert ctx.get('nonexistent', 'def') == 'def'
    assert ctx.to_dict() == {'gui_mode': 'flet', 'app_dir': '/tmp/test'}
    ctx.set('count', 3)                       # non-str coerced
    assert ctx.get('count') == '3'
    ctx.clear()
    assert ctx.to_dict() == {}


def test_error_context_shared_store(r):
    """Every instance reads/writes one process-global dict (no __new__ magic)."""
    ErrorContext().clear()
    ErrorContext().set('key', 'val')
    assert ErrorContext().get('key') == 'val'
    assert type(ErrorContext()) is ErrorContext   # plain class, not a cached singleton
    ErrorContext().clear()


def test_install_error_handler(r):
    tmp_dir = tempfile.mkdtemp()
    old_hook = sys.excepthook
    try:
        logs_dir = install_error_handler(tmp_dir)
        assert logs_dir.exists()
        assert logs_dir == Path(tmp_dir) / 'logs'
        assert sys.excepthook is _eh._crash_handler
    finally:
        sys.excepthook = old_hook
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_write_error_log(r):
    tmp_dir = tempfile.mkdtemp()
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            error_path = write_error_log(
                "Test error message", app_dir=tmp_dir,
                context={"test_key": "test_value"})
        assert error_path.name == 'error_log.txt'
        content = error_path.read_text(encoding='utf-8')
        for token in ('Test error message', '--- TRACEBACK ---', 'ValueError: boom',
                      'test_key: test_value', 'Python:', 'Platform:'):
            assert token in content, token
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_write_error_log_append(r):
    tmp_dir = tempfile.mkdtemp()
    try:
        write_error_log("First error", app_dir=tmp_dir)
        write_error_log("Second error", app_dir=tmp_dir)
        content = (Path(tmp_dir) / 'logs' / 'error_log.txt').read_text(encoding='utf-8')
        assert 'First error' in content and 'Second error' in content
        assert content.count('--- TRACEBACK ---') == 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_crash_handler_writes_full_dump(r):
    tmp_dir = tempfile.mkdtemp()
    old_hook = sys.excepthook
    try:
        install_error_handler(tmp_dir)
        try:
            raise RuntimeError("Test crash for error handler")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())

        error_log = Path(tmp_dir) / 'logs' / 'error_log.txt'
        content = error_log.read_text(encoding='utf-8')
        for token in ('CRASH', 'RuntimeError: Test crash for error handler',
                      '--- TRACEBACK ---', '--- LOCALS', 'MODULES', 'THREADS'):
            assert token in content, token

        crash_files = list(Path(tmp_dir).glob('logs/crash_*.log'))
        assert len(crash_files) == 1
        # per-incident file holds the same report that was appended to error_log.txt
        assert crash_files[0].read_text(encoding='utf-8') == content
    finally:
        sys.excepthook = old_hook
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# TASK NEW FIELDS SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════

def test_task_new_fields_serialization(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("New fields task")
    t.resolution = Resolution.FIXED.value
    t.sprint_id = "sprint123"

    # Serialize
    d = t.to_dict()
    r.ok('resolution in to_dict') if d.get('resolution') == Resolution.FIXED.value else r.fail('to_dict res', d.get('resolution'))
    r.ok('sprint_id in to_dict') if d.get('sprint_id') == 'sprint123' else r.fail('to_dict sprint', d.get('sprint_id'))

    # Update and save
    svc.repo.update(t)
    fetched = svc.get_task(t.id)
    r.ok('resolution persists') if fetched and fetched.resolution == Resolution.FIXED.value else r.fail('persist res', fetched.resolution if fetched else None)
    r.ok('sprint_id persists') if fetched and fetched.sprint_id == 'sprint123' else r.fail('persist sprint', fetched.sprint_id if fetched else None)
    cleanup()


def test_task_default_new_fields(r):
    t = Task("Test")
    r.ok('default resolution None') if t.resolution is None else r.fail('def res', t.resolution)
    r.ok('default sprint_id None') if t.sprint_id is None else r.fail('def sprint', t.sprint_id)


def test_task_from_dict_new_fields(r):
    data = {
        'id': 'abc123', 'title': 'Test', 'description': '', 'status': 'Todo',
        'priority': 'Medium', 'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
        'tags': [], 'subtasks': [], 'comments': [], 'links': [], 'history': [],
        'time_spent': 0, 'start_date': None, 'due_date': None,
        'assignee': None, 'story_points': None, 'task_type': 'Task',
        'urgency': 'Normal', 'watchers': [], 'epic_link': None,
        'resolution': 'Fixed', 'sprint_id': 'sp1',
    }
    t = Task.from_dict(data)
    r.ok('from_dict resolution') if t.resolution == 'Fixed' else r.fail('fd res', t.resolution)
    r.ok('from_dict sprint_id') if t.sprint_id == 'sp1' else r.fail('fd sprint', t.sprint_id)


def test_task_from_dict_missing_new_fields(r):
    data = {
        'id': 'abc123', 'title': 'Test', 'description': '', 'status': 'Todo',
        'priority': 'Medium', 'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
        'tags': [], 'subtasks': [], 'comments': [], 'links': [], 'history': [],
        'time_spent': 0, 'start_date': None, 'due_date': None,
        'assignee': None, 'story_points': None, 'task_type': 'Task',
        'urgency': 'Normal', 'watchers': [], 'epic_link': None,
    }
    t = Task.from_dict(data)
    r.ok('missing resolution -> None') if t.resolution is None else r.fail('missing res', t.resolution)
    r.ok('missing sprint_id -> None') if t.sprint_id is None else r.fail('missing sprint', t.sprint_id)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_full_sprint_lifecycle_with_tasks(r):
    cleanup()
    svc = make_service()

    # Create sprint
    s = svc.create_sprint("Sprint 42", goal="Launch feature X", start_date="2026-08-15", end_date="2026-08-29")
    svc.start_sprint(s.id)

    # Add tasks
    t1 = svc.create_task("Design UI", story_points=3, assignee="Alice")
    t2 = svc.create_task("Implement API", story_points=5, assignee="Bob")
    t3 = svc.create_task("Write tests", story_points=2, assignee="Charlie")

    svc.assign_task_to_sprint(t1.id, s.id)
    svc.assign_task_to_sprint(t2.id, s.id)
    svc.assign_task_to_sprint(t3.id, s.id)

    # Work on tasks
    svc.update_task_status(t1.id, TaskStatus.IN_PROGRESS)
    svc.update_task_status(t1.id, TaskStatus.DONE)
    svc.set_resolution(t1.id, Resolution.DONE.value)
    svc.log_time(t1.id, 2.0)

    svc.update_task_status(t2.id, TaskStatus.IN_PROGRESS)
    svc.log_time(t2.id, 3.0)

    # Report
    report = svc.get_sprint_report(s.id)
    r.ok('sprint report total=3') if report['total_tasks'] == 3 else r.fail('total', report.get('total_tasks'))
    r.ok('sprint report done=1') if report['done_tasks'] == 1 else r.fail('done', report.get('done_tasks'))
    r.ok('sprint report points=10') if report['total_story_points'] == 10 else r.fail('points', report.get('total_story_points'))
    r.ok('sprint is active') if report['status'] == 'Active' else r.fail('status', report.get('status'))

    # Complete sprint
    svc.complete_sprint(s.id)
    r.ok('sprint completed') if svc.get_sprint(s.id).status == 'Completed' else r.fail('completed', 'bad')
    cleanup()


def test_sprint_persistence(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Persistent Sprint")
    t = svc.create_task("PS Task")
    svc.assign_task_to_sprint(t.id, s.id)

    # Reload from disk
    svc2 = make_service()
    sprints = svc2.get_all_sprints()
    r.ok('sprint persists') if len(sprints) == 1 and sprints[0].name == "Persistent Sprint" else r.fail('persist', f'{len(sprints)} sprints')
    tasks = svc2.get_all_tasks()
    r.ok('task persists') if len(tasks) == 1 and tasks[0].sprint_id == s.id else r.fail('task persist', f'{len(tasks)} tasks')
    cleanup()


def test_delete_sprint_does_not_delete_tasks(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Temp Sprint")
    t = svc.create_task("Sprint Task")
    svc.assign_task_to_sprint(t.id, s.id)

    svc.delete_sprint(s.id)
    tasks = svc.get_all_tasks()
    r.ok('task survives sprint deletion') if len(tasks) == 1 else r.fail('survive', f'{len(tasks)} tasks')
    # Task still has the sprint_id reference (orphaned)
    r.ok('task keeps sprint_id ref') if tasks[0].sprint_id == s.id else r.fail('ref', tasks[0].sprint_id)
    cleanup()


def test_resolution_with_comments_and_history(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Bug task", task_type="Bug")
    svc.add_comment(t.id, "Dev", "I found the root cause")
    svc.update_task_status(t.id, TaskStatus.IN_PROGRESS)
    svc.log_time(t.id, 1.5)
    svc.set_resolution(t.id, Resolution.FIXED.value)

    # Reload and verify
    t2 = svc.get_task(t.id)
    r.ok('status Done after resolution') if t2.status == TaskStatus.DONE else r.fail('status', t2.status)
    r.ok('resolution Fixed') if t2.resolution == 'Fixed' else r.fail('resolution', t2.resolution)
    r.ok('comment preserved') if len(t2.comments) == 1 else r.fail('comment', len(t2.comments))
    r.ok('time_spent preserved') if t2.time_spent == 1.5 else r.fail('time', t2.time_spent)
    r.ok('history has multiple entries') if len(t2.history) >= 4 else r.fail('history', len(t2.history))
    cleanup()


def test_sprint_report_with_zero_points(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("No Points Sprint")
    t = svc.create_task("No SP Task")  # no story_points
    svc.assign_task_to_sprint(t.id, s.id)
    report = svc.get_sprint_report(s.id)
    r.ok('total_points=0') if report['total_story_points'] == 0 else r.fail('points', report.get('total_story_points'))
    r.ok('completion_rate=0') if report['completion_rate'] == 0 else r.fail('rate', report.get('completion_rate'))
    cleanup()


def test_multiple_sprints_task_moves(r):
    cleanup()
    svc = make_service()
    s1 = svc.create_sprint("S1")
    s2 = svc.create_sprint("S2")
    t = svc.create_task("Mover Task")

    svc.assign_task_to_sprint(t.id, s1.id)
    r.ok('s1 has task') if len(svc.get_sprint_tasks(s1.id)) == 1 else r.fail('s1', 'empty')

    svc.assign_task_to_sprint(t.id, s2.id)
    r.ok('s1 empty after move') if len(svc.get_sprint_tasks(s1.id)) == 0 else r.fail('s1 after move', 'not empty')
    r.ok('s2 has task') if len(svc.get_sprint_tasks(s2.id)) == 1 else r.fail('s2', 'empty')
    cleanup()


def test_export_import_with_resolution_and_sprint(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Export Sprint")
    t = svc.create_task("Full Task", task_type="Bug")
    svc.assign_task_to_sprint(t.id, s.id)
    svc.update_task_status(t.id, TaskStatus.IN_PROGRESS)
    svc.log_time(t.id, 3.0)
    svc.set_resolution(t.id, Resolution.FIXED.value)

    # Export
    export_path = tempfile.mktemp(suffix='.json')
    svc.export_data(export_path)

    # Import fresh
    import_path = tempfile.mktemp(suffix='.json')
    svc2 = make_service(import_path)
    svc2.import_data(export_path, overwrite=True)

    tasks = svc2.get_all_tasks()
    r.ok('task after full import') if len(tasks) == 1 else r.fail('count', len(tasks))
    t2 = tasks[0]
    r.ok('resolution imported') if t2.resolution == 'Fixed' else r.fail('res', t2.resolution)
    r.ok('sprint_id imported') if t2.sprint_id == s.id else r.fail('sprint', t2.sprint_id)
    r.ok('time_spent imported') if t2.time_spent == 3.0 else r.fail('time', t2.time_spent)

    sprints = svc2.get_all_sprints()
    r.ok('sprint imported') if len(sprints) == 1 else r.fail('sprint count', len(sprints))

    os.unlink(export_path)
    for f in [import_path, import_path.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_sprint_create_empty_name(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("")
    r.ok('empty name accepted') if s.name == "" else r.fail('name', s.name)
    r.ok('sprint has id') if s.id else r.fail('id', 'no id')
    cleanup()


def test_sprint_update_nonexistent_field(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("S")
    updated = svc.update_sprint(s.id, nonexistent_field="value")
    # Should not crash — just ignores the field
    r.ok('nonexistent field ignored') if updated and updated.name == "S" else r.fail('ignore', 'crashed or changed')
    cleanup()


def test_resolution_all_values_in_history(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("History Task")
    for res in Resolution:
        t = svc.get_task(t.id)
        if t.status == TaskStatus.DONE:
            svc.clear_resolution(t.id)
        svc.set_resolution(t.id, res.value)
    history = svc.get_task_history(t.id)
    res_entries = [h for h in history if h['field_name'] == 'resolution']
    # Each cycle: set_resolution + clear_resolution = 2 entries (except last: only set)
    # 5 set + 4 clear = 9 entries
    expected = len(Resolution) + len(Resolution) - 1
    r.ok(f'{expected} resolution entries') if len(res_entries) == expected else r.fail('entries', len(res_entries))
    cleanup()


def test_import_corrupted_json(r):
    cleanup()
    svc = make_service()
    svc.create_task("Safe Task")
    try:
        svc.import_data_from_string('not valid json{{{', overwrite=False)
        r.fail('corrupted json', 'should raise')
    except json.JSONDecodeError:
        r.ok('raises JSONDecodeError for bad json')
    # Original data should be intact
    r.ok('data intact after bad import') if len(svc.get_all_tasks()) == 1 else r.fail('intact', 'lost data')
    cleanup()


def test_sprint_from_dict_minimal(r):
    d = {"name": "Minimal"}
    s = Sprint.from_dict(d)
    r.ok('from_dict minimal name') if s.name == "Minimal" else r.fail('name', s.name)
    r.ok('from_dict generates id') if s.id else r.fail('id', 'no id')
    r.ok('from_dict default status') if s.status == SprintStatus.PLANNING.value else r.fail('status', s.status)


def test_task_create_with_resolution_and_sprint(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Full Task")
    # Set fields after creation
    t.resolution = Resolution.DONE.value
    t.sprint_id = "sp1"
    svc.repo.update(t)
    fetched = svc.get_task(t.id)
    r.ok('resolution after create') if fetched.resolution == Resolution.DONE.value else r.fail('res', fetched.resolution)
    r.ok('sprint_id after create') if fetched.sprint_id == "sp1" else r.fail('sprint', fetched.sprint_id)
    cleanup()


def test_sprint_delete_nonexistent(r):
    cleanup()
    svc = make_service()
    r.ok('delete nonexistent sprint False') if not svc.delete_sprint('nonexistent') else r.fail('delete', 'should be False')
    cleanup()


def test_sprint_report_after_deleting_tasks(r):
    cleanup()
    svc = make_service()
    s = svc.create_sprint("Report Sprint")
    t1 = svc.create_task("T1", story_points=5)
    t2 = svc.create_task("T2", story_points=3)
    svc.assign_task_to_sprint(t1.id, s.id)
    svc.assign_task_to_sprint(t2.id, s.id)
    svc.delete_task(t1.id)
    report = svc.get_sprint_report(s.id)
    r.ok('report 1 task after delete') if report['total_tasks'] == 1 else r.fail('total', report.get('total_tasks'))
    r.ok('report 3 points after delete') if report['total_story_points'] == 3 else r.fail('points', report.get('total_story_points'))
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    r = TestResults()

    print('\n--- Sprint Model ---')
    test_sprint_model(r)
    test_sprint_serialization(r)
    test_sprint_is_active(r)
    test_sprint_days_remaining(r)
    test_sprint_days_remaining_invalid_date(r)

    print('\n--- Sprint CRUD ---')
    test_sprint_crud(r)
    test_sprint_lifecycle(r)
    test_sprint_with_dates(r)

    print('\n--- Sprint Task Assignment ---')
    test_assign_task_to_sprint(r)
    test_assign_nonexistent_sprint(r)
    test_sprint_report(r)
    test_empty_sprint_report(r)

    print('\n--- Resolution ---')
    test_resolution_enum(r)
    test_set_resolution(r)
    test_set_resolution_invalid(r)
    test_clear_resolution(r)
    test_set_resolution_already_done(r)
    test_all_resolutions(r)

    print('\n--- Export / Import ---')
    test_export_import_file(r)
    test_import_merge(r)
    test_import_overwrite(r)
    test_export_import_roundtrip(r)
    test_import_empty_data(r)
    test_import_with_sprints_and_tasks(r)

    print('\n--- Error Handler ---')
    test_error_context(r)
    test_error_context_shared_store(r)
    test_install_error_handler(r)
    test_write_error_log(r)
    test_write_error_log_append(r)
    test_crash_handler_writes_full_dump(r)

    print('\n--- Task New Fields Serialization ---')
    test_task_new_fields_serialization(r)
    test_task_default_new_fields(r)
    test_task_from_dict_new_fields(r)
    test_task_from_dict_missing_new_fields(r)

    print('\n--- Integration ---')
    test_full_sprint_lifecycle_with_tasks(r)
    test_sprint_persistence(r)
    test_delete_sprint_does_not_delete_tasks(r)
    test_resolution_with_comments_and_history(r)
    test_sprint_report_with_zero_points(r)
    test_multiple_sprints_task_moves(r)
    test_export_import_with_resolution_and_sprint(r)

    print('\n--- Edge Cases ---')
    test_sprint_create_empty_name(r)
    test_sprint_update_nonexistent_field(r)
    test_resolution_all_values_in_history(r)
    test_import_corrupted_json(r)
    test_sprint_from_dict_minimal(r)
    test_task_create_with_resolution_and_sprint(r)
    test_sprint_delete_nonexistent(r)
    test_sprint_report_after_deleting_tasks(r)

    print('\n' + '=' * 60)
    print('JIRA FEATURES TEST SUMMARY')
    print('=' * 60)
    r.summary()

    cleanup()
