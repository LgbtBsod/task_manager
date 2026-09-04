"""Project templates — a reusable multi-task phased plan.

Author once (a name + an ordered list of step titles, each optionally
"sequential" = blocked by the step before it), then apply it any time to
stamp out real, already-linked tasks in one action. The actual creation goes
through TaskService.create_tasks_from_project_template, which reuses
epic_link / Task.links(BLOCKED_BY) — the same mechanisms the task dialog's
Epic picker and "blocked by" chip picker already drive by hand.
"""
from typing import TYPE_CHECKING

import flet as ft

from core import strings as L

from ._ui import field as _field
from ._ui import safe_update
from ._ui import switch as _switch
from .app import COLORS, ic

if TYPE_CHECKING:
    from .app import TaskManagerApp


def show_project_templates_dialog(app: "TaskManagerApp") -> None:
    page = app.page
    list_col = ft.Column(spacing=8, tight=True)

    def _refresh_list():
        list_col.controls.clear()
        templates = app.service.templates.get_all_project_templates()
        if not templates:
            list_col.controls.append(
                ft.Text(L.UI.PT_EMPTY, size=11, color=COLORS["text_secondary"]))
        for tpl in templates:
            list_col.controls.append(_template_row(tpl))
        safe_update(list_col)

    def _template_row(tpl) -> ft.Row:
        return ft.Row([
            ft.Column([
                ft.Text(tpl.name, size=13, weight=ft.FontWeight.W_600,
                       color=COLORS["text_primary"]),
                ft.Text(L.UI.PT_STEP_COUNT.format(n=len(tpl.steps)), size=11,
                       color=COLORS["text_secondary"]),
            ], spacing=0, expand=True),
            ft.TextButton(L.UI.PT_APPLY, icon=ic("play_arrow"),
                         on_click=lambda e, t=tpl: _open_apply(t)),
            ft.IconButton(ic("delete_outline"), icon_size=16, icon_color=COLORS["text_secondary"],
                         tooltip=L.UI.DELETE, on_click=lambda e, t=tpl: _delete(t)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _delete(tpl):
        app.service.templates.delete_project_template(tpl.id)
        _refresh_list()

    def _open_apply(tpl):
        epic_field = _field(label=L.UI.PT_EPIC_TITLE, hint_text=tpl.name,
                            text_size=13, width=280)

        def _do_apply(e):
            page.pop_dialog()
            tasks = app.service.create_tasks_from_project_template(
                tpl.id, epic_title=(epic_field.value or "").strip() or None)
            app._show_snackbar(L.UI.PT_APPLIED.format(n=len(tasks)))
            app.refresh_all()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(L.UI.PT_APPLY_TITLE.format(name=tpl.name), size=16,
                          weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Text(L.UI.PT_APPLY_HINT, size=11, color=COLORS["text_secondary"]),
                epic_field,
            ], tight=True, width=320, spacing=8),
            actions=[
                ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog()),
                ft.Button(L.UI.PT_APPLY, on_click=_do_apply,
                         style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    # ── author a new template ──
    name_field = _field(label=L.UI.PT_NAME, text_size=13, width=320)
    steps_col = ft.Column(spacing=6, tight=True)
    step_rows: list[dict] = []

    def _add_step_row(title: str = ""):
        title_field = _field(hint_text=L.UI.PT_STEP_HINT, text_size=12, dense=True,
                             expand=True, value=title)
        seq_switch = _switch(value=True, label=L.UI.PT_SEQUENTIAL)
        entry = {"title_field": title_field, "seq_switch": seq_switch}

        def _remove(e):
            steps_col.controls.remove(entry["row"])
            step_rows.remove(entry)
            safe_update(steps_col)

        entry["row"] = ft.Row([
            title_field, seq_switch,
            ft.IconButton(ic("close"), icon_size=14, icon_color=COLORS["text_secondary"],
                         on_click=_remove),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        step_rows.append(entry)
        steps_col.controls.append(entry["row"])
        safe_update(steps_col)

    _add_step_row()
    _add_step_row()

    def _save_template(e):
        name = (name_field.value or "").strip()
        if not name:
            return
        steps = [{"title": r["title_field"].value or "", "sequential": r["seq_switch"].value}
                for r in step_rows]
        app.service.templates.create_project_template(name, steps=steps)
        name_field.value = ""
        steps_col.controls.clear()
        step_rows.clear()
        _add_step_row()
        _add_step_row()
        safe_update(name_field, steps_col)
        _refresh_list()

    _refresh_list()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(L.UI.PT_TITLE, size=18, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            list_col,
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.PT_NEW, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            name_field,
            steps_col,
            ft.Row([
                ft.TextButton(L.UI.PT_ADD_STEP, icon=ic("add"),
                             on_click=lambda e: _add_step_row()),
                ft.TextButton(L.UI.PT_SAVE, icon=ic("save"), on_click=_save_template),
            ]),
        ], tight=True, width=420, spacing=10, scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
