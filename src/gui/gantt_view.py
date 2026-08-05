"""
Task Manager - Modern Kanban Board
Gantt Chart View for Timeline Visualization
"""
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta
from typing import Callable, Optional

try:
    from ..core import Task, TaskStatus, Priority, TaskService
    from ..utils.helpers import get_month_range, parse_date, get_tasks_for_month
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))
    from core import Task, TaskStatus, Priority, TaskService
    from utils.helpers import get_month_range, parse_date, get_tasks_for_month


# Colors for Gantt chart
GANTT_COLORS = {
    "bg": "#1a1a1a",
    "card_bg": "#2d2d2d",
    "header_bg": "#3a3a3a",
    "grid_line": "#444444",
    "today_line": "#F44336",
    "task_todo": "#9E9E9E",
    "task_in_progress": "#FF9800",
    "task_done": "#4CAF50",
    "text_primary": "#ffffff",
    "text_secondary": "#aaaaaa",
    "weekend": "#2a2a2a",
}


class GanttChartFrame(ctk.CTkScrollableFrame):
    """Диаграмма Ганта для визуализации задач во времени."""
    
    def __init__(self, parent, service: TaskService, **kwargs):
        super().__init__(parent, fg_color=GANTT_COLORS["bg"], **kwargs)
        self.service = service
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        
        # Day width in pixels
        self.day_width = 40
        self.row_height = 45
        self.header_height = 50
        
        self._setup_controls()
        self._render_gantt()
    
    def _setup_controls(self):
        """Настройка элементов управления."""
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=10)
        
        # Previous month button
        prev_btn = ctk.CTkButton(
            control_frame, text="◀ Пред.", width=100, height=30,
            command=self._prev_month,
            fg_color="#444444", hover_color="#555555"
        )
        prev_btn.pack(side="left", padx=5)
        
        # Current month label
        self.month_label = ctk.CTkLabel(
            control_frame, text="", 
            font=("Arial", 16, "bold"),
            text_color=GANTT_COLORS["text_primary"]
        )
        self.month_label.pack(side="left", padx=20)
        
        # Next month button
        next_btn = ctk.CTkButton(
            control_frame, text="След. ▶", width=100, height=30,
            command=self._next_month,
            fg_color="#444444", hover_color="#555555"
        )
        next_btn.pack(side="left", padx=5)
        
        # Today button
        today_btn = ctk.CTkButton(
            control_frame, text="Сегодня", width=100, height=30,
            command=self._go_to_today,
            fg_color="#2196F3", hover_color="#1976D2"
        )
        today_btn.pack(side="right", padx=5)
        
        # Refresh button
        refresh_btn = ctk.CTkButton(
            control_frame, text="🔄", width=40, height=30,
            command=self._render_gantt,
            fg_color="#444444", hover_color="#555555"
        )
        refresh_btn.pack(side="right", padx=5)
        
        self._update_month_label()
    
    def _update_month_label(self):
        """Обновление метки месяца."""
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        self.month_label.configure(text=f"{month_names[self.current_month - 1]} {self.current_year}")
    
    def _prev_month(self):
        """Переход к предыдущему месяцу."""
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._update_month_label()
        self._render_gantt()
    
    def _next_month(self):
        """Переход к следующему месяцу."""
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._update_month_label()
        self._render_gantt()
    
    def _go_to_today(self):
        """Переход к текущему месяцу."""
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self._update_month_label()
        self._render_gantt()
    
    def _render_gantt(self):
        """Отрисовка диаграммы Ганта."""
        # Clear existing content (except controls)
        for widget in self.winfo_children():
            if isinstance(widget, ctk.CTkFrame) and widget != self.winfo_children()[0]:
                widget.destroy()
        
        # Get month range
        start_date_str, end_date_str = get_month_range(self.current_year, self.current_month)
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        # Get all tasks and filter for this month
        all_tasks = self.service.get_all_tasks()
        month_tasks = get_tasks_for_month(all_tasks, self.current_year, self.current_month)
        
        # Sort tasks by priority (High first) then by start date
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        month_tasks.sort(key=lambda t: (priority_order.get(t.priority, 1), t.get_gantt_start()))
        
        if not month_tasks:
            no_data_label = ctk.CTkLabel(
                self, text="📭 Нет задач в этом месяце",
                font=("Arial", 16), text_color=GANTT_COLORS["text_secondary"]
            )
            no_data_label.pack(pady=50)
            return
        
        # Calculate total days in month
        total_days = (end_date - start_date).days + 1
        chart_width = total_days * self.day_width + 250  # + space for task names
        
        # Main chart container
        chart_container = ctk.CTkFrame(self, fg_color="transparent")
        chart_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header with dates
        self._render_header(chart_container, start_date, total_days)
        
        # Grid with tasks
        self._render_grid(chart_container, month_tasks, start_date, total_days)
    
    def _render_header(self, parent, start_date: datetime, total_days: int):
        """Отрисовка заголовка с датами."""
        header_frame = ctk.CTkFrame(parent, fg_color=GANTT_COLORS["header_bg"], height=self.header_height)
        header_frame.pack(fill="x", padx=0, pady=(0, 5))
        header_frame.pack_propagate(False)
        
        # Task name column header
        name_header = ctk.CTkFrame(header_frame, fg_color=GANTT_COLORS["header_bg"], width=250, height=self.header_height)
        name_header.pack(side="left", fill="y")
        name_header.pack_propagate(False)
        ctk.CTkLabel(
            name_header, text="Задача", font=("Arial", 12, "bold"),
            text_color=GANTT_COLORS["text_primary"]
        ).place(relx=0.5, rely=0.5, anchor="center")
        
        # Date headers
        date_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        date_frame.pack(side="left", fill="both", expand=True)
        
        current_date = start_date
        day_num = 0
        while day_num < total_days:
            col_width = self.day_width
            is_weekend = current_date.weekday() >= 5
            bg_color = GANTT_COLORS["weekend"] if is_weekend else GANTT_COLORS["header_bg"]
            
            day_col = ctk.CTkFrame(date_frame, fg_color=bg_color, width=col_width, height=self.header_height)
            day_col.pack(side="left", fill="y")
            day_col.pack_propagate(False)
            
            # Day number
            day_label = ctk.CTkLabel(
                day_col, text=str(current_date.day),
                font=("Arial", 10, "bold"),
                text_color=GANTT_COLORS["text_secondary"]
            )
            day_label.place(relx=0.5, rely=0.35, anchor="center")
            
            # Weekday short name
            weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            weekday_label = ctk.CTkLabel(
                day_col, text=weekday_names[current_date.weekday()],
                font=("Arial", 8),
                text_color=GANTT_COLORS["text_secondary"]
            )
            weekday_label.place(relx=0.5, rely=0.65, anchor="center")
            
            current_date += timedelta(days=1)
            day_num += 1
    
    def _render_grid(self, parent, tasks: list, start_date: datetime, total_days: int):
        """Отрисовка сетки задач."""
        grid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True)
        
        today = datetime.now().date()
        
        for row_idx, task in enumerate(tasks):
            self._render_task_row(grid_frame, task, start_date, total_days, row_idx, today)
    
    def _render_task_row(self, parent, task: Task, start_date: datetime, total_days: int, row_idx: int, today):
        """Отрисовка строки задачи."""
        row_frame = ctk.CTkFrame(parent, fg_color=GANTT_COLORS["card_bg"], height=self.row_height)
        row_frame.pack(fill="x", pady=1)
        row_frame.pack_propagate(False)
        
        # Task name section
        name_frame = ctk.CTkFrame(row_frame, fg_color="transparent", width=250, height=self.row_height)
        name_frame.pack(side="left", fill="y")
        name_frame.pack_propagate(False)
        
        # Priority indicator
        prio_color = task.priority.color
        prio_dot = ctk.CTkLabel(
            name_frame, text="●", text_color=prio_color,
            font=("Arial", 14, "bold")
        )
        prio_dot.place(x=10, rely=0.5, anchor="w")
        
        # Task title (truncated)
        title_text = task.title[:28] + "..." if len(task.title) > 28 else task.title
        title_label = ctk.CTkLabel(
            name_frame, text=title_text,
            font=("Arial", 11),
            text_color=GANTT_COLORS["text_primary"],
            anchor="w"
        )
        title_label.place(x=30, rely=0.5, anchor="w")
        
        # Status badge
        status_colors = {
            TaskStatus.TODO: GANTT_COLORS["task_todo"],
            TaskStatus.IN_PROGRESS: GANTT_COLORS["task_in_progress"],
            TaskStatus.DONE: GANTT_COLORS["task_done"]
        }
        status_badge = ctk.CTkLabel(
            name_frame, text=task.status.value,
            font=("Arial", 9),
            text_color=status_colors[task.status],
            anchor="e"
        )
        status_badge.place(x=240, rely=0.5, anchor="e")
        
        # Timeline section
        timeline_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        timeline_frame.pack(side="left", fill="both", expand=True)
        
        # Calculate task position
        task_start = parse_date(task.get_gantt_start()) or start_date
        task_end = parse_date(task.get_gantt_end()) or (start_date + timedelta(days=total_days-1))
        
        # Clamp to visible range
        task_start = max(task_start, start_date)
        month_end = start_date + timedelta(days=total_days-1)
        task_end = min(task_end, month_end)
        
        # Calculate offset and width
        offset_days = (task_start - start_date).days
        duration_days = max((task_end - task_start).days + 1, 1)
        
        x_offset = offset_days * self.day_width + 5
        bar_width = max(duration_days * self.day_width - 10, self.day_width - 10)
        
        # Draw task bar
        bar_color = status_colors[task.status]
        task_bar = ctk.CTkFrame(
            timeline_frame, fg_color=bar_color,
            corner_radius=5, height=25
        )
        task_bar.place(x=x_offset, rely=0.5, anchor="w", width=bar_width)
        
        # Task label on bar
        if bar_width > 50:
            bar_label = ctk.CTkLabel(
                task_bar, text=f"#{task.id}",
                font=("Arial", 9, "bold"),
                text_color="#000000" if task.status != TaskStatus.TODO else "#333333"
            )
            bar_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # Draw today line if visible
        if start_date.date() <= today <= (start_date + timedelta(days=total_days-1)).date():
            today_offset = (today - start_date.date()).days * self.day_width
            today_line = ctk.CTkFrame(
                timeline_frame, fg_color=GANTT_COLORS["today_line"],
                width=2, height=self.row_height
            )
            today_line.place(x=today_offset, rely=0, anchor="nw")


class GanttViewTab(ctk.CTkFrame):
    """Вкладка с диаграммой Ганта."""
    
    def __init__(self, parent, service: TaskService, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.service = service
        
        self.gantt_frame = GanttChartFrame(self, service)
        self.gantt_frame.pack(fill="both", expand=True)
    
    def refresh(self):
        """Обновить диаграмму."""
        self.gantt_frame._render_gantt()
