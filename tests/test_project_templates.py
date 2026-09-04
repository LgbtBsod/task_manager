"""Project templates: a reusable multi-task plan, applied as real linked
tasks via the existing epic_link / Task.links(BLOCKED_BY) mechanisms."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import TaskType
from core.repository import TaskRepository
from core.service import TaskService


@pytest.fixture
def svc(tmp_path):
    return TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))


def test_create_project_template_drops_blank_titles(svc):
    tpl = svc.templates.create_project_template(
        "Plan", steps=[{"title": "  Design  "}, {"title": "   "}, {"title": "QA"}])
    assert [s.title for s in tpl.steps] == ["Design", "QA"]


def test_create_project_template_defaults(svc):
    tpl = svc.templates.create_project_template("Plan", steps=[{"title": "A"}])
    assert tpl.steps[0].task_type == "Task"
    assert tpl.steps[0].sequential is True


def test_apply_template_creates_a_task_per_step_in_order(svc):
    tpl = svc.templates.create_project_template(
        "Launch", steps=[{"title": "Design"}, {"title": "Build"}, {"title": "Ship"}])
    tasks = svc.create_tasks_from_project_template(tpl.id)
    assert [t.title for t in tasks] == ["Design", "Build", "Ship"]


def test_sequential_steps_are_chained_blocked_by_the_previous_step(svc):
    tpl = svc.templates.create_project_template(
        "Launch", steps=[{"title": "Design"}, {"title": "Build"}, {"title": "Ship"}])
    design, build, ship = svc.create_tasks_from_project_template(tpl.id)

    assert design.links == []                                  # nothing precedes it
    assert svc.is_blocked(design) is False
    assert [t.id for t in svc.blocking_tasks(build)] == [design.id]
    assert [t.id for t in svc.blocking_tasks(ship)] == [build.id]


def test_non_sequential_step_starts_unblocked(svc):
    tpl = svc.templates.create_project_template(
        "Launch", steps=[{"title": "Design"},
                         {"title": "Docs", "sequential": False},
                         {"title": "Build"}])
    design, docs, build = svc.create_tasks_from_project_template(tpl.id)
    assert svc.is_blocked(docs) is False        # marked non-sequential
    assert svc.is_blocked(build) is True        # still chains off Design (the prior step)


def test_epic_title_creates_an_epic_and_links_every_step(svc):
    tpl = svc.templates.create_project_template("Launch", steps=[{"title": "A"}, {"title": "B"}])
    tasks = svc.create_tasks_from_project_template(tpl.id, epic_title="Launch v2")
    epics = [t for t in svc.get_all_tasks() if t.task_type == TaskType.EPIC.value]
    assert len(epics) == 1
    assert all(t.epic_link == epics[0].id for t in tasks)


def test_no_epic_title_creates_no_epic(svc):
    tpl = svc.templates.create_project_template("Launch", steps=[{"title": "A"}])
    tasks = svc.create_tasks_from_project_template(tpl.id)
    assert tasks[0].epic_link is None
    assert not any(t.task_type == TaskType.EPIC.value for t in svc.get_all_tasks())


def test_apply_unknown_template_raises(svc):
    with pytest.raises(ValueError):
        svc.create_tasks_from_project_template("nope")


def test_apply_empty_template_returns_empty_list(svc):
    tpl = svc.templates.create_project_template("Empty", steps=[])
    assert svc.create_tasks_from_project_template(tpl.id) == []


def test_project_templates_are_listed_and_deletable(svc):
    a = svc.templates.create_project_template("A", steps=[{"title": "x"}])
    svc.templates.create_project_template("B", steps=[{"title": "y"}])
    assert {t.name for t in svc.templates.get_all_project_templates()} == {"A", "B"}
    assert svc.templates.delete_project_template(a.id) is True
    assert {t.name for t in svc.templates.get_all_project_templates()} == {"B"}


def test_project_templates_survive_reload(svc, tmp_path):
    svc.templates.create_project_template(
        "Launch", steps=[{"title": "Design"}, {"title": "Build", "sequential": False}])
    fresh = TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))
    tpls = fresh.templates.get_all_project_templates()
    assert len(tpls) == 1
    assert [(s.title, s.sequential) for s in tpls[0].steps] == \
        [("Design", True), ("Build", False)]


def test_bulk_dialog_module_unaffected_by_project_template_import():
    # cheap import-clean guard, mirrors the other GUI-module smoke tests
    from gui_flet.project_template_dialog import show_project_templates_dialog
    assert callable(show_project_templates_dialog)
