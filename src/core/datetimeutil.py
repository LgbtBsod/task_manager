"""Flexible date / date-time parsing for task fields.

`start_date` and `due_date` are stored as strings and may be either a plain
date ("2026-09-18") or a date with time ("2026-09-18 14:30" / ISO
"2026-09-18T14:30"). Everything that reads those fields goes through here.
"""
from datetime import date, datetime
from typing import Optional

_DATE_FMT = "%Y-%m-%d"


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse a task date / date-time string ("2026-09-18", "… 14:30",
    ISO "…T14:30[:ss]"). Returns None if empty or unparseable.

    Any timezone offset is dropped: task datetimes are compared against a
    naive ``datetime.now()`` throughout, so an aware value here would raise
    ``TypeError`` on the first ``<`` comparison.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=None)
    except ValueError:
        return None


def to_date(value: Optional[str]) -> Optional[date]:
    """Parse to a plain ``date`` (drops any time component). None if invalid."""
    dt = parse_dt(value)
    return dt.date() if dt else None


def has_time(value: Optional[str]) -> bool:
    """True if the string carries a time component."""
    if not value:
        return False
    v = value.strip()
    return (" " in v or "T" in v) and parse_dt(v) is not None


def date_part(value: Optional[str]) -> Optional[str]:
    """Return just the 'YYYY-MM-DD' part, or None."""
    dt = parse_dt(value)
    return dt.strftime(_DATE_FMT) if dt else None


def normalize(date_str: str, time_str: str = "") -> Optional[str]:
    """Combine a picked date + optional 'HH:MM' into a stored string.

    Returns None for an empty/invalid date.
    """
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()
    if not date_str:
        return None
    d = parse_dt(date_str)
    if d is None:
        return None
    base = d.strftime(_DATE_FMT)
    if not time_str:
        return base
    # accept "9:5", "09:05", "0905"
    t = time_str.replace(".", ":")
    if ":" not in t and t.isdigit() and len(t) in (3, 4):
        t = f"{t[:-2]}:{t[-2:]}"
    try:
        parsed = datetime.strptime(t, "%H:%M")
    except ValueError:
        try:
            parsed = datetime.strptime(t, "%H:%M:%S")
        except ValueError:
            return base
    return f"{base} {parsed.strftime('%H:%M')}"


def display(value: Optional[str]) -> str:
    """Human-friendly rendering: '18.09.2026' or '18.09.2026 14:30'."""
    dt = parse_dt(value)
    if dt is None:
        return value or ""
    if has_time(value):
        return dt.strftime("%d.%m.%Y %H:%M")
    return dt.strftime("%d.%m.%Y")
