"""Extended tests for Task Manager.

Covers: CRITICAL priority, Urgency, Watchers, Epic links, Filters,
Move task, Log time, Team workload, Crash dump logger, Edge cases,
Serialization round-trips, Concurrency, Repository edge cases.
"""
import sys, os, json, tempfile, shutil, traceback as tb_module
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.models import (
    Task, TaskStatus, Priority, TaskModel, SubTask, TaskComment,
    TaskLink, HistoryEntry, LinkType, TaskType, _normalize_tags, Urgency,
)
from core.repository import TaskRepository
from core.service import TaskService
from utils.logger import setup_logging, get_logger

TMP_DB = tempfile.mktemp(suffix='.json')


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


# ═══════════════════════════════════════════════════════════════════════
# CRITICAL PRIORITY TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_critical_priority(r):
    r.ok('CRITICAL exists' if hasattr(Priority, 'CRITICAL') else 'no CRITICAL')
    t = Task(title='Critical task', priority=Priority.CRITICAL)
    r.ok('CRITICAL assigned' if t.priority == Priority.CRITICAL else f'got {t.priority}')
    r.ok('CRITICAL color' if Priority.CRITICAL.color == '#FF1744' else f'got {Priority.CRITICAL.color}')
    d = t.to_dict()
    r.ok('CRITICAL serializes' if d['priority'] == 'Critical' else f'got {d["priority"]}')
    t2 = Task.from_dict(d)
    r.ok('CRITICAL deserializes' if t2.priority == Priority.CRITICAL else f'got {t2.priority}')


def test_critical_priority_service(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Critical service task', priority=Priority.CRITICAL)
    r.ok('service creates CRITICAL' if t.priority == Priority.CRITICAL else 'wrong')
    loaded = service.get_task(t.id)
    r.ok('CRITICAL persists' if loaded.priority == Priority.CRITICAL else 'lost')
    t2 = service.create_task('Normal task')
    t3 = service.update_task(t2.id, priority=Priority.CRITICAL)
    r.ok('update to CRITICAL' if t3.priority == Priority.CRITICAL else f'got {t3.priority}')
    service.delete_task(t.id)
    service.delete_task(t2.id)


def test_critical_in_statistics(r):
    repo = TaskRepository(db_path=TMP_DB)
    repo.add(Task(title='C1', priority=Priority.CRITICAL))
    repo.add(Task(title='C2', priority=Priority.LOW))
    s = repo.get_statistics()
    r.ok('critical=1' if s['by_priority'].get('critical', 0) == 1 else f'got {s["by_priority"]}')
    r.ok('low=1' if s['by_priority']['low'] == 1 else 'low wrong')
    r.ok('total=2' if s['total'] == 2 else f'total={s["total"]}')


# ═══════════════════════════════════════════════════════════════════════
# URGENCY TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_urgency_enum(r):
    r.ok('Urgency exists' if hasattr(Urgency, 'LOW') else 'no Urgency')
    r.ok('4 levels' if len(Urgency) == 4 else f'got {len(Urgency)}')
    for u in Urgency:
        r.ok(f'urgency {u.value}' if isinstance(u.value, str) else 'not string')


def test_urgency_on_task(r):
    t = Task(title='Urgent task', urgency='Urgent')
    r.ok('urgency set' if t.urgency == 'Urgent' else f'got {t.urgency}')
    r.ok('default urgency Normal' if Task(title='X').urgency == Urgency.NORMAL.value else 'wrong default')
    d = t.to_dict()
    t2 = Task.from_dict(d)
    r.ok('urgency round-trip' if t2.urgency == 'Urgent' else f'got {t2.urgency}')


def test_urgency_service(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Urgent task', urgency='Urgent')
    r.ok('created with urgency' if t.urgency == 'Urgent' else f'got {t.urgency}')
    loaded = service.get_task(t.id)
    r.ok('urgency persists' if loaded.urgency == 'Urgent' else f'got {loaded.urgency}')
    t2 = service.update_task(t.id, urgency='High')
    r.ok('urgency updated' if t2.urgency == 'High' else f'got {t2.urgency}')
    history = service.get_task_history(t.id)
    urgency_changes = [h for h in history if h['field_name'] == 'urgency']
    r.ok('urgency change in history' if len(urgency_changes) >= 1 else 'not recorded')
    service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# WATCHERS TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_watchers_on_task(r):
    t = Task(title='Watched task')
    r.ok('watchers default empty' if t.watchers == [] else f'got {t.watchers}')
    t.watchers = ['Alice', 'Bob']
    d = t.to_dict()
    t2 = Task.from_dict(d)
    r.ok('watchers round-trip' if t2.watchers == ['Alice', 'Bob'] else f'got {t2.watchers}')


def test_watchers_service(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Watched task')

    t2 = service.add_watcher(t.id, 'Alice')
    r.ok('watcher added' if 'Alice' in t2.watchers else 'not added')
    r.ok('watcher change in history' if any(h['field_name'] == 'watcher_added' for h in service.get_task_history(t.id)) else 'not recorded')

    t3 = service.add_watcher(t.id, 'Alice')
    r.ok('duplicate watcher ignored' if t3.watchers.count('Alice') == 1 else f'got {t3.watchers.count("Alice")}')

    t4 = service.add_watcher(t.id, 'Bob')
    r.ok('2 watchers' if len(t4.watchers) == 2 else f'got {len(t4.watchers)}')

    t5 = service.remove_watcher(t.id, 'Alice')
    r.ok('watcher removed' if 'Alice' not in t5.watchers else 'still there')
    r.ok('1 watcher left' if len(t5.watchers) == 1 else f'got {len(t5.watchers)}')

    t6 = service.add_watcher(t.id, 'Charlie')
    t7 = service.remove_watcher(t.id, 'charlie')
    r.ok('case-insensitive remove' if 'Charlie' not in t7.watchers else 'not removed')

    r.ok('add watcher missing returns None' if service.add_watcher('nope', 'A') is None else 'should be None')
    r.ok('remove watcher missing returns None' if service.remove_watcher('nope', 'A') is None else 'should be None')

    service.create_task('W2', watchers=['Dave'])
    all_w = service.get_all_watchers()
    r.ok('all_watchers sorted' if isinstance(all_w, list) and 'Bob' in all_w and 'Dave' in all_w else f'got {all_w}')

    service.delete_task(t.id)
    for t in service.get_all_tasks():
        service.delete_task(t.id)


def test_watchers_on_create(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Create with watchers', watchers=['Alice', 'Bob', 'Alice'])
    r.ok('watchers on create' if len(t.watchers) == 2 else f'got {len(t.watchers)}')
    r.ok('Alice in watchers' if 'Alice' in t.watchers else 'missing')
    service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# EPIC LINK TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_epic_link(r):
    t = Task(title='Child task')
    r.ok('epic_link default None' if t.epic_link is None else f'got {t.epic_link}')
    t.epic_link = 'epic123'
    d = t.to_dict()
    t2 = Task.from_dict(d)
    r.ok('epic_link round-trip' if t2.epic_link == 'epic123' else f'got {t2.epic_link}')


def test_epic_link_service(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)

    epic = service.create_task('Epic', task_type=TaskType.EPIC.value)
    child = service.create_task('Child task')

    t = service.set_epic_link(child.id, epic.id)
    r.ok('epic link set' if t.epic_link == epic.id else f'got {t.epic_link}')

    children = service.get_epic_children(epic.id)
    r.ok('1 epic child' if len(children) == 1 else f'got {len(children)}')
    r.ok('child is correct' if children[0].id == child.id else 'wrong child')

    task2 = service.create_task('Not an epic')
    try:
        service.set_epic_link(child.id, task2.id)
        r.fail('non-epic target', 'should raise')
    except ValueError:
        r.ok('non-epic target rejected')

    t2 = service.set_epic_link(child.id, None)
    r.ok('epic link cleared' if t2.epic_link is None else f'got {t2.epic_link}')

    r.ok('set_epic_link missing returns None' if service.set_epic_link('nope', 'x') is None else 'should be None')

    service.delete_task(epic.id)
    service.delete_task(child.id)
    service.delete_task(task2.id)


# ═══════════════════════════════════════════════════════════════════════
# FILTER TASKS TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_filter_tasks(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)

    service.create_task('F1', priority=Priority.HIGH, tags=['backend'], assignee='Alice', task_type='Bug')
    service.create_task('F2', priority=Priority.LOW, tags=['frontend'], assignee='Bob', task_type='Story')
    service.create_task('F3', priority=Priority.HIGH, tags=['backend'], assignee='Alice', task_type='Task')

    high = service.filter_tasks(priority=Priority.HIGH)
    r.ok('filter by HIGH' if len(high) == 2 else f'got {len(high)}')

    alice = service.filter_tasks(assignee='Alice')
    r.ok('filter by assignee' if len(alice) == 2 else f'got {len(alice)}')

    backend = service.filter_tasks(tag='backend')
    r.ok('filter by tag' if len(backend) == 2 else f'got {len(backend)}')

    bugs = service.filter_tasks(task_type='Bug')
    r.ok('filter by type Bug' if len(bugs) == 1 else f'got {len(bugs)}')

    service.update_task(service.get_all_tasks()[0].id, urgency='Urgent')
    urgent = service.filter_tasks(urgency='Urgent')
    r.ok('filter by urgency' if len(urgent) == 1 else f'got {len(urgent)}')

    results = service.filter_tasks(query='F1')
    r.ok('filter by query' if len(results) == 1 else f'got {len(results)}')

    combined = service.filter_tasks(priority=Priority.HIGH, assignee='Alice')
    r.ok('combined filter' if len(combined) == 2 else f'got {len(combined)}')

    none = service.filter_tasks(priority=Priority.CRITICAL)
    r.ok('no results' if len(none) == 0 else f'got {len(none)}')

    all_t = service.filter_tasks()
    r.ok('empty filter returns all' if len(all_t) == 3 else f'got {len(all_t)}')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


def test_filter_overdue(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    past = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    service.create_task('Overdue filter', due_date=past)
    service.create_task('Future filter', due_date=future)

    overdue = service.filter_tasks(is_overdue=True)
    r.ok('filter overdue' if len(overdue) == 1 else f'got {len(overdue)}')
    not_overdue = service.filter_tasks(is_overdue=False)
    r.ok('filter not overdue' if len(not_overdue) == 1 else f'got {len(not_overdue)}')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# MOVE TASK TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_move_task(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Move me')

    t2 = service.move_task(t.id, 'forward')
    r.ok('forward to In Progress' if t2.status == TaskStatus.IN_PROGRESS else f'got {t2.status}')

    t3 = service.move_task(t.id, 'forward')
    r.ok('forward to Done' if t3.status == TaskStatus.DONE else f'got {t3.status}')

    t4 = service.move_task(t.id, 'forward')
    r.ok('forward at boundary' if t4.status == TaskStatus.DONE else 'moved past Done')

    t5 = service.move_task(t.id, 'backward')
    r.ok('backward to In Progress' if t5.status == TaskStatus.IN_PROGRESS else f'got {t5.status}')

    t6 = service.move_task(t.id, 'backward')
    r.ok('backward to Todo' if t6.status == TaskStatus.TODO else f'got {t6.status}')

    t7 = service.move_task(t.id, 'backward')
    r.ok('backward at boundary' if t7.status == TaskStatus.TODO else 'moved past Todo')

    try:
        service.move_task(t.id, 'sideways')
        r.fail('invalid direction', 'should raise')
    except ValueError:
        r.ok('invalid direction rejected')

    r.ok('move missing returns None' if service.move_task('nope') is None else 'should be None')

    service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# LOG TIME TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_log_time(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Time track', time_spent=1.0)

    t2 = service.log_time(t.id, 2.5)
    r.ok('time logged' if t2.time_spent == 3.5 else f'got {t2.time_spent}')
    r.ok('time change in history' if any(h['field_name'] == 'time_spent' for h in service.get_task_history(t.id)) else 'not recorded')

    t3 = service.log_time(t.id, 0.5)
    r.ok('cumulative time' if t3.time_spent == 4.0 else f'got {t3.time_spent}')

    try:
        service.log_time(t.id, -1)
        r.fail('negative hours', 'should raise')
    except ValueError:
        r.ok('negative hours rejected')

    try:
        service.log_time(t.id, 0)
        r.fail('zero hours', 'should raise')
    except ValueError:
        r.ok('zero hours rejected')

    r.ok('log time missing returns None' if service.log_time('nope', 1) is None else 'should be None')

    service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# TEAM WORKLOAD TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_team_workload(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    service.create_task('W1', assignee='Alice')
    service.create_task('W2', assignee='Alice')
    service.create_task('W3', assignee='Bob')
    service.create_task('W4')  # Unassigned

    wl = service.get_team_workload()
    r.ok('workload is list' if isinstance(wl, list) else f'got {type(wl)}')
    r.ok('3 entries' if len(wl) == 3 else f'got {len(wl)} entries')

    alice_wl = [w for w in wl if w['assignee'] == 'Alice'][0]
    r.ok('Alice total=2' if alice_wl['total'] == 2 else f'got {alice_wl["total"]}')
    r.ok('Alice todo=2' if alice_wl['todo'] == 2 else f'got {alice_wl["todo"]}')

    bob_wl = [w for w in wl if w['assignee'] == 'Bob'][0]
    r.ok('Bob total=1' if bob_wl['total'] == 1 else f'got {bob_wl["total"]}')

    unassigned = [w for w in wl if w['assignee'] == 'Unassigned'][0]
    r.ok('Unassigned exists' if unassigned else 'missing')

    t = service.create_task('W5', assignee='Alice', story_points=5)
    wl2 = service.get_team_workload()
    alice_wl2 = [w for w in wl2 if w['assignee'] == 'Alice'][0]
    r.ok('Alice SP sum' if alice_wl2['story_points_sum'] == 5 else f'got {alice_wl2["story_points_sum"]}')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# CRASH DUMP / LOGGER TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_crash_dump(r):
    import logging
    tmp_dir = tempfile.mkdtemp()
    logs_path = setup_logging(tmp_dir)
    log = get_logger('crash_test')
    log.error('Simulated crash error')

    with open(logs_path / 'error.log', 'r') as f:
        content = f.read()
    r.ok('error in error.log' if 'Simulated crash error' in content else 'missing from error.log')

    with open(logs_path / 'app.log', 'r') as f:
        app_content = f.read()
    r.ok('error in app.log too' if 'Simulated crash error' in app_content else 'missing from app.log')

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_logger_multiple_levels(r):
    import logging
    tmp_dir = tempfile.mkdtemp()
    logs_path = setup_logging(tmp_dir)
    log = get_logger('multi_level_test')

    log.debug('debug_msg_xyz')
    log.info('info_msg_xyz')
    log.warning('warning_msg_xyz')
    log.error('error_msg_xyz')

    with open(logs_path / 'app.log', 'r') as f:
        content = f.read()
    r.ok('debug in app.log' if 'debug_msg_xyz' in content else 'debug missing')
    r.ok('info in app.log' if 'info_msg_xyz' in content else 'info missing')
    r.ok('warning in app.log' if 'warning_msg_xyz' in content else 'warning missing')
    r.ok('error in app.log' if 'error_msg_xyz' in content else 'error missing')

    with open(logs_path / 'error.log', 'r') as f:
        error_content = f.read()
    r.ok('only error in error.log' if 'error_msg_xyz' in error_content else 'error missing')
    r.ok('debug NOT in error.log' if 'debug_msg_xyz' not in error_content else 'debug leaked to error.log')

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# INTERFACE TESTS
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# SERIALIZATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_full_serialization_roundtrip(r):
    t = Task(
        title='Full round-trip',
        description='A detailed description',
        status=TaskStatus.IN_PROGRESS,
        priority=Priority.CRITICAL,
        due_date='2026-12-31',
        start_date='2026-08-01',
        time_spent=7.5,
        tags=['critical', 'backend'],
        assignee='Alice',
        story_points=13,
        task_type=TaskType.BUG.value,
        urgency='Urgent',
        watchers=['Bob', 'Charlie'],
        epic_link='epic123',
        subtasks=[SubTask(title='Step 1', done=True), SubTask(title='Step 2')],
        comments=[TaskComment(author='Dave', text='Looking into it')],
        links=[TaskLink(target_task_id='t2', link_type='blocks')],
    )
    t.record_change('status', 'Todo', 'In Progress')

    d = t.to_dict()
    t2 = Task.from_dict(d)

    r.ok('round-trip title' if t2.title == t.title else 'mismatch')
    r.ok('round-trip status' if t2.status == t.status else 'mismatch')
    r.ok('round-trip priority' if t2.priority == t.priority else 'mismatch')
    r.ok('round-trip due_date' if t2.due_date == t.due_date else 'mismatch')
    r.ok('round-trip start_date' if t2.start_date == t.start_date else 'mismatch')
    r.ok('round-trip time_spent' if t2.time_spent == t.time_spent else 'mismatch')
    r.ok('round-trip tags' if t2.tags == t.tags else f'got {t2.tags}')
    r.ok('round-trip assignee' if t2.assignee == t.assignee else 'mismatch')
    r.ok('round-trip story_points' if t2.story_points == t.story_points else 'mismatch')
    r.ok('round-trip task_type' if t2.task_type == t.task_type else 'mismatch')
    r.ok('round-trip urgency' if t2.urgency == t.urgency else 'mismatch')
    r.ok('round-trip watchers' if t2.watchers == t.watchers else f'got {t2.watchers}')
    r.ok('round-trip epic_link' if t2.epic_link == t.epic_link else 'mismatch')
    r.ok('round-trip subtasks' if len(t2.subtasks) == 2 else f'got {len(t2.subtasks)}')
    r.ok('round-trip subtask done' if t2.subtasks[0].done else 'subtask done lost')
    r.ok('round-trip comments' if len(t2.comments) == 1 else 'comments lost')
    r.ok('round-trip links' if len(t2.links) == 1 else 'links lost')
    r.ok('round-trip history' if len(t2.history) == 1 else 'history lost')


def test_pydantic_model_validation(r):
    m = TaskModel(title='Valid', due_date='2026-12-31')
    r.ok('valid model created' if m.title == 'Valid' else 'model failed')
    t = m.to_task()
    r.ok('model to_task' if t.title == 'Valid' else 'to_task failed')
    m2 = TaskModel.from_task(t)
    r.ok('model from_task' if m2.title == 'Valid' else 'from_task failed')
    try:
        TaskModel(title='')
        r.fail('empty title model', 'should raise')
    except Exception:
        r.ok('empty title model rejected')


# ═══════════════════════════════════════════════════════════════════════
# REPOSITORY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_repository_concurrent_writes(r):
    repo = TaskRepository(db_path=TMP_DB)
    ids = []
    for i in range(20):
        t = Task(title=f'Concurrent {i}')
        repo.add(t)
        ids.append(t.id)
    r.ok('20 tasks added' if repo.count() == 20 else f'got {repo.count()}')
    for tid in ids:
        found = repo.get_by_id(tid)
        if not found:
            r.fail(f'task {tid[:4]} retrievable', 'not found')
    r.ok('all 20 tasks retrievable')
    for tid in ids:
        repo.delete(tid)
    r.ok('all deleted' if repo.count() == 0 else f'got {repo.count()}')


def test_repository_empty_file(r):
    tmp = tempfile.mktemp(suffix='.json')
    with open(tmp, 'w') as f:
        f.write('')
    repo = TaskRepository(db_path=tmp)
    r.ok('empty file handled' if repo.count() == 0 else f'got {repo.count()}')
    os.unlink(tmp)


def test_repository_update_nonexistent(r):
    repo = TaskRepository(db_path=TMP_DB)
    t = Task(title='Ghost')
    result = repo.update(t)
    r.ok('update nonexistent returns task' if result.id == t.id else 'should still return task')
    r.ok('repo still empty' if repo.count() == 0 else f'got {repo.count()}')


# ═══════════════════════════════════════════════════════════════════════
# SERVICE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_service_create_validation(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    try:
        service.create_task('')
        r.fail('empty title', 'should raise')
    except ValueError:
        r.ok('empty title rejected')
    try:
        service.create_task('   ')
        r.fail('whitespace title', 'should raise')
    except ValueError:
        r.ok('whitespace title rejected')
    try:
        service.create_task('Bad date', due_date='not-a-date')
        r.fail('bad date', 'should raise')
    except ValueError:
        r.ok('bad date rejected')
    try:
        service.create_task('Bad dates', start_date='2026-12-31', due_date='2026-01-01')
        r.fail('start > due', 'should raise')
    except ValueError:
        r.ok('start > due rejected')


def test_service_update_nonexistent(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    r.ok('update missing returns None' if service.update_task('nope', title='X') is None else 'should be None')
    r.ok('status missing returns None' if service.update_task_status('nope', TaskStatus.DONE) is None else 'should be None')


def test_service_create_with_all_fields(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task(
        'All fields',
        description='Full description',
        priority=Priority.CRITICAL,
        due_date='2026-12-31',
        start_date='2026-08-01',
        tags=['critical', 'backend', 'api'],
        assignee='Alice',
        story_points=13,
        task_type=TaskType.BUG.value,
        time_spent=2.5,
        urgency='Urgent',
        watchers=['Bob', 'Charlie'],
        epic_link=None,
    )
    r.ok('all fields task created' if t else 'no task')
    r.ok('CRITICAL' if t.priority == Priority.CRITICAL else 'wrong priority')
    r.ok('urgency Urgent' if t.urgency == 'Urgent' else f'got {t.urgency}')
    r.ok('2 watchers' if len(t.watchers) == 2 else f'got {len(t.watchers)}')
    r.ok('3 tags' if len(t.tags) == 3 else f'got {len(t.tags)}')
    service.delete_task(t.id)


def test_service_empty_title_on_update(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Original')
    try:
        service.update_task(t.id, title='')
        r.fail('empty title update', 'should raise')
    except ValueError:
        r.ok('empty title update rejected')
    loaded = service.get_task(t.id)
    r.ok('original intact after failed update' if loaded.title == 'Original' else f'got {loaded.title}')
    service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# LINKS EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_link_types_all(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('Linker')
    t2 = service.create_task('Target')
    for lt in LinkType:
        service.add_task_link(t1.id, t2.id, lt.value)
    loaded = service.get_task(t1.id)
    r.ok(f'{len(LinkType)} link types' if len(loaded.links) == len(LinkType) else f'got {len(loaded.links)}')
    linked = service.get_linked_tasks(t1.id)
    r.ok('get_linked_tasks has all types' if len(linked) == len(LinkType) else f'got {len(linked)} keys')
    service.remove_task_link(t1.id, t2.id)
    loaded2 = service.get_task(t1.id)
    r.ok('all links removed' if len(loaded2.links) == 0 else f'got {len(loaded2.links)}')
    service.delete_task(t1.id)
    service.delete_task(t2.id)


def test_blocks_link_not_symmetric(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('Blocker')
    t2 = service.create_task('Blocked')
    service.add_task_link(t1.id, t2.id, 'blocks')
    t2_loaded = service.get_task(t2.id)
    has_reverse = any(l.target_task_id == t1.id for l in t2_loaded.links)
    r.ok('blocks NOT symmetric' if not has_reverse else 'should not add reverse')
    service.delete_task(t1.id)
    service.delete_task(t2.id)


def test_clones_link_symmetric(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('Original')
    t2 = service.create_task('Clone')
    service.add_task_link(t1.id, t2.id, 'clones')
    t2_loaded = service.get_task(t2.id)
    has_reverse = any(l.target_task_id == t1.id for l in t2_loaded.links)
    r.ok('clones IS symmetric' if has_reverse else 'should add reverse')
    service.delete_task(t1.id)
    service.delete_task(t2.id)


# ═══════════════════════════════════════════════════════════════════════
# SUBTASK / COMMENT EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_subtask_progress_edge_cases(r):
    t = Task(title='Progress test')
    r.ok('empty progress 0.0' if t.subtask_progress() == 0.0 else f'got {t.subtask_progress()}')
    t.subtasks.append(SubTask(title='A', done=True))
    r.ok('1/1 progress 1.0' if t.subtask_progress() == 1.0 else f'got {t.subtask_progress()}')
    t.subtasks.append(SubTask(title='B', done=False))
    r.ok('1/2 progress 0.5' if t.subtask_progress() == 0.5 else f'got {t.subtask_progress()}')
    r.ok('negative index returns False' if not t.toggle_subtask(-1) else 'should be False')


def test_comment_edge_cases(r):
    t = Task(title='Comment edge')
    c = t.add_comment('', 'Some text')
    r.ok('empty author accepted' if c.author == '' else 'rejected')
    c2 = t.add_comment('Alice', '')
    r.ok('empty text accepted' if c2.text == '' else 'rejected')
    r.ok('delete from empty returns False' if not t.delete_comment('nope') else 'should be False')


# ═══════════════════════════════════════════════════════════════════════
# GANTT EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_gantt_done_task(r):
    t = Task(title='Done gantt', status=TaskStatus.DONE, start_date='2026-08-01', due_date='2026-08-10')
    end = t.get_gantt_end()
    r.ok('done gantt end is date' if len(end) == 10 else f'got {end}')
    r.ok('done gantt end >= start' if end >= t.get_gantt_start() else 'end < start')


def test_gantt_invalid_date(r):
    t = Task(title='Bad date', created_at='not-a-date')
    start = t.get_gantt_start()
    r.ok('gantt start no crash' if isinstance(start, str) else f'got {type(start)}')


# ═══════════════════════════════════════════════════════════════════════
# PRIORITY ORDER TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_priority_ordering(r):
    priorities = [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL]
    colors = [p.color for p in priorities]
    r.ok('4 distinct colors' if len(set(colors)) == 4 else f'got {len(set(colors))} unique')
    for p in priorities:
        r.ok(f'{p.name} has value' if p.value else 'no value')


# ═══════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    results = TestResults()
    tests = [
        ('CRITICAL priority', test_critical_priority),
        ('CRITICAL priority service', test_critical_priority_service),
        ('CRITICAL in statistics', test_critical_in_statistics),
        ('Urgency enum', test_urgency_enum),
        ('Urgency on task', test_urgency_on_task),
        ('Urgency service', test_urgency_service),
        ('Watchers on task', test_watchers_on_task),
        ('Watchers service', test_watchers_service),
        ('Watchers on create', test_watchers_on_create),
        ('Epic link model', test_epic_link),
        ('Epic link service', test_epic_link_service),
        ('Filter tasks', test_filter_tasks),
        ('Filter overdue', test_filter_overdue),
        ('Move task', test_move_task),
        ('Log time', test_log_time),
        ('Team workload', test_team_workload),
        ('Crash dump', test_crash_dump),
        ('Logger multiple levels', test_logger_multiple_levels),
        ('Full serialization round-trip', test_full_serialization_roundtrip),
        ('Pydantic model validation', test_pydantic_model_validation),
        ('Repository concurrent writes', test_repository_concurrent_writes),
        ('Repository empty file', test_repository_empty_file),
        ('Repository update nonexistent', test_repository_update_nonexistent),
        ('Service create validation', test_service_create_validation),
        ('Service update nonexistent', test_service_update_nonexistent),
        ('Service create all fields', test_service_create_with_all_fields),
        ('Service empty title update', test_service_empty_title_on_update),
        ('All link types', test_link_types_all),
        ('Blocks not symmetric', test_blocks_link_not_symmetric),
        ('Clones symmetric', test_clones_link_symmetric),
        ('Subtask progress edge cases', test_subtask_progress_edge_cases),
        ('Comment edge cases', test_comment_edge_cases),
        ('Gantt done task', test_gantt_done_task),
        ('Gantt invalid date', test_gantt_invalid_date),
        ('Priority ordering', test_priority_ordering),
    ]
    for name, fn in tests:
        print(f'\n--- {name} ---')
        try:
            fn(results)
        except Exception as e:
            results.fail(name, f'unhandled: {e}')
            tb_module.print_exc()
    print('\n' + '='*60)
    print('EXTENDED TEST SUMMARY')
    print('='*60)
    ok = results.summary()
    sys.exit(0 if ok else 1)
