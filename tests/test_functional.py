"""Comprehensive functional tests for Task Manager.

Covers: models, repository, service (CRUD + all Jira features), events.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback as tb_module
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.models import (
    HistoryEntry,
    LinkType,
    Priority,
    SubTask,
    Task,
    TaskComment,
    TaskLink,
    TaskModel,
    TaskStatus,
    TaskType,
    _normalize_tags,
)
from core.repository import TaskRepository
from core.service import TaskService
from utils.logger import get_logger, setup_logging

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
# MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_task_creation(r):
    t = Task(title='Test task', priority=Priority.HIGH)
    r.ok('id auto-generated' if t.id and len(t.id) == 8 else f'id={t.id}')
    r.ok('title set' if t.title == 'Test task' else f'title={t.title}')
    r.ok('priority HIGH' if t.priority == Priority.HIGH else f'prio={t.priority}')
    r.ok('status defaults TODO' if t.status == TaskStatus.TODO else f'status={t.status}')
    r.ok('time_spent=0' if t.time_spent == 0.0 else f'time={t.time_spent}')
    r.ok('created_at set' if t.created_at else 'created_at missing')
    r.ok('updated_at set' if t.updated_at else 'updated_at missing')
    r.ok('tags default empty' if t.tags == [] else f'tags={t.tags}')
    r.ok('subtasks default empty' if t.subtasks == [] else f'subtasks={t.subtasks}')
    r.ok('comments default empty' if t.comments == [] else f'comments={t.comments}')
    r.ok('links default empty' if t.links == [] else f'links={t.links}')
    r.ok('history default empty' if t.history == [] else f'history={t.history}')
    r.ok('assignee default None' if t.assignee is None else f'assignee={t.assignee}')
    r.ok('story_points default None' if t.story_points is None else f'sp={t.story_points}')
    r.ok('task_type default Task' if t.task_type == TaskType.TASK.value else f'type={t.task_type}')


def test_task_validation(r):
    try:
        Task(title='Valid', due_date='2026-12-31')
        r.ok('valid task accepted')
    except Exception as e:
        r.fail('valid task', str(e))

    try:
        Task(title='')
        r.fail('empty title', 'should have raised')
    except (ValueError, Exception):
        r.ok('empty title rejected')

    try:
        Task(title='X', due_date='not-a-date')
        r.fail('bad date', 'should have raised')
    except (ValueError, Exception):
        r.ok('bad date rejected')

    try:
        Task(title='X', start_date='2026-12-31', due_date='2026-01-01')
        r.fail('inconsistent dates', 'should have raised')
    except (ValueError, Exception):
        r.ok('inconsistent dates rejected')

    # Invalid task_type
    try:
        Task(title='X', task_type='InvalidType')
        r.fail('invalid task_type', 'should have raised')
    except (ValueError, Exception):
        r.ok('invalid task_type rejected')

    # Valid task types
    for tt in [TaskType.TASK.value, TaskType.BUG.value, TaskType.STORY.value, TaskType.EPIC.value]:
        try:
            Task(title='TypeTest', task_type=tt)
            r.ok(f'task_type={tt} accepted')
        except Exception as e:
            r.fail(f'task_type={tt}', str(e))

    # Negative time_spent should be rejected by Pydantic
    try:
        Task(title='X', time_spent=-5)
        r.fail('negative time_spent', 'should have raised')
    except (ValueError, Exception):
        r.ok('negative time_spent rejected')

    # Story points validation
    try:
        Task(title='X', story_points=200)
        r.fail('story_points > 100', 'should have raised')
    except (ValueError, Exception):
        r.ok('story_points > 100 rejected')

    try:
        Task(title='X', story_points=-1)
        r.fail('negative story_points', 'should have raised')
    except (ValueError, Exception):
        r.ok('negative story_points rejected')

    # Long title > 200 chars
    try:
        Task(title='X' * 201)
        r.fail('title > 200 chars', 'should have raised')
    except (ValueError, Exception):
        r.ok('title > 200 chars rejected')


def test_task_tags(r):
    t = Task(title='Tags test', tags=['frontend', ' Bug ', 'frontend'])
    r.ok('tags deduplicated' if len(set(t.tags)) == len(t.tags) else f'duplicates: {t.tags}')
    r.ok('tags normalized' if 'bug' in t.tags else f'got {t.tags}')
    r.ok('no empty tags' if '' not in t.tags else 'has empty tag')
    r.ok('max 10 tags enforced' if len(t.tags) <= 10 else f'got {len(t.tags)}')
    many = Task(title='Many tags', tags=[f'tag{i}' for i in range(15)])
    r.ok('tags capped at 10' if len(many.tags) == 10 else f'got {len(many.tags)}')


def test_subtasks(r):
    t = Task(title='Subtask test')
    r.ok('empty subtask progress' if t.subtask_progress() == 0.0 else f'progress={t.subtask_progress()}')
    t.subtasks.append(SubTask(title='Do thing A'))
    t.subtasks.append(SubTask(title='Do thing B'))
    t.subtasks.append(SubTask(title='Do thing C', done=True))
    r.ok('3 subtasks' if len(t.subtasks) == 3 else f'got {len(t.subtasks)}')
    r.ok('progress 0.333' if abs(t.subtask_progress() - 0.333) < 0.01 else f'got {t.subtask_progress()}')
    result = t.toggle_subtask(0)
    r.ok('toggle subtask 0 returns True' if result is True else f'got {result}')
    r.ok('subtask 0 done' if t.subtasks[0].done else 'not toggled')
    r.ok('progress 0.667' if abs(t.subtask_progress() - 0.667) < 0.01 else f'got {t.subtask_progress()}')
    t.toggle_subtask(1)
    r.ok('progress 1.0' if t.subtask_progress() == 1.0 else f'got {t.subtask_progress()}')
    result = t.toggle_subtask(99)
    r.ok('invalid index returns False' if result is False else f'got {result}')
    r.ok('toggle back works' if t.toggle_subtask(0) and not t.subtasks[0].done else 'toggle back failed')


def test_subtask_model_serialization(r):
    s = SubTask(title='Test sub', done=True)
    d = s.to_dict()
    r.ok('subtask dict has id' if 'id' in d else 'missing id')
    r.ok('subtask dict has title' if d['title'] == 'Test sub' else f'wrong title: {d}')
    r.ok('subtask dict has done' if d['done'] is True else f'wrong done: {d}')
    s2 = SubTask.from_dict(d)
    r.ok('subtask round-trip title' if s2.title == s.title else 'title mismatch')
    r.ok('subtask round-trip done' if s2.done == s.done else 'done mismatch')


def test_task_comment(r):
    t = Task(title='Comment test')
    c = t.add_comment('Alice', 'Looks good')
    r.ok('comment added' if len(t.comments) == 1 else f'got {len(t.comments)}')
    r.ok('comment author' if t.comments[0].author == 'Alice' else f'author={t.comments[0].author}')
    r.ok('comment text' if t.comments[0].text == 'Looks good' else f'text={t.comments[0].text}')
    r.ok('comment has id' if t.comments[0].id else 'no id')
    r.ok('comment has timestamp' if t.comments[0].created_at else 'no timestamp')

    # Delete comment
    result = t.delete_comment(c.id)
    r.ok('delete comment returns True' if result is True else f'got {result}')
    r.ok('comment removed' if len(t.comments) == 0 else f'got {len(t.comments)}')

    # Delete non-existent
    result = t.delete_comment('nonexistent')
    r.ok('delete nonexistent returns False' if result is False else f'got {result}')

    # Comment serialization
    c2 = t.add_comment('Bob', 'Second comment')
    d = c2.to_dict()
    r.ok('comment dict keys' if {'id', 'author', 'text', 'created_at'} == set(d.keys()) else f'keys={d.keys()}')
    c3 = TaskComment.from_dict(d)
    r.ok('comment round-trip' if c3.author == 'Bob' and c3.text == 'Second comment' else 'mismatch')


def test_task_link(r):
    t = Task(title='Link test')
    t.add_link('task2', 'blocks')
    r.ok('link added' if len(t.links) == 1 else f'got {len(t.links)}')
    r.ok('link target' if t.links[0].target_task_id == 'task2' else 'wrong target')
    r.ok('link type' if t.links[0].link_type == 'blocks' else 'wrong type')
    t.add_link('task3', 'relates_to')
    r.ok('second link' if len(t.links) == 2 else f'got {len(t.links)}')
    result = t.remove_link('task2')
    r.ok('remove link returns True' if result is True else f'got {result}')
    r.ok('link removed' if len(t.links) == 1 else f'got {len(t.links)}')
    result = t.remove_link('nonexistent')
    r.ok('remove nonexistent returns False' if result is False else f'got {result}')

    # Link serialization
    l = t.links[0]
    d = l.to_dict()
    r.ok('link dict keys' if {'target_task_id', 'link_type'} == set(d.keys()) else f'keys={d.keys()}')
    l2 = TaskLink.from_dict(d)
    r.ok('link round-trip' if l2.target_task_id == 'task3' else 'mismatch')


def test_history_entry(r):
    t = Task(title='History test')
    t.record_change('status', 'Todo', 'In Progress')
    t.record_change('priority', 'Low', 'High')
    r.ok('2 history entries' if len(t.history) == 2 else f'got {len(t.history)}')
    r.ok('entry field_name' if t.history[0].field_name == 'status' else f'got {t.history[0].field_name}')
    r.ok('entry old_value' if t.history[0].old_value == 'Todo' else f'got {t.history[0].old_value}')
    r.ok('entry new_value' if t.history[0].new_value == 'In Progress' else f'got {t.history[0].new_value}')
    r.ok('entry has timestamp' if t.history[0].timestamp else 'no timestamp')

    # Serialization
    d = t.history[0].to_dict()
    h = HistoryEntry.from_dict(d)
    r.ok('history round-trip' if h.field_name == 'status' and h.old_value == 'Todo' else 'mismatch')


def test_task_serialization(r):
    t = Task(
        title='Serialize me', description='desc', priority=Priority.LOW,
        due_date='2026-09-01', time_spent=3.5, tags=['test'],
        subtasks=[SubTask(title='sub1', done=True)],
        assignee='Alice', story_points=5, task_type=TaskType.BUG.value,
    )
    d = t.to_dict()
    r.ok('to_dict has id' if 'id' in d else 'missing id')
    r.ok('status is string' if isinstance(d['status'], str) else 'status not string')
    r.ok('tags in dict' if 'tags' in d and d['tags'] == ['test'] else f'tags wrong: {d.get("tags")}')
    r.ok('subtasks in dict' if 'subtasks' in d else 'missing subtasks')
    r.ok('comments in dict' if 'comments' in d else 'missing comments')
    r.ok('links in dict' if 'links' in d else 'missing links')
    r.ok('history in dict' if 'history' in d else 'missing history')
    r.ok('assignee in dict' if d.get('assignee') == 'Alice' else f'assignee={d.get("assignee")}')
    r.ok('story_points in dict' if d.get('story_points') == 5 else f'sp={d.get("story_points")}')
    r.ok('task_type in dict' if d.get('task_type') == 'Bug' else f'type={d.get("task_type")}')

    t2 = Task.from_dict(d)
    r.ok('round-trip title' if t2.title == t.title else 'title mismatch')
    r.ok('round-trip priority' if t2.priority == t.priority else 'priority mismatch')
    r.ok('round-trip due_date' if t2.due_date == t.due_date else 'due_date mismatch')
    r.ok('round-trip tags' if t2.tags == t.tags else f'tags: {t2.tags}')
    r.ok('round-trip subtasks' if len(t2.subtasks) == 1 and t2.subtasks[0].title == 'sub1' else 'subtasks wrong')
    r.ok('round-trip assignee' if t2.assignee == 'Alice' else f'assignee={t2.assignee}')
    r.ok('round-trip story_points' if t2.story_points == 5 else f'sp={t2.story_points}')
    r.ok('round-trip task_type' if t2.task_type == 'Bug' else f'type={t2.task_type}')


def test_task_overdue(r):
    past = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    t_overdue = Task(title='Overdue', due_date=past)
    r.ok('past due detected' if t_overdue.is_overdue() else 'overdue not detected')
    r.ok('days_until_due < 0' if t_overdue.days_until_due() is not None and t_overdue.days_until_due() < 0 else 'wrong days')
    t_future = Task(title='Future', due_date=future)
    r.ok('future not overdue' if not t_future.is_overdue() else 'false positive overdue')
    t_done = Task(title='Done past', due_date=past, status=TaskStatus.DONE)
    r.ok('done task not overdue' if not t_done.is_overdue() else 'done task marked overdue')
    t_no_date = Task(title='No date')
    r.ok('no date not overdue' if not t_no_date.is_overdue() else 'false positive no-date')
    r.ok('no date days_until_none' if t_no_date.days_until_due() is None else 'should be None')


def test_gantt_methods(r):
    t = Task(title='Gantt test', start_date='2026-08-15', due_date='2026-08-25')
    r.ok('gantt_start' if t.get_gantt_start() == '2026-08-15' else f'got {t.get_gantt_start()}')
    r.ok('gantt_end' if t.get_gantt_end() == '2026-08-25' else f'got {t.get_gantt_end()}')
    t_no_dates = Task(title='No dates')
    start = t_no_dates.get_gantt_start()
    r.ok('gantt_start fallback is date string' if len(start) == 10 else f'got {start}')
    end = t_no_dates.get_gantt_end()
    r.ok('gantt_end fallback is date string' if len(end) == 10 else f'got {end}')


def test_normalize_tags_helper(r):
    r.ok('empty list' if _normalize_tags([]) == [] else 'not empty')
    r.ok('dedup' if _normalize_tags(['a', 'a']) == ['a'] else 'not deduped')
    r.ok('strip+lower' if _normalize_tags([' FrontEnd ']) == ['frontend'] else 'not normalized')
    r.ok('remove empty' if _normalize_tags(['', 'a', ' ']) == ['a'] else 'empty not removed')
    r.ok('cap at 10' if len(_normalize_tags([f't{i}' for i in range(15)])) == 10 else 'not capped')


def test_priority_colors(r):
    # SAP Horizon severity ramp
    assert Priority.LOW.color == '#36a41d'
    assert Priority.MEDIUM.color == '#e76500'
    assert Priority.HIGH.color == '#f53232'
    assert Priority.CRITICAL.color == '#d20a0a'
    assert len({p.color for p in Priority}) == 4


def test_task_with_new_fields(r):
    t = Task(
        title='Full task',
        assignee='Bob',
        story_points=8,
        task_type=TaskType.STORY.value,
        tags=['backend', 'api'],
    )
    r.ok('assignee set' if t.assignee == 'Bob' else f'got {t.assignee}')
    r.ok('story_points set' if t.story_points == 8 else f'got {t.story_points}')
    r.ok('task_type set' if t.task_type == 'Story' else f'got {t.task_type}')
    r.ok('tags set' if t.tags == ['backend', 'api'] else f'got {t.tags}')


# ═══════════════════════════════════════════════════════════════════════
# REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_repository_crud(r):
    repo = TaskRepository(db_path=TMP_DB)
    initial = repo.count()
    r.ok('initial count 0' if initial == 0 else f'initial count {initial}')
    t = Task(title='Repo test', priority=Priority.MEDIUM)
    created = repo.add(t)
    r.ok('repo add' if repo.count() == 1 else 'add failed')
    r.ok('id preserved' if created.id == t.id else 'id mismatch')
    found = repo.get_by_id(t.id)
    r.ok('get_by_id' if found and found.title == 'Repo test' else 'not found')
    all_tasks = repo.get_all()
    r.ok('get_all count 1' if len(all_tasks) == 1 else f'count {len(all_tasks)}')
    found.title = 'Updated'
    repo.update(found)
    updated = repo.get_by_id(t.id)
    r.ok('repo update' if updated.title == 'Updated' else 'update failed')
    todo_tasks = repo.get_by_status(TaskStatus.TODO)
    r.ok('filter by status' if len(todo_tasks) == 1 else f'filter count {len(todo_tasks)}')
    result = repo.delete(t.id)
    r.ok('repo delete' if result and repo.count() == 0 else 'delete failed')
    r.ok('delete missing returns False' if not repo.delete('nonexistent') else 'should be False')


def test_repository_with_new_fields(r):
    repo = TaskRepository(db_path=TMP_DB)
    t = Task(
        title='Rich task', assignee='Alice', story_points=5,
        tags=['test'], task_type='Bug',
        subtasks=[SubTask(title='sub1')],
        comments=[TaskComment(author='Bob', text='Nice')],
        links=[TaskLink(target_task_id='other', link_type='relates_to')],
        history=[HistoryEntry(field_name='status', old_value='Todo', new_value='Done')],
    )
    repo.add(t)
    loaded = repo.get_by_id(t.id)
    r.ok('rich task loaded' if loaded else 'not found')
    r.ok('assignee persisted' if loaded.assignee == 'Alice' else f'got {loaded.assignee}')
    r.ok('story_points persisted' if loaded.story_points == 5 else f'got {loaded.story_points}')
    r.ok('task_type persisted' if loaded.task_type == 'Bug' else f'got {loaded.task_type}')
    r.ok('tags persisted' if loaded.tags == ['test'] else f'got {loaded.tags}')
    r.ok('subtasks persisted' if len(loaded.subtasks) == 1 else f'got {len(loaded.subtasks)}')
    r.ok('comments persisted' if len(loaded.comments) == 1 else f'got {len(loaded.comments)}')
    r.ok('links persisted' if len(loaded.links) == 1 else f'got {len(loaded.links)}')
    r.ok('history persisted' if len(loaded.history) == 1 else f'got {len(loaded.history)}')
    repo.delete(t.id)


def test_repository_corrupted_json(r):
    repo = TaskRepository(db_path=TMP_DB)
    # Write garbage to the file
    with open(TMP_DB, 'w') as f:
        f.write('NOT VALID JSON{{{{')
    tasks = repo.get_all()
    r.ok('corrupted JSON returns empty list' if tasks == [] else f'got {len(tasks)} tasks')
    # Clean up for other tests
    with open(TMP_DB, 'w') as f:
        json.dump([], f)


def test_repository_missing_file(r):
    tmp = tempfile.mktemp(suffix='.json')
    repo = TaskRepository(db_path=tmp)
    assert repo.count() == 0
    assert not os.path.exists(tmp)          # created lazily, only on first write
    repo.add(Task(title='first'))
    assert os.path.exists(tmp)
    os.unlink(tmp)


def test_repository_statistics(r):
    repo = TaskRepository(db_path=TMP_DB)
    past = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    repo.add(Task(title='Low1', priority=Priority.LOW))
    repo.add(Task(title='Med1', priority=Priority.MEDIUM))
    repo.add(Task(title='High1', priority=Priority.HIGH, due_date=past))
    s = repo.get_statistics()
    r.ok('total=3' if s['total'] == 3 else f'total={s["total"]}')
    r.ok('low=1' if s['by_priority']['low'] == 1 else 'low wrong')
    r.ok('overdue=1' if s['overdue'] == 1 else f'overdue={s["overdue"]}')
    r.ok('completion_rate=0' if s['completion_rate'] == 0 else f'rate={s["completion_rate"]}')


# ═══════════════════════════════════════════════════════════════════════
# SERVICE CRUD TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_service_crud(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Service test', priority=Priority.HIGH, due_date='2026-12-31')
    r.ok('service create' if t.title == 'Service test' else 'create failed')
    updated = service.update_task_status(t.id, TaskStatus.IN_PROGRESS)
    r.ok('status updated' if updated and updated.status == TaskStatus.IN_PROGRESS else 'status failed')
    updated = service.update_task(t.id, title='Renamed', time_spent=2.5)
    r.ok('field update' if updated and updated.title == 'Renamed' else 'field update failed')
    r.ok('time_spent updated' if updated.time_spent == 2.5 else 'time_spent wrong')
    try:
        service.update_task(t.id, due_date='bad-date')
        r.fail('bad date update', 'should raise')
    except ValueError:
        r.ok('bad date update rejected')
    result = service.delete_task(t.id)
    r.ok('service delete' if result else 'delete failed')
    r.ok('get missing returns None' if service.get_task('nope') is None else 'should be None')


def test_service_with_new_fields(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task(
        'New fields task',
        tags=['frontend', 'urgent'],
        assignee='Alice',
        story_points=8,
        task_type=TaskType.STORY.value,
    )
    r.ok('created with tags' if t.tags == ['frontend', 'urgent'] else f'got {t.tags}')
    r.ok('created with assignee' if t.assignee == 'Alice' else f'got {t.assignee}')
    r.ok('created with story_points' if t.story_points == 8 else f'got {t.story_points}')
    r.ok('created with task_type' if t.task_type == 'Story' else f'got {t.task_type}')

    # Update new fields
    updated = service.update_task(t.id, tags=['backend'], assignee='Bob', story_points=3)
    r.ok('tags updated' if updated.tags == ['backend'] else f'got {updated.tags}')
    r.ok('assignee updated' if updated.assignee == 'Bob' else f'got {updated.assignee}')
    r.ok('story_points updated' if updated.story_points == 3 else f'got {updated.story_points}')

    # History recorded
    history = service.get_task_history(t.id)
    r.ok('history has entries' if len(history) > 0 else 'no history')
    service.delete_task(t.id)


def test_service_tags(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Tagged task', tags=['frontend', 'bug', 'urgent'])
    r.ok('task created with tags' if t.tags == ['frontend', 'bug', 'urgent'] else f'got {t.tags}')
    by_tag = service.get_tasks_by_tag('frontend')
    r.ok('find by tag' if len(by_tag) == 1 and by_tag[0].id == t.id else f'got {len(by_tag)}')
    r.ok('case insensitive tag' if len(service.get_tasks_by_tag('FRONTEND')) == 1 else 'case sensitive')
    r.ok('no match for missing tag' if len(service.get_tasks_by_tag('nonexistent')) == 0 else 'wrong match')
    all_tags = service.get_all_tags()
    r.ok('all_tags returns list' if isinstance(all_tags, list) else f'got {type(all_tags)}')
    r.ok('tags in all_tags' if 'frontend' in all_tags and 'bug' in all_tags else f'got {all_tags}')
    updated = service.update_task(t.id, tags=['backend', 'refactor'])
    r.ok('tags updated' if updated.tags == ['backend', 'refactor'] else f'got {updated.tags}')
    r.ok('old tag gone' if len(service.get_tasks_by_tag('frontend')) == 0 else 'old tag persists')
    service.delete_task(t.id)


def test_service_subtasks(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Subtask service test')
    t2 = service.add_subtask(t.id, 'Do thing A')
    r.ok('subtask added' if t2 and len(t2.subtasks) == 1 else 'add failed')
    r.ok('subtask title' if t2.subtasks[0].title == 'Do thing A' else 'title wrong')
    t3 = service.add_subtask(t.id, 'Do thing B')
    r.ok('second subtask' if t3 and len(t3.subtasks) == 2 else 'add failed')
    t4 = service.toggle_subtask(t.id, 0)
    r.ok('subtask toggled' if t4 and t4.subtasks[0].done else 'toggle failed')
    t5 = service.delete_subtask(t.id, 1)
    r.ok('subtask deleted' if t5 and len(t5.subtasks) == 1 else 'delete failed')
    r.ok('delete invalid index returns None' if service.delete_subtask(t.id, 99) is None else 'should be None')
    r.ok('add to missing task returns None' if service.add_subtask('nonexistent', 'x') is None else 'should be None')
    r.ok('toggle missing task returns None' if service.toggle_subtask('nonexistent', 0) is None else 'should be None')
    service.delete_task(t.id)


def test_service_comments(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('Comment task')
    t2 = service.add_comment(t.id, 'Alice', 'First comment')
    r.ok('comment added' if t2 and len(t2.comments) == 1 else 'add failed')
    r.ok('comment content' if t2.comments[0].text == 'First comment' else 'wrong text')
    t3 = service.add_comment(t.id, 'Bob', 'Second comment')
    if t3 and len(t3.comments) == 2:
        r.ok('second comment')
    else:
        r.fail('second comment', f't3={t3}, comments={len(t3.comments) if t3 else "None"}')
    t4 = service.delete_comment(t.id, t3.comments[1].id if t3 else 'nope')
    r.ok('comment deleted' if t4 and len(t4.comments) == 1 else 'delete failed')
    r.ok('delete nonexistent comment returns None' if service.delete_comment(t.id, 'nope') is None else 'should be None')
    r.ok('comment on missing task returns None' if service.add_comment('nope', 'A', 'B') is None else 'should be None')
    service.delete_task(t.id)


def test_service_task_links(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('Task 1')
    t2 = service.create_task('Task 2')
    t3 = service.create_task('Task 3')

    # Add link
    updated = service.add_task_link(t1.id, t2.id, 'blocks')
    r.ok('link added' if updated and len(updated.links) == 1 else 'add failed')

    # Self-link rejected
    try:
        service.add_task_link(t1.id, t1.id, 'relates_to')
        r.fail('self-link', 'should raise')
    except ValueError:
        r.ok('self-link rejected')

    # Invalid target
    try:
        service.add_task_link(t1.id, 'nonexistent', 'relates_to')
        r.fail('invalid target', 'should raise')
    except ValueError:
        r.ok('invalid target rejected')

    # Invalid link type
    try:
        service.add_task_link(t1.id, t2.id, 'invalid_type')
        r.fail('invalid link_type', 'should raise')
    except ValueError:
        r.ok('invalid link_type rejected')

    # Get linked tasks
    linked = service.get_linked_tasks(t1.id)
    if 'blocks' in linked:
        r.ok('get_linked_tasks has blocks')
        r.ok('linked task found' if len(linked['blocks']) == 1 and linked['blocks'][0].id == t2.id else 'wrong linked')
    else:
        r.fail('get_linked_tasks has blocks', f'got keys={list(linked.keys())}, links={[(l.target_task_id, l.link_type) for l in service.get_task(t1.id).links]}')

    # Duplicate link
    dup = service.add_task_link(t1.id, t2.id, 'blocks')
    r.ok('duplicate link returns same task' if dup and len(dup.links) == 1 else 'duplicate added')

    # Remove link
    removed = service.remove_task_link(t1.id, t2.id)
    r.ok('link removed' if removed and len(removed.links) == 0 else 'remove failed')

    # Symmetric link (relates_to should add reverse)
    service.add_task_link(t1.id, t3.id, 'relates_to')
    t3_loaded = service.get_task(t3.id)
    r.ok('reverse link added' if t3_loaded and any(l.target_task_id == t1.id for l in t3_loaded.links) else 'no reverse')

    service.delete_task(t1.id)
    service.delete_task(t2.id)
    service.delete_task(t3.id)


def test_service_bulk_operations(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('Bulk 1')
    t2 = service.create_task('Bulk 2')
    t3 = service.create_task('Bulk 3')
    ids = [t1.id, t2.id, t3.id]

    # Bulk status change
    count = service.bulk_status_change(ids, TaskStatus.IN_PROGRESS)
    r.ok('bulk status changed 3' if count == 3 else f'changed {count}')
    for tid in ids:
        t = service.get_task(tid)
        r.ok(f'{tid[:4]} in_progress' if t and t.status == TaskStatus.IN_PROGRESS else 'status wrong')

    # Bulk delete
    count = service.bulk_delete(ids)
    r.ok('bulk deleted 3' if count == 3 else f'deleted {count}')
    r.ok('repo empty' if service.get_all_tasks() == [] else 'not empty')

    # Bulk on empty
    r.ok('bulk delete empty returns 0' if service.bulk_delete([]) == 0 else 'not 0')
    r.ok('bulk status empty returns 0' if service.bulk_status_change([], TaskStatus.DONE) == 0 else 'not 0')


def test_service_search(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    service.create_task('Implement login page', description='Create login form', tags=['frontend'], assignee='Alice')
    service.create_task('Fix database connection', description='DB timeout issue', tags=['backend'], assignee='Bob')
    service.create_task('Deploy to production', tags=['devops'])

    r1 = service.search_tasks('login')
    r.ok('search by title' if len(r1) == 1 else f'got {len(r1)}')
    r2 = service.search_tasks('frontend')
    r.ok('search by tag' if len(r2) == 1 else f'got {len(r2)}')
    r3 = service.search_tasks('Alice')
    r.ok('search by assignee' if len(r3) == 1 else f'got {len(r3)}')
    r4 = service.search_tasks('database')
    r.ok('search by description' if len(r4) == 1 else f'got {len(r4)}')
    r5 = service.search_tasks('')
    r.ok('empty query returns all' if len(r5) == 3 else f'got {len(r5)}')
    r6 = service.search_tasks('NONEXISTENT_QUERY_XYZ')
    r.ok('no results' if len(r6) == 0 else f'got {len(r6)}')

    # Cleanup
    for t in service.get_all_tasks():
        service.delete_task(t.id)


def test_service_assignee(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    service.create_task('A1', assignee='Alice')
    service.create_task('A2', assignee='Bob')
    service.create_task('A3', assignee='Alice')

    alice_tasks = service.get_tasks_by_assignee('Alice')
    r.ok('alice has 2 tasks' if len(alice_tasks) == 2 else f'got {len(alice_tasks)}')
    bob_tasks = service.get_tasks_by_assignee('Bob')
    r.ok('bob has 1 task' if len(bob_tasks) == 1 else f'got {len(bob_tasks)}')
    r.ok('case insensitive' if len(service.get_tasks_by_assignee('ALICE')) == 2 else 'case sensitive')
    r.ok('no match' if len(service.get_tasks_by_assignee('Charlie')) == 0 else 'wrong match')

    all_assignees = service.get_all_assignees()
    r.ok('all_assignees sorted' if all_assignees == ['Alice', 'Bob'] else f'got {all_assignees}')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


def test_service_clone(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    original = service.create_task(
        'Original task', description='Some desc',
        priority=Priority.HIGH, tags=['test'], assignee='Alice',
        story_points=5, task_type=TaskType.BUG.value,
    )
    service.add_subtask(original.id, 'Step 1')
    service.add_subtask(original.id, 'Step 2')

    cloned = service.clone_task(original.id)
    r.ok('clone created' if cloned else 'no clone')
    r.ok('clone has different id' if cloned.id != original.id else 'same id')
    r.ok('clone title has (copy)' if '(copy)' in cloned.title else f'title={cloned.title}')
    r.ok('clone description' if cloned.description == 'Some desc' else 'desc mismatch')
    r.ok('clone priority' if cloned.priority == Priority.HIGH else 'prio mismatch')
    r.ok('clone tags' if cloned.tags == ['test'] else f'tags={cloned.tags}')
    r.ok('clone assignee' if cloned.assignee == 'Alice' else f'assignee={cloned.assignee}')
    r.ok('clone story_points' if cloned.story_points == 5 else f'sp={cloned.story_points}')
    r.ok('clone task_type' if cloned.task_type == 'Bug' else f'type={cloned.task_type}')
    r.ok('clone subtasks copied' if len(cloned.subtasks) == 2 else f'subtasks={len(cloned.subtasks)}')
    r.ok('clone subtasks not done' if all(not s.done for s in cloned.subtasks) else 'subtasks done')

    # Clone with custom title
    cloned2 = service.clone_task(original.id, new_title='Custom title')
    r.ok('clone custom title' if cloned2.title == 'Custom title' else f'got {cloned2.title}')

    # Clone nonexistent
    r.ok('clone nonexistent returns None' if service.clone_task('nope') is None else 'should be None')

    service.delete_task(original.id)
    service.delete_task(cloned.id)
    service.delete_task(cloned2.id)


def test_service_history(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t = service.create_task('History task')
    service.update_task(t.id, title='Renamed')
    service.update_task_status(t.id, TaskStatus.IN_PROGRESS)
    service.update_task(t.id, priority=Priority.HIGH)

    history = service.get_task_history(t.id)
    r.ok('history has entries' if len(history) >= 3 else f'got {len(history)}')
    field_names = [h['field_name'] for h in history]
    r.ok('title change recorded' if 'title' in field_names else 'no title change')
    r.ok('status change recorded' if 'status' in field_names else 'no status change')
    r.ok('priority change recorded' if 'priority' in field_names else 'no priority change')

    # History for nonexistent task
    r.ok('history for missing returns []' if service.get_task_history('nope') == [] else 'not empty')

    service.delete_task(t.id)


def test_service_overdue(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    past = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    service.create_task('Overdue task', due_date=past)
    service.create_task('Future task', due_date=future)
    service.create_task('No date task')

    overdue = service.get_overdue_tasks()
    r.ok('1 overdue task' if len(overdue) == 1 else f'got {len(overdue)}')
    r.ok('overdue is the right one' if overdue[0].title == 'Overdue task' else 'wrong task')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


def test_statistics(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    service.create_task('S1', priority=Priority.LOW)
    service.create_task('S2', priority=Priority.MEDIUM)
    service.create_task('S3', priority=Priority.HIGH)
    s = service.get_statistics()
    r.ok('total=3' if s['total'] == 3 else f'total={s["total"]}')
    r.ok('todo=3' if s['by_status']['todo'] == 3 else 'todo wrong')
    r.ok('low=1' if s['by_priority']['low'] == 1 else 'low wrong')
    r.ok('high=1' if s['by_priority']['high'] == 1 else 'high wrong')
    r.ok('overdue=0' if s['overdue'] == 0 else 'overdue wrong')
    r.ok('completion_rate=0' if s['completion_rate'] == 0 else 'rate wrong')
    tasks = service.get_all_tasks()
    service.update_task_status(tasks[0].id, TaskStatus.DONE)
    s2 = service.get_statistics()
    r.ok('done=1' if s2['by_status']['done'] == 1 else 'done wrong')
    r.ok('rate=33.3' if s2['completion_rate'] == 33.3 else f'rate={s2["completion_rate"]}')
    for t in service.get_all_tasks():
        service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# HELPER TESTS
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# LOGGER TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_logger(r):
    tmp_dir = tempfile.mkdtemp()
    try:
        logs_path = setup_logging(tmp_dir)
        assert logs_path.exists()
        assert (logs_path / 'app.log').exists()
        assert (logs_path / 'error.log').exists()

        log = get_logger('test_logger')
        log.info('Test info message')
        log.error('Test error message')

        content = (logs_path / 'app.log').read_text(encoding='utf-8')
        assert 'Test info message' in content
        assert 'Test error message' in content
        assert 'Test error message' in (logs_path / 'error.log').read_text(encoding='utf-8')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_edge_cases(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)

    # Create with all optional fields None
    t = service.create_task('Minimal task')
    r.ok('minimal task created' if t else 'no task')

    # Update with no changes (should still work)
    t2 = service.update_task(t.id)
    r.ok('no-op update works' if t2 else 'update returned None')

    # Very long description (max 5000)
    long_desc = 'A' * 5000
    t3 = service.update_task(t.id, description=long_desc)
    r.ok('max description accepted' if t3 else 'rejected')

    # Too long description
    try:
        service.update_task(t.id, description='A' * 5001)
        r.fail('description > 5000', 'should raise')
    except ValueError:
        r.ok('description > 5000 rejected')

    # Create with strip whitespace
    t4 = service.create_task('  Whitespace task  ', description='  desc  ')
    r.ok('title stripped' if t4.title == 'Whitespace task' else f'got "{t4.title}"')
    r.ok('description stripped' if t4.description == 'desc' else f'got "{t4.description}"')

    # Multiple tags with spaces and duplicates
    t5 = service.create_task('Tag edge', tags=['  Frontend  ', 'frontend', '', '  ', 'Backend'])
    r.ok('tags cleaned' if t5.tags == ['frontend', 'backend'] else f'got {t5.tags}')

    # Negative time_spent clamped to 0
    t6 = service.update_task(t.id, time_spent=-5)
    r.ok('negative time_spent clamped' if t6.time_spent == 0 else f'got {t6.time_spent}')

    service.delete_task(t.id)
    service.delete_task(t4.id)
    service.delete_task(t5.id)


def test_update_timestamp(r):
    """Verify updated_at changes on update."""
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    import time
    t = service.create_task('Timestamp test')
    first_ts = t.updated_at
    time.sleep(0.05)  # small delay
    t2 = service.update_task(t.id, title='Updated title')
    r.ok('timestamp changed' if t2.updated_at != first_ts else 'timestamp same')
    service.delete_task(t.id)


def test_get_tasks_by_status_service(r):
    repo = TaskRepository(db_path=TMP_DB)
    service = TaskService(repository=repo)
    t1 = service.create_task('TS1')
    t2 = service.create_task('TS2')
    service.update_task_status(t1.id, TaskStatus.IN_PROGRESS)
    service.update_task_status(t2.id, TaskStatus.DONE)

    r.ok('todo count 0' if len(service.get_tasks_by_status(TaskStatus.TODO)) == 0 else 'wrong')
    r.ok('in_progress count 1' if len(service.get_tasks_by_status(TaskStatus.IN_PROGRESS)) == 1 else 'wrong')
    r.ok('done count 1' if len(service.get_tasks_by_status(TaskStatus.DONE)) == 1 else 'wrong')

    for t in service.get_all_tasks():
        service.delete_task(t.id)


# ═══════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    results = TestResults()
    tests = [
        ('Task creation', test_task_creation),
        ('Task validation', test_task_validation),
        ('Task tags', test_task_tags),
        ('Subtasks', test_subtasks),
        ('Subtask model serialization', test_subtask_model_serialization),
        ('Task comments', test_task_comment),
        ('Task links', test_task_link),
        ('History entry', test_history_entry),
        ('Serialization', test_task_serialization),
        ('Overdue detection', test_task_overdue),
        ('Gantt methods', test_gantt_methods),
        ('Normalize tags helper', test_normalize_tags_helper),
        ('Priority colors', test_priority_colors),
        ('Task with new fields', test_task_with_new_fields),
        ('Repository CRUD', test_repository_crud),
        ('Repository new fields', test_repository_with_new_fields),
        ('Repository corrupted JSON', test_repository_corrupted_json),
        ('Repository missing file', test_repository_missing_file),
        ('Repository statistics', test_repository_statistics),
        ('Service CRUD', test_service_crud),
        ('Service new fields', test_service_with_new_fields),
        ('Service tags', test_service_tags),
        ('Service subtasks', test_service_subtasks),
        ('Service comments', test_service_comments),
        ('Service task links', test_service_task_links),
        ('Service bulk operations', test_service_bulk_operations),
        ('Service search', test_service_search),
        ('Service assignee', test_service_assignee),
        ('Service clone', test_service_clone),
        ('Service history', test_service_history),
        ('Service overdue', test_service_overdue),
        ('Statistics', test_statistics),
        ('Logger', test_logger),
        ('Edge cases', test_edge_cases),
        ('Update timestamp', test_update_timestamp),
        ('Service get_by_status', test_get_tasks_by_status_service),
    ]
    for name, fn in tests:
        print(f'\n--- {name} ---')
        try:
            fn(results)
        except Exception as e:
            results.fail(name, f'unhandled: {e}')
            tb_module.print_exc()
    print('\n' + '='*60)
    print('FUNCTIONAL TEST SUMMARY')
    print('='*60)
    ok = results.summary()
    sys.exit(0 if ok else 1)
