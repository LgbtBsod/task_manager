import flet as ft
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from .app import COLORS, PRIORITY_COLORS

if TYPE_CHECKING:
    from .app import TaskManagerApp

ROW_HEIGHT = 44
LEFT_MARGIN = 220
BAR_HEIGHT = 26
TODAY_LINE_COLOR = "#ff453a"
WEEKEND_COLOR = "#1a1a1c"
GRID_LINE_COLOR = "#2c2c2e"


class GanttView:
    """Gantt chart view with proper timeline axis, today marker, and range controls."""

    def __init__(self, app: 'TaskManagerApp'):
        self.app = app
        self.container: Optional[ft.Control] = None
        self._range_var: str = "all"
        self._tasks_data: list = []
        self._min_date = None
        self._max_date = None
        self._total_days = 0

    def build(self):
        self.range_buttons = {}
        range_items = [
            ("all", "Все"),
            ("month", "Месяц"),
            ("week", "Неделя"),
            ("quarter", "Квартал"),
        ]
        btns = []
        for val, label in range_items:
            btn = ft.Button(
                text=label, on_click=lambda e, v=val: self._set_range(v),
                style=ft.ButtonStyle(
                    bgcolor=COLORS["accent_blue"] if val == self._range_var else ft.Colors.TRANSPARENT,
                    color="#ffffff" if val == self._range_var else COLORS["text_primary"],
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    text_style=ft.TextStyle(size=12),
                ),
            )
            self.range_buttons[val] = btn
            btns.append(btn)

        header = ft.Container(
            content=ft.Row([
                ft.Text("Gantt Chart", size=18, weight=ft.FontWeight.BOLD,
                        color=COLORS["text_primary"]),
                ft.Container(expand=True),
                ft.Row(btns, spacing=4),
            ]),
            padding=ft.padding.only(left=20, right=20, top=15, bottom=5),
        )

        self._scroll = ft.Column(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)

        self.container = ft.Column(controls=[header, self._scroll], spacing=0, expand=True)

    def _set_range(self, value: str):
        self._range_var = value
        for v, btn in self.range_buttons.items():
            btn.style.bgcolor = COLORS["accent_blue"] if v == value else ft.Colors.TRANSPARENT
            btn.style.color = "#ffffff" if v == value else COLORS["text_primary"]
            btn.update()
        self.refresh()

    def _get_date_range(self, tasks):
        today = datetime.now().date()
        if self._range_var == "week":
            return today - timedelta(days=1), today + timedelta(days=7)
        elif self._range_var == "month":
            return today - timedelta(days=3), today + timedelta(days=28)
        elif self._range_var == "quarter":
            return today - timedelta(days=7), today + timedelta(days=90)
        else:
            starts, ends = [], []
            for t in tasks:
                try:
                    starts.append(datetime.strptime(t.get_gantt_start(), "%Y-%m-%d").date())
                except (ValueError, TypeError):
                    pass
                try:
                    ends.append(datetime.strptime(t.get_gantt_end(), "%Y-%m-%d").date())
                except (ValueError, TypeError):
                    pass
            if not starts or not ends:
                return today - timedelta(days=7), today + timedelta(days=21)
            return min(starts) - timedelta(days=2), max(ends) + timedelta(days=3)

    def refresh(self):
        tasks = self.app.service.get_all_tasks()
        tasks_with_dates = [t for t in tasks if t.start_date or t.due_date]

        if not tasks_with_dates:
            self._scroll.controls = [
                ft.Container(
                    content=ft.Column([
                        ft.Icon("bar_chart", size=48, color="#38383a"),
                        ft.Container(height=12),
                        ft.Text("Нет задач с датами для отображения", size=14, color="#86868b"),
                        ft.Container(height=4),
                        ft.Text("Добавьте дату начала или дедлайн к задаче", size=12, color="#48484a"),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.alignment.center(0, 0), expand=True,
                )
            ]
            self._scroll.update()
            return

        status_order = {"In Progress": 0, "Todo": 1, "Done": 2}
        prio_order = {"High": 0, "Medium": 1, "Low": 2}
        self._tasks_data = sorted(
            tasks_with_dates,
            key=lambda t: (status_order.get(t.status.value, 99),
                          prio_order.get(t.priority.value, 99), t.title),
        )

        self._min_date, self._max_date = self._get_date_range(self._tasks_data)
        self._total_days = max((self._max_date - self._min_date).days, 1)
        self._draw()

    def _draw(self):
        td = self._total_days
        today = datetime.now().date()
        controls = []

        step = max(1, td // 12)

        header_cells = [
            ft.Container(
                content=ft.Text("Задача", size=10, color="#86868b", weight=ft.FontWeight.W_500),
                width=LEFT_MARGIN - 10, alignment=ft.Alignment(-1, 0),
            )
        ]
        for d in range(0, td + 1, step):
            date_obj = self._min_date + timedelta(days=d)
            date_str = date_obj.strftime("%d.%m")
            weekday = date_obj.strftime("%a")
            is_today = (date_obj == today)
            color = TODAY_LINE_COLOR if is_today else "#86868b"
            header_cells.append(ft.Container(
                content=ft.Column([
                    ft.Text(date_str, size=9, color=color, text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.W_600 if is_today else ft.FontWeight.NORMAL),
                    ft.Text(weekday, size=8, color="#48484a", text_align=ft.TextAlign.CENTER),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=max(step, 1), alignment=ft.Alignment(0.5, 0),
            ))

        controls.append(ft.Container(
            content=ft.Row(header_cells, spacing=0),
            padding=ft.padding.only(left=10, right=10, top=8, bottom=4),
        ))
        controls.append(ft.Divider(color=GRID_LINE_COLOR, height=1))

        for i, task in enumerate(self._tasks_data):
            try:
                start_dt = datetime.strptime(task.get_gantt_start(), "%Y-%m-%d").date()
                end_dt = datetime.strptime(task.get_gantt_end(), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            duration = max((end_dt - start_dt).days, 1)
            start_offset = max((start_dt - self._min_date).days, 0)
            remaining = max(td - start_offset - duration, 0)
            bar_color = PRIORITY_COLORS.get(task.priority.value, "#FF9800")
            is_done = task.status.value == "Done"

            status_icons = {"Todo": "radio_button_unchecked", "In Progress": "pending", "Done": "check_circle"}
            status_icon = status_icons.get(task.status.value, "radio_button_unchecked")
            icon_color = {
                "Todo": COLORS["accent_blue"],
                "In Progress": COLORS["accent_orange"],
                "Done": COLORS["accent_green"],
            }.get(task.status.value, "#86868b")

            bar_text = None
            if duration / td > 0.04:
                bar_text = ft.Text(task.title[:25], size=10, color="#ffffff",
                                   max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

            bar_inner = ft.Container(
                content=bar_text, height=BAR_HEIGHT, bgcolor=bar_color, border_radius=6,
                padding=ft.padding.only(left=8, right=8), alignment=ft.Alignment(-1, 0),
                opacity=0.55 if is_done else 1.0,
                on_click=lambda e, t=task: self.app.show_edit_dialog(t),
                tooltip=f"{task.title} | {task.priority.value} | {task.status.value} | {task.get_gantt_start()} - {task.get_gantt_end()}",
            )

            duration_label = f"{duration}d" if duration > 0 else ""
            due_info = " !" if (task.due_date and task.is_overdue()) else ""

            row_children = [
                ft.Container(
                    content=ft.Row([
                        ft.Icon(status_icon, size=14, color=icon_color),
                        ft.Text(task.title[:24], size=12, color="#f5f5f7",
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=6),
                    width=LEFT_MARGIN - 10,
                ),
                ft.Container(expand=start_offset),
                ft.Container(
                    expand=max(duration, 1),
                    content=ft.Row([
                        ft.Container(expand=1, content=bar_inner),
                        ft.Text(f"{duration_label}{due_info}", size=9,
                                color=COLORS["accent_red"] if due_info else "#86868b")
                        if (duration_label or due_info) else ft.Container(),
                    ], spacing=4),
                ),
                ft.Container(expand=remaining),
            ]

            row = ft.Container(
                content=ft.Row(row_children, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=ROW_HEIGHT, padding=ft.padding.only(left=10, right=10),
                bgcolor=WEEKEND_COLOR if (i % 2 == 1) else None,
            )

            if i > 0:
                controls.append(ft.Container(height=1, bgcolor=GRID_LINE_COLOR))
            controls.append(row)

        if self._min_date <= today <= self._max_date:
            today_offset = (today - self._min_date).days
            controls.append(ft.Container(height=2, bgcolor=GRID_LINE_COLOR))
            today_marker_row = ft.Row([
                ft.Container(content=ft.Text("Сегодня", size=9, color=TODAY_LINE_COLOR,
                                              weight=ft.FontWeight.W_500),
                               width=LEFT_MARGIN - 10, alignment=ft.Alignment(1, 0)),
                ft.Container(expand=today_offset),
                ft.Container(width=2, height=20, bgcolor=TODAY_LINE_COLOR, border_radius=1),
                ft.Container(expand=td - today_offset),
            ], spacing=0)
            controls.append(today_marker_row)

        self._scroll.controls = controls
        self._scroll.update()