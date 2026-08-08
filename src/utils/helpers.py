"""
Task Manager - Utils Module
Helper functions and utilities
Python 3.14+ Compatible

Note: Using standard library instead of external date/holiday libraries when possible (DRTTW)
- datetime for date operations
- workalendar only as optional enhancement for Russian holidays
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List, Any

try:
    from workalendar.europe import Russia
    _calendar = Russia()
except ImportError:
    _calendar = None


def validate_date(date_str: str) -> bool:
    """Validate date format YYYY-MM-DD.
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid format or empty/None, False otherwise
    """
    match date_str:
        case "":
            return True  # Empty is valid (optional field)
        case None:
            return True
        case date_val:
            try:
                datetime.strptime(date_val, "%Y-%m-%d")
                return True
            except ValueError:
                return False


def format_time_spent(hours: float) -> str:
    """Format time spent in human-readable form.
    
    Args:
        hours: Time spent in hours
        
    Returns:
        Formatted string (e.g., "2ч 30м", "1ч", "45м")
    """
    match hours:
        case h if h <= 0:
            return "0ч"
        case _:
            h_int = int(hours)
            m = int((hours - h_int) * 60)
            
            match (h_int, m):
                case (0, _):
                    return f"{m}м"
                case (_, 0):
                    return f"{h_int}ч"
                case _:
                    return f"{h_int}ч {m}м"


def get_month_range(year: int, month: int) -> Tuple[str, str]:
    """Get first and last day of a month.
    
    Args:
        year: Year (e.g., 2024)
        month: Month (1-12)
        
    Returns:
        Tuple of (first_day, last_day) in YYYY-MM-DD format
    """
    match month:
        case 12:
            next_month = datetime(year + 1, 1, 1)
        case _:
            next_month = datetime(year, month + 1, 1)
    
    last_day = next_month - timedelta(days=1)
    return (
        datetime(year, month, 1).strftime("%Y-%m-%d"),
        last_day.strftime("%Y-%m-%d")
    )


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date from string.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        datetime object or None if parsing fails
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def get_tasks_for_month(tasks: List, year: int, month: int) -> List:
    """Filter tasks that overlap with specified month.
    
    Args:
        tasks: List of Task objects
        year: Year to filter by
        month: Month to filter by (1-12)
        
    Returns:
        List of tasks that overlap with the month
    """
    start, end = get_month_range(year, month)
    result = []
    month_start = parse_date(start)
    month_end = parse_date(end)
    
    for task in tasks:
        task_start = parse_date(task.get_gantt_start())
        task_end = parse_date(task.get_gantt_end())
        
        # Check overlap with month
        match (task_start, task_end):
            case (None, _) | (_, None):
                continue
            case (ts, te) if month_end >= ts and te >= month_start:
                result.append(task)
            case _:
                continue
    
    return result


def get_working_days(start_date: str, end_date: str) -> int:
    """
    Calculate working days between two dates.
    Uses workalendar library for Russian holidays if available.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Number of working days (excludes weekends and Russian holidays)
    """
    match (start_date, end_date):
        case ("", _) | (_, "") | (None, _) | (_, None):
            return 0
    
    start = parse_date(start_date)
    end = parse_date(end_date)
    
    match (start, end):
        case (None, _) | (_, None):
            return 0
    
    if start > end:
        start, end = end, start
    
    if _calendar:
        return _calendar.get_working_days_delta(start.date(), end.date())
    else:
        # Fallback: simple count without holidays (DRTTW - stdlib only)
        delta = (end - start).days + 1
        weekends = 0
        current = start
        while current <= end:
            if current.weekday() >= 5:  # Saturday or Sunday
                weekends += 1
            current += timedelta(days=1)
        return max(0, delta - weekends)


def is_weekend(date_str: str) -> bool:
    """Check if a date is a weekend or holiday.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        
    Returns:
        True if date is weekend or Russian holiday
    """
    date = parse_date(date_str)
    
    match date:
        case None:
            return False
        case d if _calendar:
            return not _calendar.is_working_day(d.date())
        case d:
            return d.weekday() >= 5


def add_working_days(start_date: str, days: int) -> str:
    """
    Add working days to a date.
    Returns new date in YYYY-MM-DD format.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        days: Number of working days to add (can be negative)
        
    Returns:
        New date string in YYYY-MM-DD format
    """
    match (start_date, days):
        case ("", _) | (None, _) | (_, 0):
            return start_date
    
    date = parse_date(start_date)
    
    match date:
        case None:
            return start_date
    
    if _calendar:
        result_date = _calendar.add_working_days(date.date(), days)
        return result_date.strftime("%Y-%m-%d")
    else:
        # Fallback: simple count without holidays (DRTTW - stdlib only)
        current = date
        added = 0
        step = 1 if days > 0 else -1
        days_abs = abs(days)
        
        while added < days_abs:
            current += timedelta(days=step)
            if current.weekday() < 5:  # Only weekdays
                added += 1
        
        return current.strftime("%Y-%m-%d")


def calculate_task_duration_business_days(start_date: str, end_date: str) -> Dict[str, int]:
    """
    Calculate task duration in working days with detailed breakdown.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Dictionary with:
        - working_days: Number of working days
        - calendar_days: Total calendar days
        - weekends: Number of weekend days
        - holidays: Number of holidays (if workalendar available)
    """
    empty_result: Dict[str, int] = {
        'working_days': 0,
        'calendar_days': 0,
        'weekends': 0,
        'holidays': 0
    }
    
    match (start_date, end_date):
        case ("", _) | (_, "") | (None, _) | (_, None):
            return empty_result
    
    start = parse_date(start_date)
    end = parse_date(end_date)
    
    match (start, end):
        case (None, _) | (_, None):
            return empty_result
    
    if start > end:
        start, end = end, start
    
    calendar_days = (end - start).days + 1
    working_days = get_working_days(start_date, end_date)
    
    weekends = 0
    holidays = 0
    current = start
    while current <= end:
        if _calendar:
            if not _calendar.is_working_day(current.date()):
                match current.weekday():
                    case wd if wd >= 5:
                        weekends += 1
                    case _:
                        holidays += 1
        else:
            if current.weekday() >= 5:
                weekends += 1
        current += timedelta(days=1)
    
    return {
        'working_days': working_days,
        'calendar_days': calendar_days,
        'weekends': weekends,
        'holidays': holidays
    }


__all__ = [
    'validate_date', 
    'format_time_spent', 
    'get_month_range', 
    'parse_date', 
    'get_tasks_for_month',
    'get_working_days',
    'is_weekend',
    'add_working_days',
    'calculate_task_duration_business_days'
]
