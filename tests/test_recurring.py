"""Recurring-task generation — was entirely untested and broken
(next_due_date always returned a future date, so nothing ever generated)."""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import RecurringTask
from core.repository import TaskRepository
from core.service import TaskService


def _svc() -> TaskService:
    return TaskService(TaskRepository(db_path=tempfile.mktemp(suffix=".json")))


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def test_due_occurrence_weekly_overdue():
    rec = RecurringTask(title="report", frequency="weekly", base_due_date=_days_ago(10))
    today = datetime.now().strftime("%Y-%m-%d")
    occ = rec.due_occurrence(today, None)
    assert occ is not None
    assert occ <= today                       # it's actually due
    assert occ == _days_ago(3)                # latest due occurrence (10d ago + 1 week)


def test_due_occurrence_none_when_base_in_future():
    rec = RecurringTask(title="x", frequency="daily",
                        base_due_date=(datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"))
    assert rec.due_occurrence(datetime.now().strftime("%Y-%m-%d"), None) is None


def test_due_occurrence_skips_already_generated():
    rec = RecurringTask(title="x", frequency="weekly", base_due_date=_days_ago(20))
    today = datetime.now().strftime("%Y-%m-%d")
    first = rec.due_occurrence(today, None)     # latest due: 20d ago + 2 weeks = 6d ago
    assert first == _days_ago(6)
    assert rec.due_occurrence(today, first) is None   # nothing newer is due yet


def test_generate_creates_one_task_and_advances():
    s = _svc()
    s.create_recurring_task("Еженедельный отчёт", frequency="weekly",
                            base_due_date=_days_ago(10))
    made = s.generate_recurring_tasks()
    assert len(made) == 1
    t = made[0]
    assert t.title == "Еженедельный отчёт"
    assert t.recurring_task_id is not None
    assert t.due_date == _days_ago(3)          # latest missed occurrence

    # second call the same day must NOT duplicate
    assert s.generate_recurring_tasks() == []
    assert len(s.get_all_tasks()) == 1


def test_generate_ignores_inactive():
    s = _svc()
    rec = s.create_recurring_task("paused", frequency="daily", base_due_date=_days_ago(5))
    s.toggle_recurring_active(rec.id)          # -> inactive
    assert s.generate_recurring_tasks() == []


def test_invalid_frequency_rejected():
    s = _svc()
    with pytest.raises(ValueError):
        s.create_recurring_task("x", frequency="hourly", base_due_date=_days_ago(1))


def test_monthly_recurrence_uses_calendar_months_not_fixed_30_days():
    """A month-end base date must step by real calendar months (Jan 31 ->
    Feb 28, clamped for the shorter month), not drift forward the way a
    fixed timedelta(days=30) step would (Jan 31 -> Mar 2 -> Apr 1 -> ...)."""
    rec = RecurringTask(title="rent", frequency="monthly", base_due_date="2026-01-31")
    assert rec.next_due_date(after_date="2026-02-15") == "2026-02-28"
    assert rec.next_due_date(after_date="2026-03-01") == "2026-03-28"


def test_quarterly_recurrence_uses_calendar_months():
    rec = RecurringTask(title="review", frequency="quarterly", base_due_date="2026-01-31")
    assert rec.next_due_date(after_date="2026-03-01") == "2026-04-30"


def test_recurring_dialog_module_imports_clean():
    from gui_flet.recurring_dialog import show_recurring_dialog
    assert callable(show_recurring_dialog)


class _FakeSettings:
    """Minimal stand-in for AppSettings — DeadlineWatcher only calls .get()."""
    def __init__(self, **values):
        self._values = values

    def get(self, key):
        return self._values[key]


def _watcher(svc):
    from gui_flet.deadline_watcher import DeadlineWatcher
    refreshes = {"n": 0}
    watcher = DeadlineWatcher(
        service=svc, settings=_FakeSettings(notifications_enabled=False, notify_check_seconds=60),
        page=None, on_refresh=lambda: refreshes.__setitem__("n", refreshes["n"] + 1))
    return watcher, refreshes


def test_watcher_generates_due_recurring_tasks_and_refreshes():
    s = _svc()
    s.create_recurring_task("Еженедельный отчёт", frequency="weekly", base_due_date=_days_ago(10))
    watcher, refreshes = _watcher(s)
    watcher._generate_recurring()
    assert len(s.get_all_tasks()) == 1
    assert refreshes["n"] == 1


def test_watcher_does_not_refresh_when_nothing_is_due():
    s = _svc()
    watcher, refreshes = _watcher(s)   # no recurring definitions at all
    watcher._generate_recurring()
    assert refreshes["n"] == 0
