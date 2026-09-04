"""Recurring tasks — a schedule that auto-generates a fresh task each time
its period comes due (core.models.RecurringTask.next_due_date/due_occurrence,
core.service_catalog.RecurringService). Generation itself runs on
DeadlineWatcher's periodic tick, not from here — this dialog is just CRUD
over the recurring-task *definitions*.
"""
from datetime import datetime
from typing import TYPE_CHECKING

import flet as ft

from core import strings as L
from core.models import Priority, RecurrenceFrequency

from ._ui import dropdown as _dropdown
from ._ui import field as _field
from ._ui import safe_update
from .app import COLORS, ic

if TYPE_CHECKING:
    from .app import TaskManagerApp


def show_recurring_dialog(app: "TaskManagerApp") -> None:
    page = app.page
    list_col = ft.Column(spacing=8, tight=True)

    def _refresh_list():
        list_col.controls.clear()
        recs = app.service.get_all_recurring()
        if not recs:
            list_col.controls.append(
                ft.Text(L.UI.REC_EMPTY, size=11, color=COLORS["text_secondary"]))
        for rec in recs:
            list_col.controls.append(_rec_row(rec))
        safe_update(list_col)

    def _rec_row(rec) -> ft.Row:
        next_due = rec.next_due_date()
        subtitle = (L.UI.REC_NEXT.format(date=next_due) if next_due
                   else L.UI.REC_NO_BASE_DATE)
        return ft.Row([
            ft.Switch(value=rec.is_active, active_color=COLORS["accent_blue"],
                     on_change=lambda e, r=rec: _toggle(r)),
            ft.Column([
                ft.Text(rec.title, size=13, weight=ft.FontWeight.W_600,
                       color=COLORS["text_primary"]),
                ft.Text(f"{L.frequency(rec.frequency)} · {subtitle}", size=11,
                       color=COLORS["text_secondary"]),
            ], spacing=0, expand=True),
            ft.IconButton(ic("delete_outline"), icon_size=16,
                         icon_color=COLORS["text_secondary"],
                         tooltip=L.UI.DELETE, on_click=lambda e, r=rec: _delete(r)),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _toggle(rec):
        app.service.toggle_recurring_active(rec.id)
        _refresh_list()

    def _delete(rec):
        app.service.delete_recurring(rec.id)
        _refresh_list()

    # ── author a new recurring task ──
    title_field = _field(label=L.UI.REC_TITLE, text_size=13, width=320)

    freq_dropdown = _dropdown(
        label=L.UI.REC_FREQUENCY, value=RecurrenceFrequency.WEEKLY.value,
        options=[ft.dropdown.Option(f.value, text=L.frequency(f.value))
                for f in RecurrenceFrequency],
        text_size=13, width=200,
    )
    priority_dropdown = _dropdown(
        label=L.UI.REC_PRIORITY, value=Priority.MEDIUM.value,
        options=[ft.dropdown.Option(p.value, text=L.priority(p.value)) for p in Priority],
        text_size=13, width=150,
    )

    base_date_value: dict[str, str] = {"v": ""}
    date_field = _field(label=L.UI.REC_BASE_DATE, value="", read_only=True,
                        suffix_icon=ic("calendar_today"), text_size=13, width=150)
    err = ft.Text("", size=11, color=COLORS["accent_red"])

    def pick_date(e):
        def date_changed(ev):
            v = ev.control.value
            if v is None:
                return
            # DatePicker's value round-trips through the client as a
            # UTC-tagged instant — formatting it directly shows the wrong
            # calendar day whenever local time is ahead of UTC (e.g. a user
            # in UTC+4 picking "Sep 1" gets back "Aug 31 20:00 UTC", which
            # strftime'd as-is prints "2026-08-31"). Normalize to local time
            # first so the stored date matches what was actually clicked.
            base_date_value["v"] = v.astimezone().strftime("%Y-%m-%d")
            date_field.value = base_date_value["v"]
            date_field.update()

        page.show_dialog(ft.DatePicker(
            first_date=datetime(2020, 1, 1), last_date=datetime(2035, 12, 31),
            value=datetime.now(), on_change=date_changed,
        ))

    date_field.on_click = pick_date

    def _add(e):
        title = (title_field.value or "").strip()
        if not title:
            return
        if not base_date_value["v"]:
            err.value = L.UI.REC_PICK_DATE_FIRST
            err.update()
            return
        err.value = ""
        app.service.create_recurring_task(
            title, frequency=freq_dropdown.value or RecurrenceFrequency.WEEKLY.value,
            base_due_date=base_date_value["v"], priority=priority_dropdown.value or Priority.MEDIUM.value,
        )
        title_field.value = ""
        base_date_value["v"] = ""
        date_field.value = ""
        safe_update(title_field, date_field, err)
        _refresh_list()

    _refresh_list()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(L.UI.REC_TITLE_DIALOG, size=18, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text(L.UI.REC_MANAGE_HINT, size=11, color=COLORS["text_secondary"]),
            ft.Container(height=4),
            list_col,
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.REC_NEW, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            title_field,
            ft.Row([freq_dropdown, priority_dropdown], spacing=8, wrap=True),
            date_field,
            err,
            ft.TextButton(L.UI.REC_ADD, icon=ic("add"), on_click=_add),
        ], tight=True, width=420, spacing=8, scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
