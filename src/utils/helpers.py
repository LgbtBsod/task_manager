"""
Task Manager - Utils Module
Helper functions and utilities
"""


def validate_date(date_str: str) -> bool:
    """Проверка формата даты YYYY-MM-DD."""
    import re
    if not date_str:
        return True  # Empty is valid (optional field)
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(pattern, date_str):
        return False
    
    # Check valid date values
    try:
        year, month, day = map(int, date_str.split('-'))
        if month < 1 or month > 12:
            return False
        if day < 1 or day > 31:
            return False
        return True
    except ValueError:
        return False


def format_time_spent(hours: float) -> str:
    """Форматирование затраченного времени."""
    if hours <= 0:
        return "0ч"
    
    h = int(hours)
    m = int((hours - h) * 60)
    
    if h == 0:
        return f"{m}м"
    elif m == 0:
        return f"{h}ч"
    else:
        return f"{h}ч {m}м"


__all__ = ['validate_date', 'format_time_spent']
