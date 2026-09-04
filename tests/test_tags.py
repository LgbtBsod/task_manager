"""Tag registry: catalog CRUD, rename/delete rewrites, migration, analytics."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import TaskStatus
from core.repository import TaskRepository
from core.service import TaskService


@pytest.fixture
def svc(tmp_path):
    return TaskService(repository=TaskRepository(db_path=str(tmp_path / "tasks.json")))


def test_create_tag_normalises_and_is_idempotent(svc):
    a = svc.tags.create_tag("  Frontend ")
    assert a.name == "frontend"
    b = svc.tags.create_tag("FRONTEND")
    assert b.id == a.id                       # same entry, not a duplicate
    assert len(svc.list_tags()) == 1


def test_create_tag_rejects_blank(svc):
    with pytest.raises(ValueError):
        svc.tags.create_tag("   ")


def test_sync_from_tasks_backfills_registry(svc):
    svc.create_task("A", tags=["frontend", "UI5"])
    svc.create_task("B", tags=["frontend", "backend"])
    added = svc.tags.sync_from_tasks()
    assert added == 3
    assert {t.name for t in svc.list_tags()} == {"frontend", "ui5", "backend"}
    # idempotent
    assert svc.tags.sync_from_tasks() == 0
    # distinct auto-colours
    assert len({t.color for t in svc.list_tags()}) == 3


def test_rename_tag_rewrites_every_task(svc):
    svc.create_task("A", tags=["frontend"])
    svc.create_task("B", tags=["frontend", "backend"])
    svc.tags.sync_from_tasks()
    fe = svc.tags.get_tag_by_name("frontend")
    svc.tags.update_tag(fe.id, name="web")
    assert sorted(sorted(t.tags) for t in svc.get_all_tasks()) == [["backend", "web"], ["web"]]
    assert svc.tags.get_tag_by_name("frontend") is None
    assert svc.tags.get_tag_by_name("web") is not None


def test_rename_onto_existing_name_raises(svc):
    svc.tags.create_tag("a")
    b = svc.tags.create_tag("b")
    with pytest.raises(ValueError):
        svc.tags.update_tag(b.id, name="a")


def test_delete_tag_strips_it_from_tasks(svc):
    svc.create_task("A", tags=["frontend", "backend"])
    svc.tags.sync_from_tasks()
    be = svc.tags.get_tag_by_name("backend")
    assert svc.tags.delete_tag(be.id) is True
    assert svc.get_all_tasks()[0].tags == ["frontend"]
    assert svc.tags.get_tag_by_name("backend") is None


def test_recolor_tag(svc):
    t = svc.tags.create_tag("x", color="#123456")
    svc.tags.update_tag(t.id, color="not-a-hex")      # ignored
    assert svc.tags.get_tag("x" and t.id).color == "#123456"
    svc.tags.update_tag(t.id, color="#ABCDEF")
    assert svc.tags.get_tag(t.id).color == "#abcdef"


def test_tag_breakdown_counts_and_orders(svc):
    svc.create_task("A", tags=["frontend"])
    b = svc.create_task("B", tags=["frontend", "backend"])
    svc.tags.sync_from_tasks()
    svc.update_task(b.id, status=TaskStatus.DONE)
    rows = svc.tag_breakdown()
    assert rows[0]["name"] == "frontend" and rows[0]["count"] == 2 and rows[0]["done"] == 1
    assert rows[1]["name"] == "backend" and rows[1]["count"] == 1


def test_tags_survive_export_import(svc, tmp_path):
    svc.tags.create_tag("frontend", color="#111111")
    dump = svc.repo.export_all()
    assert any(t["name"] == "frontend" for t in dump["tags"])

    fresh = TaskService(repository=TaskRepository(db_path=str(tmp_path / "other.json")))
    fresh.repo.import_all(dump)
    assert fresh.tags.get_tag_by_name("frontend").color == "#111111"
