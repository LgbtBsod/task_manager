"""datetimeutil — the single date/date-time parser for task fields.

Previously untested; covered here since parse_dt moved to
datetime.fromisoformat (the tzinfo strip is load-bearing).
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.datetimeutil import parse_dt, to_date, has_time, date_part, normalize, display


@pytest.mark.parametrize("text,expected", [
    ("2026-09-18", datetime(2026, 9, 18)),
    ("2026-09-18 14:30", datetime(2026, 9, 18, 14, 30)),
    ("2026-09-18T14:30", datetime(2026, 9, 18, 14, 30)),
    ("2026-09-18 14:30:45", datetime(2026, 9, 18, 14, 30, 45)),
    ("  2026-09-18 14:30  ", datetime(2026, 9, 18, 14, 30)),
])
def test_parse_dt_accepts_stored_shapes(text, expected):
    assert parse_dt(text) == expected


@pytest.mark.parametrize("bad", ["", None, "not a date", "2026-13-01", "18/09/2026"])
def test_parse_dt_rejects(bad):
    assert parse_dt(bad) is None


def test_parse_dt_strips_timezone():
    got = parse_dt("2026-09-18T14:30:00+03:00")
    assert got == datetime(2026, 9, 18, 14, 30)
    assert got.tzinfo is None                         # must stay naive
    # and the result is comparable with a naive now() (the real call site)
    assert isinstance(got < datetime.now(), bool)


def test_to_date_drops_time():
    assert to_date("2026-09-18 14:30").isoformat() == "2026-09-18"
    assert to_date("bad") is None


def test_has_time():
    assert has_time("2026-09-18 14:30") is True
    assert has_time("2026-09-18T14:30") is True
    assert has_time("2026-09-18") is False
    assert has_time("") is False


def test_date_part():
    assert date_part("2026-09-18T14:30") == "2026-09-18"
    assert date_part("garbage") is None


def test_normalize_combines_date_and_time():
    assert normalize("2026-09-18") == "2026-09-18"
    assert normalize("2026-09-18", "14:30") == "2026-09-18 14:30"
    assert normalize("2026-09-18", "9:5") == "2026-09-18 09:05"   # single digits
    assert normalize("2026-09-18", "0905") == "2026-09-18 09:05"  # compact
    assert normalize("", "14:30") is None
    assert normalize("2026-09-18", "nonsense") == "2026-09-18"    # bad time -> date only


def test_display():
    assert display("2026-09-18") == "18.09.2026"
    assert display("2026-09-18 14:30") == "18.09.2026 14:30"
    assert display("") == ""
    assert display("keep as-is") == "keep as-is"
