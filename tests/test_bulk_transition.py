"""Bulk status transitions by tag (b8): matching, moving, history, edge cases."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import TaskStatus
from core.repository import TaskRepository
from core.service import TaskService

TODO, PROG, DONE = TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE


@pytest.fixture
def svc(tmp_path):
    return TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))


def test_moves_matching_tag_and_source_status(svc):
    a = svc.create_task("A", tags=["front"])
    b = svc.create_task("B", tags=["front"])
    svc.create_task("C", tags=["back"])
    assert svc.bulk_transition_by_tag(["front"], [TODO], PROG) == 2
    assert svc.get_task(a.id).status == PROG
    assert svc.get_task(b.id).status == PROG
    assert svc.get_all_tasks()[2].status == TODO


def test_multi_tag_is_or(svc):
    svc.create_task("A", tags=["front"])
    svc.create_task("B", tags=["ui5"])
    c = svc.create_task("C", tags=["back"])
    assert svc.bulk_transition_by_tag(["front", "ui5"], [TODO], PROG) == 2
    assert svc.get_task(c.id).status == TODO


def test_match_all_requires_every_tag(svc):
    a = svc.create_task("A", tags=["front", "ui5"])
    b = svc.create_task("B", tags=["front"])
    assert svc.bulk_transition_by_tag(["front", "ui5"], [TODO], PROG, match_all=True) == 1
    assert svc.get_task(a.id).status == PROG
    assert svc.get_task(b.id).status == TODO


def test_source_status_filter_excludes_others(svc):
    a = svc.create_task("A", tags=["front"])
    b = svc.create_task("B", tags=["front"])
    svc.update_task_status(b.id, DONE)
    assert svc.bulk_transition_by_tag(["front"], [TODO], PROG) == 1
    assert svc.get_task(a.id).status == PROG
    assert svc.get_task(b.id).status == DONE


def test_multi_source_status(svc):
    a = svc.create_task("A", tags=["front"])
    b = svc.create_task("B", tags=["front"])
    c = svc.create_task("C", tags=["front"])
    svc.update_task_status(b.id, PROG)
    svc.update_task_status(c.id, DONE)
    assert svc.bulk_transition_by_tag(["front"], [TODO, PROG], DONE) == 2
    assert all(t.status == DONE for t in svc.get_all_tasks())
    assert a.id in {t.id for t in svc.get_all_tasks() if t.status == DONE}


def test_already_in_target_is_skipped(svc):
    a = svc.create_task("A", tags=["front"])
    b = svc.create_task("B", tags=["front"])
    svc.update_task_status(b.id, PROG)
    assert svc.bulk_transition_by_tag(["front"], [TODO, PROG], PROG) == 1
    history_b = svc.get_task_history(b.id)
    status_entries = [h for h in history_b if h["field_name"] == "status"]
    assert len(status_entries) == 1                 # only the earlier TODO->PROG move


def test_target_equals_single_source_is_noop(svc):
    a = svc.create_task("A", tags=["front"])
    assert svc.bulk_transition_by_tag(["front"], [TODO], TODO) == 0
    assert svc.get_task_history(a.id) == []


def test_empty_tag_list_returns_zero(svc):
    a = svc.create_task("A", tags=["front"])
    assert svc.bulk_transition_by_tag([], [TODO], DONE) == 0
    assert svc.get_task(a.id).status == TODO


def test_empty_source_status_returns_zero(svc):
    a = svc.create_task("A", tags=["front"])
    assert svc.bulk_transition_by_tag(["front"], [], DONE) == 0
    assert svc.get_task(a.id).status == TODO


def test_unknown_tag_returns_zero(svc):
    svc.create_task("A", tags=["front"])
    assert svc.bulk_transition_by_tag(["nope"], [TODO], DONE) == 0


def test_tag_match_is_case_insensitive(svc):
    svc.create_task("A", tags=["Frontend"])   # stored lower-cased
    assert svc.bulk_transition_by_tag(["FRONTEND"], [TODO], PROG) == 1


def test_accepts_raw_string_statuses(svc):
    svc.create_task("A", tags=["front"])
    assert svc.bulk_transition_by_tag(["front"], ["Todo"], "In Progress") == 1


def test_history_entry_written_per_move(svc):
    a = svc.create_task("A", tags=["front"])
    svc.bulk_transition_by_tag(["front"], [TODO], PROG)
    history = svc.get_task_history(a.id)
    assert any(h["field_name"] == "status" and h["old_value"] == "Todo"
               and h["new_value"] == "In Progress" for h in history)


def test_candidates_is_read_only_and_matches_apply(svc):
    a = svc.create_task("A", tags=["front"])
    svc.create_task("B", tags=["front"])
    c = svc.create_task("C", tags=["front"])
    svc.update_task_status(c.id, DONE)

    cands = svc.bulk_transition_candidates(["front"], [TODO], PROG)
    assert len(cands) == 2
    assert svc.get_task(a.id).status == TODO           # preview didn't mutate
    assert svc.get_task_history(a.id) == []

    assert svc.bulk_transition_by_tag(["front"], [TODO], PROG) == 2


def test_changes_persist_across_reload(svc, tmp_path):
    a = svc.create_task("A", tags=["front"])
    svc.bulk_transition_by_tag(["front"], [TODO], PROG)

    fresh = TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))
    assert fresh.get_task(a.id).status == PROG


def test_bulk_strings_exist_and_format():
    from core.strings import UI
    assert "5" in UI.BULK_PREVIEW.format(n=5)
    assert "7" in UI.BULK_DONE.format(n=7)
    assert UI.BULK_APPLY and UI.BULK_TITLE and UI.BULK_TOOLTIP and UI.BULK_HINT


def test_bulk_dialog_module_imports_clean():
    from gui_flet.bulk_dialog import show_bulk_dialog
    assert callable(show_bulk_dialog)
