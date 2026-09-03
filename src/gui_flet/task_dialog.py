"""Task create/edit dialog with all Jira fields."""
import flet as ft
from typing import Optional, Callable
from datetime import datetime
from .app import COLORS, ic
from . import labels as L
from core.datetimeutil import parse_dt, date_part, has_time, normalize


def show_task_dialog(page: ft.Page, title: str = "Новая задача",
                      task=None, on_save: Optional[Callable] = None):
    title_field = ft.TextField(
        label="Название", value=task.title if task else "",
        text_size=14, autofocus=True, border_radius=8,
    )
    desc_field = ft.TextField(
        label="Описание", value=task.description if task else "",
        text_size=14, multiline=True, min_lines=2, max_lines=4, border_radius=8,
    )
    priority_var = task.priority.value if task else "Medium"
    priority_field = ft.Dropdown(
        label="Приоритет", value=priority_var,
        options=[ft.dropdown.Option(v, text=L.priority(v))
                 for v in ("Low", "Medium", "High", "Critical")],
        text_size=14, border_radius=8, width=200,
    )

    # Тип задачи
    task_type_var = getattr(task, 'task_type', 'Task') if task else 'Task'
    task_type_field = ft.Dropdown(
        label="Тип", value=task_type_var,
        options=[ft.dropdown.Option(v, text=L.task_type(v))
                 for v in ("Task", "Bug", "Story", "Epic", "Sub-task")],
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
        label="Дата начала", value=start_date_value,
        text_size=14, border_radius=8, read_only=True,
        suffix_icon=ic("calendar_today"), width=150,
    )
    start_time_field = ft.TextField(
        label="Время", value=start_time_value, hint_text="ЧЧ:ММ",
        text_size=14, border_radius=8, width=90,
    )
    due_display = ft.TextField(
        label="Дедлайн", value=due_date_value,
        text_size=14, border_radius=8, read_only=True,
        suffix_icon=ic("calendar_today"), width=150,
    )
    due_time_field = ft.TextField(
        label="Время", value=due_time_value, hint_text="ЧЧ:ММ",
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
        label="Затрачено (часы)",
        value=str(task.time_spent) if task and task.time_spent > 0 else "0",
        text_size=14, border_radius=8, width=200,
    )
    tags_field = ft.TextField(
        label="Теги (через запятую)",
        value=", ".join(task.tags) if task and task.tags else "",
        text_size=14, border_radius=8, hint_text="frontend, bug, feature",
    )
    assignee_field = ft.TextField(
        label="Исполнитель",
        value=getattr(task, 'assignee', None) or "",
        text_size=14, border_radius=8, width=200,
    )
    story_points_field = ft.TextField(
        label="Очки истории",
        value=str(task.story_points) if task and task.story_points else "",
        text_size=14, border_radius=8, width=200,
    )

    urgency_field = ft.Dropdown(
        label="Срочность", value=getattr(task, 'urgency', 'Normal') if task else 'Normal',
        options=[ft.dropdown.Option(v, text=L.urgency(v))
                 for v in ("Low", "Normal", "High", "Urgent")],
        text_size=14, border_radius=8, width=200,
    )
    watchers_field = ft.TextField(
        label="Наблюдатели (через запятую)",
        value=", ".join(getattr(task, 'watchers', []) or []) if task and getattr(task, 'watchers', None) else "",
        text_size=14, border_radius=8, hint_text="alice, bob",
    )
    error_label = ft.Text("", size=12, color=COLORS["accent_red"])

    def _err(msg: str):
        """Show a validation message. Refresh via the dialog (always mounted)
        rather than the label alone."""
        error_label.value = msg
        for ctl in (error_label, dlg):
            try:
                if getattr(ctl, "page", None) is not None:
                    ctl.update()
                    break
            except (AttributeError, AssertionError, RuntimeError):
                pass

    def on_save_click(e):
        from core.models import Priority

        t = title_field.value.strip()
        if not t:
            _err("Название обязательно")
            return

        s_time = (start_time_field.value or "").strip()
        d_time = (due_time_field.value or "").strip()
        start_val = normalize(start_date_value, s_time)
        due_val = normalize(due_date_value, d_time)
        if s_time and not start_date_value.strip():
            _err("Сначала выберите дату начала"); return
        if d_time and not due_date_value.strip():
            _err("Сначала выберите дату дедлайна"); return
        if (s_time and start_val and " " not in start_val) or \
           (d_time and due_val and " " not in due_val):
            _err("Время в формате ЧЧ:ММ (например 14:30)"); return

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
            ft.TextButton("Отмена", on_click=on_cancel),
            ft.Button("Сохранить", on_click=on_save_click,
                     style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff",
                                        padding=ft.Padding.symmetric(horizontal=20, vertical=8))),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
