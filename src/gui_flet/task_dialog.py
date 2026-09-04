"""Task create/edit dialog with all Jira fields."""
from collections.abc import Callable
from datetime import datetime

import flet as ft

from core import strings as L
from core.datetimeutil import date_part, has_time, normalize, parse_dt
from core.models import Priority, TaskType, Urgency

from ._ui import safe_update
from .app import COLORS, ic


def show_task_dialog(page: ft.Page, title: str = L.UI.NEW_TASK,
                      task=None, on_save: Callable | None = None):
    title_field = ft.TextField(
        label=L.UI.F_TITLE, value=task.title if task else "",
        text_size=14, autofocus=True, border_radius=8,
    )
    desc_field = ft.TextField(
        label=L.UI.F_DESCRIPTION, value=task.description if task else "",
        text_size=14, multiline=True, min_lines=2, max_lines=4, border_radius=8,
    )
    priority_var = task.priority.value if task else "Medium"
    priority_field = ft.Dropdown(
        label=L.UI.F_PRIORITY, value=priority_var,
        options=[ft.dropdown.Option(p.value, text=L.priority(p.value)) for p in Priority],
        text_size=14, border_radius=8, width=200,
    )

    task_type_var = getattr(task, 'task_type', 'Task') if task else 'Task'
    task_type_field = ft.Dropdown(
        label=L.UI.F_TYPE, value=task_type_var,
        options=[ft.dropdown.Option(t.value, text=L.task_type(t.value)) for t in TaskType],
        text_size=14, border_radius=8, width=200,
    )

    # ── Dates (date picker) + optional time (ЧЧ:ММ text field) ──
    def _split(dt_str: str):
        d = date_part(dt_str) or ""
        t = ""
        p = parse_dt(dt_str)
        if p and has_time(dt_str):
            t = p.strftime("%H:%M")
        return d, t

    start_date_value, start_time_value = _split(task.start_date if task else "")
    due_date_value, due_time_value = _split(task.due_date if task else "")

    start_display = ft.TextField(
        label=L.UI.F_START_DATE, value=start_date_value,
        text_size=14, border_radius=8, read_only=True,
        suffix_icon=ic("calendar_today"), width=150,
    )
    start_time_field = ft.TextField(
        label=L.UI.F_TIME, value=start_time_value, hint_text=L.UI.F_TIME_HINT,
        text_size=14, border_radius=8, width=90,
    )
    due_display = ft.TextField(
        label=L.UI.F_DUE_DATE, value=due_date_value,
        text_size=14, border_radius=8, read_only=True,
        suffix_icon=ic("calendar_today"), width=150,
    )
    due_time_field = ft.TextField(
        label=L.UI.F_TIME, value=due_time_value, hint_text=L.UI.F_TIME_HINT,
        text_size=14, border_radius=8, width=90,
    )

    def _parse_or_now(s: str) -> datetime:
        return parse_dt(s) or datetime.now()

    def pick_start_date(e):
        def date_changed(ev):
            nonlocal start_date_value
            v = ev.control.value
            start_date_value = v.strftime("%Y-%m-%d") if v else ""
            start_display.value = start_date_value
            start_display.update()

        page.show_dialog(ft.DatePicker(
            first_date=datetime(2020, 1, 1), last_date=datetime(2035, 12, 31),
            value=_parse_or_now(start_date_value), on_change=date_changed,
        ))

    def pick_due_date(e):
        def date_changed(ev):
            nonlocal due_date_value
            v = ev.control.value
            due_date_value = v.strftime("%Y-%m-%d") if v else ""
            due_display.value = due_date_value
            due_display.update()

        page.show_dialog(ft.DatePicker(
            first_date=datetime(2020, 1, 1), last_date=datetime(2035, 12, 31),
            value=_parse_or_now(due_date_value), on_change=date_changed,
        ))

    start_display.on_click = pick_start_date
    due_display.on_click = pick_due_date

    time_field = ft.TextField(
        label=L.UI.F_TIME_SPENT,
        value=str(task.time_spent) if task and task.time_spent > 0 else "0",
        text_size=14, border_radius=8, width=200,
    )
    tags_field = ft.TextField(
        label=L.UI.F_TAGS,
        value=", ".join(task.tags) if task and task.tags else "",
        text_size=14, border_radius=8, hint_text="frontend, bug, feature",
    )
    assignee_field = ft.TextField(
        label=L.UI.F_ASSIGNEE,
        value=getattr(task, 'assignee', None) or "",
        text_size=14, border_radius=8, width=200,
    )
    story_points_field = ft.TextField(
        label=L.UI.F_STORY_POINTS,
        value=str(task.story_points) if task and task.story_points else "",
        text_size=14, border_radius=8, width=200,
    )

    urgency_field = ft.Dropdown(
        label=L.UI.F_URGENCY, value=getattr(task, 'urgency', 'Normal') if task else 'Normal',
        options=[ft.dropdown.Option(u.value, text=L.urgency(u.value)) for u in Urgency],
        text_size=14, border_radius=8, width=200,
    )
    watchers_field = ft.TextField(
        label=L.UI.F_WATCHERS,
        value=", ".join(getattr(task, 'watchers', []) or []) if task and getattr(task, 'watchers', None) else "",
        text_size=14, border_radius=8, hint_text="alice, bob",
    )
    error_label = ft.Text("", size=12, color=COLORS["accent_red"])

    def _err(msg: str):
        """Show a validation message (the dialog is always mounted)."""
        error_label.value = msg
        safe_update(error_label, dlg)

    def on_save_click(e):
        t = title_field.value.strip()
        if not t:
            _err(L.ERR.TITLE_REQUIRED)
            return

        s_time = (start_time_field.value or "").strip()
        d_time = (due_time_field.value or "").strip()
        start_val = normalize(start_date_value, s_time)
        due_val = normalize(due_date_value, d_time)
        if s_time and not start_date_value.strip():
            _err(L.ERR.PICK_START_FIRST)
            return
        if d_time and not due_date_value.strip():
            _err(L.ERR.PICK_DUE_FIRST)
            return
        if (s_time and start_val and " " not in start_val) or \
           (d_time and due_val and " " not in due_val):
            _err(L.ERR.TIME_FORMAT)
            return

        try:
            time_val = float(time_field.value.strip() or "0")
        except ValueError:
            time_val = 0.0

        try:
            sp_val = story_points_field.value.strip()
            sp = int(sp_val) if sp_val else None
        except ValueError:
            sp = None

        priority = Priority(priority_field.value)
        raw_tags = tags_field.value.strip() if tags_field.value else ""
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
        assignee = assignee_field.value.strip() or None

        urgency_val = urgency_field.value
        raw_watchers = watchers_field.value.strip() if watchers_field.value else ""
        watcher_list = [w.strip() for w in raw_watchers.split(",") if w.strip()] if raw_watchers else []

        if on_save:
            try:
                on_save(
                    title=t, description=desc_field.value.strip(),
                    priority=priority, due_date=due_val, start_date=start_val,
                    time_spent=time_val, tags=tags, assignee=assignee,
                    story_points=sp, task_type=task_type_field.value,
                    urgency=urgency_val, watchers=watcher_list,
                )
            except ValueError as ex:
                error_label.value = str(ex)
                error_label.update()
                return

        page.pop_dialog()

    def on_cancel(e):
        page.pop_dialog()

    dates_row = ft.Row([
        start_display, ft.Container(width=6), start_time_field,
        ft.Container(width=16),
        due_display, ft.Container(width=6), due_time_field,
    ], spacing=0)
    prio_type_row = ft.Row([priority_field, ft.Container(width=16), task_type_field], spacing=0)
    time_sp_row = ft.Row([time_field, ft.Container(width=16), story_points_field], spacing=0)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            title_field, desc_field, tags_field,
            ft.Container(height=4),
            prio_type_row, ft.Container(height=4),
            time_sp_row, ft.Container(height=4),
            dates_row, ft.Container(height=4),
            assignee_field, ft.Container(height=4),
            urgency_field, ft.Container(height=4),
            watchers_field, ft.Container(height=4),
            error_label,
        ], spacing=6, width=560, tight=True, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton(L.UI.CANCEL, on_click=on_cancel),
            ft.Button(L.UI.SAVE, on_click=on_save_click,
                     style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff",
                                        padding=ft.Padding.symmetric(horizontal=20, vertical=8))),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
