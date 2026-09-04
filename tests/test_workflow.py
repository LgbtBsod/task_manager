"""Workflow: blocked-derived state (Task.links + LinkType.BLOCKED_BY) and
opt-in auto-advance (unblock a dependent, auto-close a finished Epic) —
built entirely on the pre-existing link/epic_link graphs, no new fields."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import LinkType, TaskStatus, TaskType
from core.repository import TaskRepository
from core.service import TaskService

TODO, PROG, DONE = TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE


@pytest.fixture
def svc(tmp_path):
    return TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))


def _block(svc, task, on):
    svc.add_task_link(task.id, on.id, LinkType.BLOCKED_BY.value)


def test_not_blocked_with_no_links(svc):
    a = svc.create_task("A")
    assert svc.is_blocked(a) is False
    assert svc.blocking_tasks(a) == []


def test_blocked_by_an_unfinished_task(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    _block(svc, a, b)
    a = svc.get_task(a.id)
    assert svc.is_blocked(a) is True
    assert [t.id for t in svc.blocking_tasks(a)] == [b.id]


def test_not_blocked_once_the_blocker_is_done(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    _block(svc, a, b)
    svc.update_task_status(b.id, DONE)
    a = svc.get_task(a.id)
    assert svc.is_blocked(a) is False


def test_dependents_of_finds_tasks_blocked_by_it(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    c = svc.create_task("C")
    _block(svc, a, c)
    _block(svc, b, c)
    deps = {t.id for t in svc.dependents_of(c.id)}
    assert deps == {a.id, b.id}


def test_plan_after_done_lists_only_todo_unblocked_dependents(svc):
    a = svc.create_task("A")               # TODO, will become unblocked
    b = svc.create_task("B")               # already IN_PROGRESS -> not a candidate
    c = svc.create_task("C")               # blocked by someone else too -> still blocked
    other_blocker = svc.create_task("D")
    blocker = svc.create_task("BLOCKER")
    _block(svc, a, blocker)
    _block(svc, b, blocker)
    svc.update_task_status(b.id, PROG)
    _block(svc, c, blocker)
    _block(svc, c, other_blocker)

    blocker_done = svc.update_task_status(blocker.id, DONE)
    plan = svc.plan_after_done(blocker_done)
    assert [t.id for t in plan["unblocked"]] == [a.id]


def test_auto_start_unblocked_moves_dependent_to_in_progress(svc):
    a = svc.create_task("A")
    blocker = svc.create_task("BLOCKER")
    _block(svc, a, blocker)

    svc.update_task_status(blocker.id, DONE, auto_start_unblocked=True)
    assert svc.get_task(a.id).status == PROG
    history = [h for h in svc.get_task_history(a.id) if h["field_name"] == "status"]
    assert history[-1]["new_value"] == "In Progress"


def test_without_the_flag_dependent_is_not_auto_started(svc):
    a = svc.create_task("A")
    blocker = svc.create_task("BLOCKER")
    _block(svc, a, blocker)

    svc.update_task_status(blocker.id, DONE)   # no auto_start_unblocked
    assert svc.get_task(a.id).status == TODO


def test_auto_close_epic_when_all_children_done(svc):
    epic = svc.create_task("EPIC", task_type=TaskType.EPIC.value)
    a = svc.create_task("A", epic_link=epic.id)
    b = svc.create_task("B", epic_link=epic.id)
    svc.update_task_status(a.id, DONE, auto_close_epic=True)
    assert svc.get_task(epic.id).status == TODO       # b still open
    svc.update_task_status(b.id, DONE, auto_close_epic=True)
    assert svc.get_task(epic.id).status == DONE


def test_auto_close_epic_is_a_noop_without_the_flag(svc):
    epic = svc.create_task("EPIC", task_type=TaskType.EPIC.value)
    a = svc.create_task("A", epic_link=epic.id)
    svc.update_task_status(a.id, DONE)   # no auto_close_epic
    assert svc.get_task(epic.id).status == TODO


def test_auto_close_epic_leaves_an_already_done_epic_alone(svc):
    epic = svc.create_task("EPIC", task_type=TaskType.EPIC.value)
    a = svc.create_task("A", epic_link=epic.id)
    svc.update_task_status(epic.id, DONE)
    before = svc.get_task_history(epic.id)
    svc.update_task_status(a.id, DONE, auto_close_epic=True)
    assert svc.get_task_history(epic.id) == before     # no redundant status entry


def test_bulk_status_change_threads_workflow_flags(svc):
    a = svc.create_task("A")
    blocker = svc.create_task("BLOCKER")
    _block(svc, a, blocker)
    svc.bulk_status_change([blocker.id], DONE, auto_start_unblocked=True)
    assert svc.get_task(a.id).status == PROG


def test_bulk_transition_by_tag_threads_workflow_flags(svc):
    a = svc.create_task("A", tags=["x"])
    blocker = svc.create_task("BLOCKER", tags=["x"])
    _block(svc, a, blocker)
    svc.update_task_status(blocker.id, PROG)
    svc.bulk_transition_by_tag(["x"], [PROG], DONE, auto_start_unblocked=True)
    assert svc.get_task(a.id).status == PROG


def test_set_on_hold_toggles_and_records_history(svc):
    a = svc.create_task("A")
    assert a.on_hold is False
    svc.set_on_hold(a.id, True)
    a = svc.get_task(a.id)
    assert a.on_hold is True
    history = [h for h in a.history if h.field_name == "on_hold"]
    assert len(history) == 1


def test_set_on_hold_is_a_noop_when_unchanged(svc):
    a = svc.create_task("A")
    svc.set_on_hold(a.id, False)   # already False
    a = svc.get_task(a.id)
    assert a.history == []


def test_set_epic_link_is_a_noop_when_unchanged(svc):
    epic = svc.create_task("EPIC", task_type=TaskType.EPIC.value)
    child = svc.create_task("CHILD", epic_link=epic.id)
    svc.set_epic_link(child.id, epic.id)   # already this epic
    child = svc.get_task(child.id)
    assert [h for h in child.history if h.field_name == "epic_link"] == []


def test_direct_blocked_by_cycle_is_rejected(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    _block(svc, a, b)   # A blocked by B
    with pytest.raises(ValueError, match="cycle"):
        _block(svc, b, a)   # B blocked by A would close the loop
    # the rejected link must not have been partially applied
    b = svc.get_task(b.id)
    assert svc.blocking_tasks(b) == []


def test_transitive_blocked_by_cycle_is_rejected(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    c = svc.create_task("C")
    _block(svc, a, b)   # A blocked by B
    _block(svc, b, c)   # B blocked by C
    with pytest.raises(ValueError, match="cycle"):
        _block(svc, c, a)   # C blocked by A would close a 3-node loop


def test_non_cyclic_blocked_by_chain_is_allowed(svc):
    a = svc.create_task("A")
    b = svc.create_task("B")
    c = svc.create_task("C")
    _block(svc, a, b)
    _block(svc, b, c)
    a = svc.get_task(a.id)
    assert {t.id for t in svc.blocking_tasks(a)} == {b.id}


def test_epic_link_cycle_is_rejected(svc):
    epic_a = svc.create_task("Epic A", task_type=TaskType.EPIC.value)
    epic_b = svc.create_task("Epic B", task_type=TaskType.EPIC.value)
    svc.set_epic_link(epic_b.id, epic_a.id)   # B nested under A
    with pytest.raises(ValueError, match="cycle"):
        svc.set_epic_link(epic_a.id, epic_b.id)   # A under B would close the loop
    epic_a = svc.get_task(epic_a.id)
    assert epic_a.epic_link is None


def test_epic_link_self_nesting_is_rejected(svc):
    epic = svc.create_task("Epic", task_type=TaskType.EPIC.value)
    with pytest.raises(ValueError, match="cycle"):
        svc.set_epic_link(epic.id, epic.id)
