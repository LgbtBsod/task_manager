from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import flet as ft

from core import strings as L
from core.datetimeutil import to_date

from .app import COLORS, ic

if TYPE_CHECKING:
    from .app import TaskManagerApp

ROW_HEIGHT = 44
LEFT_MARGIN = 220
BAR_HEIGHT = 26

# Theme-following colours are read from COLORS at draw time (COLORS is rebuilt
# and this view redrawn on every theme change) — never hard-code them here.


class GanttView:
    """Gantt chart view with proper timeline axis, today marker, and range controls."""

    def __init__(self, app: 'TaskManagerApp'):
        self.app = app
        self.container: ft.Control | None = None
        self._range_var: str = "all"
        self._tasks_data: list = []
        self._min_date = None
        self._max_date = None
        self._total_days = 0

    def build(self):
        self.range_buttons = {}
        btns = []
        for val, label in L.UI.GANTT_RANGE.items():
            active = val == self._range_var
            btn = ft.Button(
                content=label, on_click=lambda e, v=val: self._set_range(v),
                style=ft.ButtonStyle(
                    bgcolor=COLORS["accent_blue"] if active else COLORS["bg_button"],
                    color="#ffffff" if active else COLORS["text_primary"],
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    text_style=ft.TextStyle(size=12),
                ),
            )
            self.range_buttons[val] = btn
            btns.append(btn)

        header = ft.Container(
            content=ft.Row([
                ft.Text(L.UI.GANTT_TITLE, size=18, weight=ft.FontWeight.BOLD,
                        color=COLORS["text_primary"]),
                ft.Container(expand=True),
                ft.Row(btns, spacing=4),
            ]),
            padding=ft.Padding.only(left=20, right=20, top=15, bottom=5),
        )

        self._scroll = ft.Column(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)

        self.container = ft.Column(controls=[header, self._scroll], spacing=0, expand=True)

    def _set_range(self, value: str):
        self._range_var = value
        for v, btn in self.range_buttons.items():
            active = v == value
            btn.style.bgcolor = COLORS["accent_blue"] if active else COLORS["bg_button"]
            btn.style.color = "#ffffff" if active else COLORS["text_primary"]
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
            starts = [d for t in tasks if (d := to_date(t.get_gantt_start()))]
            ends = [d for t in tasks if (d := to_date(t.get_gantt_end()))]
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
                        ft.Icon(ic("bar_chart"), size=48, color=COLORS["border_color"]),
                        ft.Container(height=12),
                        ft.Text(L.UI.GANTT_EMPTY, size=14, color=COLORS["text_secondary"]),
                        ft.Container(height=4),
                        ft.Text(L.UI.GANTT_EMPTY_HINT, size=12, color=COLORS["text_secondary"]),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.Alignment(0, 0), expand=True,
                )
            ]
            return

        self._tasks_data = sorted(
            tasks_with_dates,
            key=lambda t: (t.status.order, t.priority.sort_index, t.title),
        )

        self._min_date, self._max_date = self._get_date_range(self._tasks_data)
        self._total_days = max((self._max_date - self._min_date).days, 1)
        self._draw()

    def _draw(self):
        td = self._total_days
        today = datetime.now().date()
        controls = []

        step = max(1, td // 12)

        muted = COLORS["text_secondary"]
        grid = COLORS["border_color"]
        today_color = COLORS["accent_red"]

        header_cells = [
            ft.Container(
                content=ft.Text(L.UI.GANTT_COL_TASK, size=10, color=muted,
                                weight=ft.FontWeight.W_500),
                width=LEFT_MARGIN - 10, alignment=ft.Alignment(-1, 0),
            )
        ]
        for d in range(0, td + 1, step):
            date_obj = self._min_date + timedelta(days=d)
            date_str = date_obj.strftime("%d.%m")
            weekday = date_obj.strftime("%a")
            is_today = (date_obj == today)
            header_cells.append(ft.Container(
                content=ft.Column([
                    ft.Text(date_str, size=9, color=today_color if is_today else muted,
                            text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.W_600 if is_today else ft.FontWeight.NORMAL),
                    ft.Text(weekday, size=8, color=muted, text_align=ft.TextAlign.CENTER),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=max(step, 1), alignment=ft.Alignment(0.5, 0),
            ))

        controls.append(ft.Container(
            content=ft.Row(header_cells, spacing=0),
            padding=ft.Padding.only(left=10, right=10, top=8, bottom=4),
        ))
        controls.append(ft.Divider(color=grid, height=1))

        for i, task in enumerate(self._tasks_data):
            start_dt = to_date(task.get_gantt_start())
            end_dt = to_date(task.get_gantt_end())
            if start_dt is None or end_dt is None:
                continue

            duration = max((end_dt - start_dt).days, 1)
            start_offset = max((start_dt - self._min_date).days, 0)
            remaining = max(td - start_offset - duration, 0)
            bar_color = task.priority.color
            is_done = task.status.value == "Done"

            status_icon, _ckey = L.status_style(task.status.value)
            icon_color = COLORS.get(_ckey, "#86868b")

            bar_text = None
            if duration / td > 0.04:
                bar_text = ft.Text(task.title[:25], size=10, color="#ffffff",
                                   max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

            bar_inner = ft.Container(
                content=bar_text, height=BAR_HEIGHT, bgcolor=bar_color, border_radius=6,
                padding=ft.Padding.only(left=8, right=8), alignment=ft.Alignment(-1, 0),
                opacity=0.55 if is_done else 1.0,
                on_click=lambda e, t=task: self.app.show_edit_dialog(t),
                tooltip=L.UI.GANTT_TOOLTIP.format(
                    title=task.title, priority=L.priority(task.priority.value),
                    status=L.status(task.status.value),
                    start=task.get_gantt_start(), end=task.get_gantt_end()),
            )

            duration_label = f"{duration} {L.UNIT_DAYS}" if duration > 0 else ""
            due_info = " !" if (task.due_date and task.is_overdue()) else ""

            row_children = [
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ic(status_icon), size=14, color=icon_color),
                        ft.Text(task.title[:24], size=12, color=COLORS["text_primary"],
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=6),
                    width=LEFT_MARGIN - 10,
                ),
            ]
            if start_offset > 0:
                row_children.append(ft.Container(expand=start_offset))
            row_children.append(ft.Container(
                expand=max(duration, 1),
                content=ft.Row([
                    ft.Container(expand=1, content=bar_inner),
                    ft.Text(f"{duration_label}{due_info}", size=9,
                            color=today_color if due_info else muted)
                    if (duration_label or due_info) else ft.Container(),
                ], spacing=4),
            ))
            if remaining > 0:
                row_children.append(ft.Container(expand=remaining))

            row = ft.Container(
                content=ft.Row(row_children, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                height=ROW_HEIGHT, padding=ft.Padding.only(left=10, right=10),
                bgcolor=COLORS["bg_card"] if (i % 2 == 1) else None,
            )

            if i > 0:
                controls.append(ft.Container(height=1, bgcolor=grid))
            controls.append(row)

        if self._min_date <= today <= self._max_date:
            today_offset = (today - self._min_date).days
            controls.append(ft.Container(height=2, bgcolor=grid))
            marker_cells = [
                ft.Container(content=ft.Text(L.UI.GANTT_TODAY, size=9, color=today_color,
                                             weight=ft.FontWeight.W_500),
                             width=LEFT_MARGIN - 10, alignment=ft.Alignment(1, 0)),
            ]
            if today_offset > 0:
                marker_cells.append(ft.Container(expand=today_offset))
            marker_cells.append(ft.Container(width=2, height=20, bgcolor=today_color, border_radius=1))
            if td - today_offset > 0:
                marker_cells.append(ft.Container(expand=td - today_offset))
            controls.append(ft.Row(marker_cells, spacing=0))

        self._scroll.controls = controls
