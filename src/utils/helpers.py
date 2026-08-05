"""
Task Manager - Utils Module
Helper functions and utilities
Python 3.14+ Compatible
"""
import re
from datetime import datetime, timedelta

try:
    from workalendar.europe import Russia
    _calendar = Russia()
except ImportError:
    _calendar = None


def validate_date(date_str: str) -> bool:
    """Проверка формата даты YYYY-MM-DD."""
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
        # Validate actual date (e.g., Feb 30 is invalid)
        datetime(year, month, day)
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


def get_month_range(year: int, month: int) -> tuple[str, str]:
    """Получить первый и последний день месяца."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return datetime(year, month, 1).strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")


def parse_date(date_str: str) -> datetime | None:
    """Распарсить дату из строки."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def get_tasks_for_month(tasks: list, year: int, month: int) -> list:
    """Фильтрация задач для указанного месяца."""
    start, end = get_month_range(year, month)
    result = []
    for task in tasks:
        task_start = parse_date(task.get_gantt_start())
        task_end = parse_date(task.get_gantt_end())
        month_start = parse_date(start)
        month_end = parse_date(end)
        
        # Проверяем пересечение с месяцем
        if task_start and month_end >= task_start and (task_end or month_start) >= month_start:
            result.append(task)
    return result


def get_working_days(start_date: str, end_date: str) -> int:
    """
    Рассчитать количество рабочих дней между двумя датами.
    Использует библиотеку workalendar для учета выходных и праздников России.
    """
    if not start_date or not end_date:
        return 0
    
    start = parse_date(start_date)
    end = parse_date(end_date)
    
    if not start or not end:
        return 0
    
    if start > end:
        start, end = end, start
    
    if _calendar:
        return _calendar.get_working_days_delta(start.date(), end.date())
    else:
        # Fallback: простой подсчет без праздников
        delta = (end - start).days + 1
        weekends = 0
        current = start
        while current <= end:
            if current.weekday() >= 5:  # Суббота или Воскресенье
                weekends += 1
            current += timedelta(days=1)
        return max(0, delta - weekends)


def is_weekend(date_str: str) -> bool:
    """Проверить, является ли дата выходным днем."""
    date = parse_date(date_str)
    if not date:
        return False
    
    if _calendar:
        return not _calendar.is_working_day(date.date())
    else:
        return date.weekday() >= 5


def add_working_days(start_date: str, days: int) -> str:
    """
    Добавить указанное количество рабочих дней к дате.
    Возвращает новую дату в формате YYYY-MM-DD.
    """
    if not start_date or days == 0:
        return start_date
    
    date = parse_date(start_date)
    if not date:
        return start_date
    
    if _calendar:
        result_date = _calendar.add_working_days(date.date(), days)
        return result_date.strftime("%Y-%m-%d")
    else:
        # Fallback: простой подсчет без праздников
        current = date
        added = 0
        step = 1 if days > 0 else -1
        days = abs(days)
        
        while added < days:
            current += timedelta(days=step)
            if current.weekday() < 5:  # Только будни
                added += 1
        
        return current.strftime("%Y-%m-%d")


def calculate_task_duration_business_days(start_date: str, end_date: str) -> dict:
    """
    Рассчитать длительность задачи в рабочих днях с детальной информацией.
    Возвращает словарь с полной статистикой.
    """
    if not start_date or not end_date:
        return {'working_days': 0, 'calendar_days': 0, 'weekends': 0, 'holidays': 0}
    
    start = parse_date(start_date)
    end = parse_date(end_date)
    
    if not start or not end:
        return {'working_days': 0, 'calendar_days': 0, 'weekends': 0, 'holidays': 0}
    
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
                if current.weekday() >= 5:
                    weekends += 1
                else:
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
