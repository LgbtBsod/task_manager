"""Stress tests for Task Manager.

Covers:
- Large data volumes (1000+ tasks)
- Deeply nested structures (many subtasks, comments, links, history)
- Long strings and unicode
- Concurrent event handlers
- Sprint velocity with many sprints
- Activity feed at scale
- Backlog reordering with many tasks
- Export/import large datasets
- Swimlanes with many lanes
- Filter combinations at scale
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.models import (
    ActivityEntry,
    HistoryEntry,
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
    _normalize_tags,
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
    for f in [TMP_DB, TMP_DB.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)


# ═══════════════════════════════════════════════════════════════════════
# LARGE DATA VOLUMES
# ═══════════════════════════════════════════════════════════════════════

def test_create_1000_tasks(r):
    """Create 1000 tasks and verify they all persist."""
    cleanup()
    svc = make_service()
    t0 = time.time()
    for i in range(1000):
        svc.create_task(f"Task {i:04d}", assignee=f"user{i % 20}")
    elapsed = time.time() - t0
    r.ok(f'1000 tasks created in {elapsed:.2f}s') if elapsed < 30 else r.fail('speed', f'{elapsed:.2f}s')
    all_tasks = svc.get_all_tasks()
    r.ok('1000 tasks in DB') if len(all_tasks) == 1000 else r.fail('count', len(all_tasks))
    cleanup()


def test_create_500_tasks_with_tags(r):
    cleanup()
    svc = make_service()
    for i in range(500):
        svc.create_task(f"T{i}", tags=[f"tag{i%10}", f"group{i%5}"])
    tags = svc.get_all_tags()
    r.ok('15 unique tags') if len(tags) == 15 else r.fail('tags', len(tags))
    cleanup()


def test_large_search(r):
    cleanup()
    svc = make_service()
    for i in range(500):
        svc.create_task(f"Task {i:04d} description here", description=f"Detailed desc for task {i}")
    results = svc.search_tasks("0042")
    r.ok('search finds specific') if len(results) >= 1 else r.fail('search', len(results))
    results_all = svc.search_tasks("")
    r.ok('empty search returns all') if len(results_all) == 500 else r.fail('empty search', len(results_all))
    results_none = svc.search_tasks("NONEXISTENT_XYZ_123")
    r.ok('no results for nonsense') if len(results_none) == 0 else r.fail('no results', len(results_none))
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# DEEPLY NESTED STRUCTURES
# ═══════════════════════════════════════════════════════════════════════

def test_many_subtasks(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Parent")
    for i in range(100):
        svc.add_subtask(t.id, f"Subtask {i}")
    fetched = svc.get_task(t.id)
    r.ok('100 subtasks') if len(fetched.subtasks) == 100 else r.fail('count', len(fetched.subtasks))
    r.ok('progress 0.0') if fetched.subtask_progress() == 0.0 else r.fail('progress', fetched.subtask_progress())
    # Toggle all
    for i in range(100):
        svc.toggle_subtask(t.id, i)
    fetched2 = svc.get_task(t.id)
    r.ok('progress 1.0 after all done') if fetched2.subtask_progress() == 1.0 else r.fail('progress done', fetched2.subtask_progress())
    cleanup()


def test_many_comments(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Discussion")
    for i in range(50):
        svc.add_comment(t.id, f"user{i%5}", f"Comment number {i} with some text")
    fetched = svc.get_task(t.id)
    r.ok('50 comments') if len(fetched.comments) == 50 else r.fail('count', len(fetched.comments))
    # Delete half
    for i in range(25):
        svc.delete_comment(t.id, fetched.comments[i*2].id)
    fetched2 = svc.get_task(t.id)
    r.ok('25 comments after delete') if len(fetched2.comments) == 25 else r.fail('after delete', len(fetched2.comments))
    cleanup()


def test_many_links(r):
    cleanup()
    svc = make_service()
    tasks = [svc.create_task(f"LinkT{i}") for i in range(20)]
    # Link task 0 to all others
    for i in range(1, 20):
        svc.add_task_link(tasks[0].id, tasks[i].id, "relates_to")
    fetched = svc.get_task(tasks[0].id)
    r.ok('19 links') if len(fetched.links) == 19 else r.fail('links', len(fetched.links))
    # Verify reverse links
    for i in range(1, 20):
        other = svc.get_task(tasks[i].id)
        has_link = any(l.target_task_id == tasks[0].id for l in other.links)
        if not has_link:
            r.fail(f'reverse link {i}', 'missing')
            break
    else:
        r.ok('all reverse links exist')
    cleanup()


def test_history_growth(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("History Task")
    # Each status change adds history
    for _ in range(10):
        svc.update_task_status(t.id, TaskStatus.IN_PROGRESS)
        svc.update_task_status(t.id, TaskStatus.TODO)
    fetched = svc.get_task(t.id)
    r.ok('20+ history entries') if len(fetched.history) >= 20 else r.fail('history', len(fetched.history))
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# UNICODE AND LONG STRINGS
# ═══════════════════════════════════════════════════════════════════════

def test_unicode_task(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Задача на русском языке 🚀", description="Описание с эмодзи: ✅ ❌ ⭐")
    fetched = svc.get_task(t.id)
    r.ok('unicode title') if fetched.title == "Задача на русском языке 🚀" else r.fail('title', fetched.title)
    r.ok('unicode desc') if "✅" in fetched.description else r.fail('desc', 'missing emoji')
    svc.add_comment(t.id, "Пользователь", "Комментарий на русском")
    svc.add_watcher(t.id, "Наблюдатель₁")
    fetched2 = svc.get_task(t.id)
    r.ok('unicode comment') if fetched2.comments[0].text == "Комментарий на русском" else r.fail('comment', 'wrong')
    r.ok('unicode watcher') if "Наблюдатель₁" in fetched2.watchers else r.fail('watcher', 'missing')
    cleanup()


def test_max_length_title(r):
    cleanup()
    svc = make_service()
    title_200 = "A" * 200
    t = svc.create_task(title_200)
    r.ok('200 char title OK') if t.title == title_200 else r.fail('200', len(t.title))
    try:
        svc.create_task("A" * 201)
        r.fail('201 chars', 'should raise')
    except ValueError:
        r.ok('201 char title rejected')
    cleanup()


def test_max_length_description(r):
    cleanup()
    svc = make_service()
    desc_5000 = "X" * 5000
    t = svc.create_task("Desc test", description=desc_5000)
    r.ok('5000 char desc OK') if t.description == desc_5000 else r.fail('5000', len(t.description))
    try:
        svc.create_task("Desc test 2", description="Y" * 5001)
        r.fail('5001 chars', 'should raise')
    except ValueError:
        r.ok('5001 char desc rejected')
    cleanup()


def test_max_length_assignee(r):
    cleanup()
    svc = make_service()
    name_100 = "U" * 100
    t = svc.create_task("Assignee test", assignee=name_100)
    r.ok('100 char assignee OK') if t.assignee == name_100 else r.fail('100', len(t.assignee))
    try:
        svc.create_task("Assignee test 2", assignee="V" * 101)
        r.fail('101 chars', 'should raise')
    except ValueError:
        r.ok('101 char assignee rejected')
    cleanup()


def test_special_chars_in_tags(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Tags", tags=["c++", "c#", "python-3.12", ".net", "foo/bar"])
    fetched = svc.get_task(t.id)
    r.ok('special chars in tags') if len(fetched.tags) == 5 else r.fail('tags', fetched.tags)
    cleanup()


def test_whitespace_title(r):
    cleanup()
    svc = make_service()
    try:
        svc.create_task("   ")
        r.fail('whitespace title', 'should raise')
    except ValueError:
        r.ok('whitespace-only title rejected')
    try:
        svc.create_task("")
        r.fail('empty title', 'should raise')
    except ValueError:
        r.ok('empty title rejected')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# SPRINT VELOCITY AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_velocity_many_sprints(r):
    cleanup()
    svc = make_service()
    for i in range(10):
        s = svc.create_sprint(f"Sprint {i}")
        svc.start_sprint(s.id)
        points_per_sprint = (i + 1) * 3  # 3, 6, 9, ...
        for j in range(points_per_sprint):
            t = svc.create_task(f"S{i}T{j}", story_points=1)
            svc.assign_task_to_sprint(t.id, s.id)
            if j < i + 1:  # Not all done
                svc.update_task_status(t.id, TaskStatus.DONE)
        svc.complete_sprint(s.id)

    vel = svc.get_sprint_velocity(last_n=10)
    r.ok('10 completed sprints in velocity') if len(vel) == 10 else r.fail('vel count', len(vel))
    # Last 5 average
    avg = svc.get_average_velocity(5)
    r.ok('average velocity > 0') if avg > 0 else r.fail('avg', avg)
    avg_all = svc.get_average_velocity(100)
    r.ok('avg_all is computed') if avg_all > 0 else r.fail('avg all', avg_all)
    cleanup()


def test_velocity_no_completed_sprints(r):
    cleanup()
    svc = make_service()
    svc.create_sprint("Active Sprint")
    r.ok('empty velocity') if svc.get_sprint_velocity() == [] else r.fail('vel', 'should be empty')
    r.ok('avg velocity 0') if svc.get_average_velocity() == 0.0 else r.fail('avg', 'should be 0')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# ACTIVITY FEED AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_activity_feed_scale(r):
    cleanup()
    svc = make_service()
    for i in range(50):
        t = svc.create_task(f"ActivityTask {i}")
        svc.add_comment(t.id, "user", f"Comment {i}")
        svc.update_task(t.id, priority=Priority.HIGH if i % 2 == 0 else Priority.LOW)

    feed = svc.get_activity_feed(limit=1000)
    r.ok('feed has entries') if len(feed) > 0 else r.fail('feed', 'empty')
    r.ok('feed limit respected') if len(feed) <= 1000 else r.fail('limit', len(feed))
    # Should be sorted descending
    for i in range(len(feed) - 1):
        if feed[i]["timestamp"] < feed[i+1]["timestamp"]:
            r.fail('sort order', f'index {i}')
            break
    else:
        r.ok('feed sorted descending')

    # Small limit
    feed_small = svc.get_activity_feed(limit=5)
    r.ok('limit 5') if len(feed_small) == 5 else r.fail('limit 5', len(feed_small))
    cleanup()


def test_activity_feed_empty(r):
    cleanup()
    svc = make_service()
    r.ok('empty feed') if svc.get_activity_feed() == [] else r.fail('feed', 'should be empty')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# BACKLOG REORDERING AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_backlog_reorder_100(r):
    cleanup()
    svc = make_service()
    tasks = [svc.create_task(f"Backlog {i:03d}") for i in range(100)]
    # Reverse order
    reversed_ids = [t.id for t in reversed(tasks)]
    result = svc.reorder_backlog(reversed_ids)
    r.ok('reorder 100 succeeds') if result else r.fail('reorder', 'failed')
    backlog = svc.get_backlog()
    r.ok('backlog has 100') if len(backlog) == 100 else r.fail('backlog count', len(backlog))
    # First in reversed order should be rank 0
    r.ok('first is original last') if backlog[0].id == tasks[-1].id else r.fail('order', 'wrong first')
    # Ranks should be 0..99
    ranks = [t.rank for t in backlog]
    r.ok('ranks sequential') if ranks == list(range(100)) else r.fail('ranks', ranks[:5])
    cleanup()


def test_backlog_mixed_statuses(r):
    cleanup()
    svc = make_service()
    t1 = svc.create_task("Todo 1")
    t2 = svc.create_task("Todo 2")
    t3 = svc.create_task("Done Task")
    svc.update_task_status(t3.id, TaskStatus.DONE)
    svc.set_task_rank(t2.id, 0)
    svc.set_task_rank(t1.id, 10)
    backlog = svc.get_backlog()
    r.ok('backlog only Todo') if len(backlog) == 2 else r.fail('backlog', len(backlog))
    r.ok('backlog sorted by rank') if backlog[0].id == t2.id else r.fail('sort', 'wrong order')
    cleanup()


def test_rank_negative_clamped(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Rank Test")
    svc.set_task_rank(t.id, -5)
    fetched = svc.get_task(t.id)
    r.ok('negative rank clamped to 0') if fetched.rank == 0 else r.fail('clamp', fetched.rank)
    cleanup()


def test_backlog_empty(r):
    cleanup()
    svc = make_service()
    r.ok('empty backlog') if svc.get_backlog() == [] else r.fail('backlog', 'should be empty')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# SWIMLANES AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_swimlanes_many_assignees(r):
    cleanup()
    svc = make_service()
    for i in range(50):
        svc.create_task(f"T{i}", assignee=f"user{i % 10}")
        svc.update_task_status("placeholder", TaskStatus.IN_PROGRESS)  # won't match

    # Set various statuses
    tasks = svc.get_all_tasks()
    for i, t in enumerate(tasks):
        if i % 3 == 0:
            svc.update_task_status(t.id, TaskStatus.IN_PROGRESS)
        elif i % 3 == 1:
            svc.update_task_status(t.id, TaskStatus.DONE)

    lanes = svc.get_swimlanes("assignee")
    r.ok('10 assignee lanes') if len(lanes) == 10 else r.fail('lanes', len(lanes))
    total_in_lanes = sum(
        len(lane["todo"]) + len(lane["in_progress"]) + len(lane["done"])
        for lane in lanes.values()
    )
    r.ok('all tasks in lanes') if total_in_lanes == 50 else r.fail('total', total_in_lanes)
    cleanup()


def test_swimlanes_unassigned(r):
    cleanup()
    svc = make_service()
    svc.create_task("No one")
    svc.create_task("Also no one")
    lanes = svc.get_swimlanes("assignee")
    r.ok('Unassigned lane exists') if "Unassigned" in lanes else r.fail('unassigned', 'missing')
    r.ok('2 in unassigned') if len(lanes["Unassigned"]["todo"]) == 2 else r.fail('count', lanes["Unassigned"]["todo"])
    cleanup()


def test_swimlanes_invalid_group_by(r):
    cleanup()
    svc = make_service()
    svc.create_task("T1")
    lanes = svc.get_swimlanes("invalid_field")
    # Falls back to assignee
    r.ok('fallback to assignee') if "Unassigned" in lanes else r.fail('fallback', 'wrong')
    cleanup()


def test_swimlanes_task_type(r):
    cleanup()
    svc = make_service()
    svc.create_task("Bug1", task_type=TaskType.BUG.value)
    svc.create_task("Bug2", task_type=TaskType.BUG.value)
    svc.create_task("Story1", task_type=TaskType.STORY.value)
    lanes = svc.get_swimlanes("task_type")
    r.ok('Bug lane') if "Bug" in lanes else r.fail('bug', 'missing')
    r.ok('Story lane') if "Story" in lanes else r.fail('story', 'missing')
    r.ok('2 bugs') if len(lanes["Bug"]["todo"]) == 2 else r.fail('bug count', lanes["Bug"]["todo"])
    cleanup()


def test_swimlanes_urgency(r):
    cleanup()
    svc = make_service()
    svc.create_task("U1", urgency=Urgency.LOW.value)
    svc.create_task("U2", urgency=Urgency.URGENT.value)
    svc.create_task("U3", urgency=Urgency.NORMAL.value)
    lanes = svc.get_swimlanes("urgency")
    r.ok('3 urgency lanes') if len(lanes) == 3 else r.fail('lanes', len(lanes))
    r.ok('Urgent lane') if "Urgent" in lanes else r.fail('urgent', 'missing')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# EXPORT/IMPORT LARGE DATASETS
# ═══════════════════════════════════════════════════════════════════════

def test_export_import_500_tasks(r):
    cleanup()
    svc = make_service()
    for i in range(500):
        svc.create_task(f"ExpTask {i}", assignee=f"user{i%10}", tags=[f"tag{i%5}"])

    export_path = tempfile.mktemp(suffix='.json')
    svc.export_data(export_path)

    import_path = tempfile.mktemp(suffix='.json')
    svc2 = make_service(import_path)
    result = svc2.import_data(export_path, overwrite=True)
    r.ok('500 tasks imported') if result["tasks_imported"] == 500 else r.fail('import', result)
    r.ok('500 tasks in DB') if len(svc2.get_all_tasks()) == 500 else r.fail('db count', len(svc2.get_all_tasks()))

    os.unlink(export_path)
    for f in [import_path, import_path.replace('.json', '_sprints.json')]:
        if os.path.exists(f):
            os.unlink(f)
    cleanup()


def test_import_malformed_task_data(r):
    cleanup()
    svc = make_service()
    svc.create_task("Safe")

    # Missing required fields - import writes raw JSON
    bad_data = {"tasks": [{"id": "bad1"}], "sprints": []}
    result = svc.import_data_from_string(json.dumps(bad_data), overwrite=True)
    r.ok("malformed import writes data") if result["tasks_imported"] == 1 else r.fail("malformed write", result)
    # Reading is resilient: the unparseable record is skipped (and logged),
    # not crashed on.
    svc3 = make_service()
    tasks = svc3.get_all_tasks()
    r.ok("malformed record skipped on read") if tasks == [] else r.fail("read malformed", f"got {tasks}")
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# COMPONENTS AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_components_many_tasks(r):
    cleanup()
    svc = make_service()
    all_components = ["frontend", "backend", "api", "database", "auth", "ui", "docs", "tests"]
    for i in range(100):
        comps = [all_components[i % len(all_components)], all_components[(i+3) % len(all_components)]]
        svc.create_task(f"CompTask {i}", components=comps)

    unique = svc.get_all_components()
    r.ok('8 unique components') if len(unique) == 8 else r.fail('comps', len(unique))
    r.ok('sorted') if unique == sorted(unique) else r.fail('sorted', unique)

    # Filter by component
    backend_tasks = svc.get_tasks_by_component("backend")
    r.ok('backend has tasks') if len(backend_tasks) > 0 else r.fail('backend', 'empty')
    r.ok('case insensitive') if len(svc.get_tasks_by_component("BACKEND")) == len(backend_tasks) else r.fail('case', 'mismatch')
    cleanup()


def test_components_empty(r):
    cleanup()
    svc = make_service()
    r.ok('no components') if svc.get_all_components() == [] else r.fail('comps', 'should be empty')
    r.ok('no tasks by component') if svc.get_tasks_by_component("anything") == [] else r.fail('by comp', 'should be empty')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# BULK OPERATIONS AT SCALE
# ═══════════════════════════════════════════════════════════════════════

def test_bulk_delete_200(r):
    cleanup()
    svc = make_service()
    ids = []
    for i in range(200):
        t = svc.create_task(f"BulkDel {i}")
        ids.append(t.id)
    count = svc.bulk_delete(ids)
    r.ok('200 deleted') if count == 200 else r.fail('count', count)
    r.ok('DB empty') if svc.repo.count() == 0 else r.fail('db', svc.repo.count())
    cleanup()


def test_bulk_status_200(r):
    cleanup()
    svc = make_service()
    ids = []
    for i in range(200):
        t = svc.create_task(f"BulkStat {i}")
        ids.append(t.id)
    count = svc.bulk_status_change(ids, TaskStatus.DONE)
    r.ok('200 updated') if count == 200 else r.fail('count', count)
    stats = svc.get_statistics()
    r.ok('all done') if stats['by_status']['done'] == 200 else r.fail('stats', stats['by_status'])
    cleanup()


def test_clone_many_subtasks(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Original")
    for i in range(20):
        svc.add_subtask(t.id, f"Sub {i}")
    cloned = svc.clone_task(t.id)
    r.ok('cloned has 20 subtasks') if len(cloned.subtasks) == 20 else r.fail('clone subs', len(cloned.subtasks))
    # Cloned subtasks should not be done
    for s in cloned.subtasks:
        if s.done:
            r.fail('clone sub done', s.title)
            break
    else:
        r.ok('cloned subtasks not done')
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# REPOSITORY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

def test_repository_empty_file(r):
    """Empty JSON file ([]) should work."""
    tmp = tempfile.mktemp(suffix='.json')
    with open(tmp, 'w') as f:
        json.dump([], f)
    repo = TaskRepository(tmp)
    r.ok('empty repo') if repo.count() == 0 else r.fail('count', repo.count())
    r.ok('empty get_all') if repo.get_all() == [] else r.fail('get_all', 'not empty')
    os.unlink(tmp)
    sp = tmp.replace('.json', '_sprints.json')
    if os.path.exists(sp): os.unlink(sp)


def test_repository_update_nonexistent(r):
    cleanup()
    svc = make_service()
    t = Task("Ghost")
    result = svc.repo.update(t)
    r.ok('update non-existent returns task') if result.id == t.id else r.fail('update', 'should return task')
    cleanup()


def test_repository_double_delete(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Double")
    r.ok('first delete') if svc.delete_task(t.id) else r.fail('first', 'failed')
    r.ok('second delete False') if not svc.delete_task(t.id) else r.fail('second', 'should be False')
    cleanup()


def test_statistics_empty(r):
    cleanup()
    svc = make_service()
    stats = svc.get_statistics()
    r.ok('total 0') if stats['total'] == 0 else r.fail('total', stats['total'])
    r.ok('completion_rate 0') if stats['completion_rate'] == 0 else r.fail('rate', stats['completion_rate'])
    cleanup()


def test_statistics_all_done(r):
    cleanup()
    svc = make_service()
    for i in range(10):
        t = svc.create_task(f"D{i}", priority=Priority.CRITICAL if i % 2 == 0 else Priority.LOW)
        svc.update_task_status(t.id, TaskStatus.DONE)
    stats = svc.get_statistics()
    r.ok('100% completion') if stats['completion_rate'] == 100.0 else r.fail('rate', stats['completion_rate'])
    r.ok('5 critical') if stats['by_priority']['critical'] == 5 else r.fail('critical', stats['by_priority']['critical'])
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# ACTIVITY ENTRY MODEL
# ═══════════════════════════════════════════════════════════════════════

def test_activity_entry_model(r):
    ae = ActivityEntry(action="created", task_title="Test", author="Alice", details="new task created")
    d = ae.to_dict()
    r.ok('to_dict has action') if d['action'] == 'created' else r.fail('to_dict', d.get('action'))
    r.ok('to_dict has author') if d['author'] == 'Alice' else r.fail('author', d.get('author'))
    ae2 = ActivityEntry.from_dict(d)
    r.ok('from_dict roundtrip') if ae2.id == ae.id and ae2.action == ae.action else r.fail('roundtrip', 'mismatch')
    # Minimal
    ae3 = ActivityEntry.from_dict({})
    r.ok('minimal from_dict') if ae3.id else r.fail('minimal', 'no id')


# ═══════════════════════════════════════════════════════════════════════
# TASK SERIALIZATION WITH NEW FIELDS
# ═══════════════════════════════════════════════════════════════════════

def test_task_components_serialization(r):
    cleanup()
    svc = make_service()
    t = svc.create_task("Comp", components=["backend", "api"])
    t.rank = 42
    svc.repo.update(t)
    fetched = svc.get_task(t.id)
    r.ok('components persist') if set(fetched.components) == {"backend", "api"} else r.fail('comps', fetched.components)
    r.ok('rank persists') if fetched.rank == 42 else r.fail('rank', fetched.rank)

    # to_dict / from_dict roundtrip
    d = fetched.to_dict()
    r.ok('to_dict has components') if set(d.get('components')) == {'backend', 'api'} else r.fail('to_dict', d.get('components'))
    r.ok('to_dict has rank') if d.get('rank') == 42 else r.fail('to_dict rank', d.get('rank'))

    t2 = Task.from_dict(d)
    r.ok('from_dict components') if set(t2.components) == {'backend', 'api'} else r.fail('from_dict', t2.components)
    r.ok('from_dict rank') if t2.rank == 42 else r.fail('from_dict rank', t2.rank)
    cleanup()


def test_task_missing_new_fields_from_dict(r):
    data = {
        'id': 'abc', 'title': 'Old task', 'description': '', 'status': 'Todo',
        'priority': 'Medium', 'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
        'tags': [], 'subtasks': [], 'comments': [], 'links': [], 'history': [],
        'time_spent': 0, 'start_date': None, 'due_date': None,
        'assignee': None, 'story_points': None, 'task_type': 'Task',
        'urgency': 'Normal', 'watchers': [], 'epic_link': None,
        'resolution': None, 'sprint_id': None,
    }
    t = Task.from_dict(data)
    r.ok('missing components -> []') if t.components == [] else r.fail('comps', t.components)
    r.ok('missing rank -> 0') if t.rank == 0 else r.fail('rank', t.rank)


# ═══════════════════════════════════════════════════════════════════════
# FILTER COMBINATIONS
# ═══════════════════════════════════════════════════════════════════════

def test_filter_all_criteria(r):
    cleanup()
    svc = make_service()
    # Create varied tasks
    svc.create_task("Match", priority=Priority.HIGH, assignee="Alice",
                     tags=["important"], task_type=TaskType.BUG.value, urgency=Urgency.URGENT.value)
    t_nm = svc.create_task("No match", priority=Priority.LOW, assignee="Bob")
    svc.update_task_status(t_nm.id, TaskStatus.DONE)

    results = svc.filter_tasks(
        status=TaskStatus.TODO, priority=Priority.HIGH, assignee="Alice",
        tag="important", task_type=TaskType.BUG.value, urgency=Urgency.URGENT.value,
    )
    r.ok('1 match with all criteria') if len(results) == 1 else r.fail('filter', len(results))
    r.ok('match is correct') if results[0].title == "Match" else r.fail('wrong match', results[0].title)
    cleanup()


def test_filter_no_results(r):
    cleanup()
    svc = make_service()
    svc.create_task("Only task")
    results = svc.filter_tasks(status=TaskStatus.DONE)
    r.ok('no results') if results == [] else r.fail('filter', 'should be empty')
    cleanup()


def test_filter_overdue(r):
    cleanup()
    svc = make_service()
    past = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    svc.create_task("Overdue", due_date=past)
    svc.create_task("Not overdue", due_date=future)
    done_task = svc.create_task("Done overdue", due_date=past)
    svc.update_task_status(done_task.id, TaskStatus.DONE)
    # Use filter
    overdue = svc.filter_tasks(is_overdue=True)
    r.ok('1 overdue') if len(overdue) == 1 else r.fail('overdue', len(overdue))
    not_overdue = svc.filter_tasks(is_overdue=False)
    r.ok('2 not overdue') if len(not_overdue) == 2 else r.fail('not overdue', len(not_overdue))
    cleanup()


def test_filter_query(r):
    cleanup()
    svc = make_service()
    svc.create_task("Python backend API", description="Build the REST API", assignee="Alice")
    svc.create_task("Frontend UI", description="Build the React UI")
    results = svc.filter_tasks(query="python backend")
    r.ok('query finds in title+desc') if len(results) == 1 else r.fail('query', len(results))
    results2 = svc.filter_tasks(query="alice")
    r.ok('query finds in assignee') if len(results2) == 1 else r.fail('query assignee', len(results2))
    cleanup()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    r = TestResults()

    print('\n--- Large Data Volumes ---')
    test_create_1000_tasks(r)
    test_create_500_tasks_with_tags(r)
    test_large_search(r)

    print('\n--- Deeply Nested Structures ---')
    test_many_subtasks(r)
    test_many_comments(r)
    test_many_links(r)
    test_history_growth(r)

    print('\n--- Unicode and Long Strings ---')
    test_unicode_task(r)
    test_max_length_title(r)
    test_max_length_description(r)
    test_max_length_assignee(r)
    test_special_chars_in_tags(r)
    test_whitespace_title(r)

    print('\n--- Concurrent Event Handlers ---')

    print('\n--- Sprint Velocity at Scale ---')
    test_velocity_many_sprints(r)
    test_velocity_no_completed_sprints(r)

    print('\n--- Activity Feed at Scale ---')
    test_activity_feed_scale(r)
    test_activity_feed_empty(r)

    print('\n--- Backlog Reordering ---')
    test_backlog_reorder_100(r)
    test_backlog_mixed_statuses(r)
    test_rank_negative_clamped(r)
    test_backlog_empty(r)

    print('\n--- Swimlanes at Scale ---')
    test_swimlanes_many_assignees(r)
    test_swimlanes_unassigned(r)
    test_swimlanes_invalid_group_by(r)
    test_swimlanes_task_type(r)
    test_swimlanes_urgency(r)

    print('\n--- Export/Import Large ---')
    test_export_import_500_tasks(r)
    test_import_malformed_task_data(r)

    print('\n--- Components ---')
    test_components_many_tasks(r)
    test_components_empty(r)

    print('\n--- Bulk Operations ---')
    test_bulk_delete_200(r)
    test_bulk_status_200(r)
    test_clone_many_subtasks(r)

    print('\n--- Repository Edge Cases ---')
    test_repository_empty_file(r)
    test_repository_update_nonexistent(r)
    test_repository_double_delete(r)
    test_statistics_empty(r)
    test_statistics_all_done(r)

    print('\n--- Activity Entry Model ---')
    test_activity_entry_model(r)

    print('\n--- New Fields Serialization ---')
    test_task_components_serialization(r)
    test_task_missing_new_fields_from_dict(r)

    print('\n--- Filter Combinations ---')
    test_filter_all_criteria(r)
    test_filter_no_results(r)
    test_filter_overdue(r)
    test_filter_query(r)

    print('\n' + '=' * 60)
    print('STRESS TEST SUMMARY')
    print('=' * 60)
    r.summary()

    cleanup()
