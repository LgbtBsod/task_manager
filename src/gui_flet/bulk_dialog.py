"""Bulk status transitions by tag.

A modal panel: pick tag(s) + source status(es) + one target status, see a live
"will move N" preview, then apply in one action — instead of dragging every
matching card by hand. The preview and the apply step share
``service.bulk_transition_candidates`` so the count shown is always exactly
what gets moved.
"""
from typing import TYPE_CHECKING

import flet as ft

from core import strings as L
from core.models import TaskStatus

from ._ui import dropdown as _dropdown
from ._ui import safe_update
from .app import COLORS
from .palette import RADIUS_CHIP
from .task_dialog import _TagPicker

if TYPE_CHECKING:
    from .app import TaskManagerApp


def _status_color(value: str) -> str:
    return COLORS[L.status_style(value)[1]]


def show_bulk_dialog(app: "TaskManagerApp") -> None:
    page = app.page
    catalog = app.service.list_tags()

    selected_tags: set[str] = set()
    selected_sources: set[str] = {TaskStatus.TODO.value}
    target = {"v": TaskStatus.IN_PROGRESS.value}

    preview = ft.Text(L.UI.BULK_PICK_FILTERS, size=13, weight=ft.FontWeight.W_600,
                      color=COLORS["text_primary"])
    apply_btn = ft.Button(
        L.UI.BULK_APPLY, disabled=True,
        style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff"))

    def _recount():
        if not selected_tags or not selected_sources:
            preview.value = L.UI.BULK_PICK_FILTERS
            apply_btn.disabled = True
        else:
            cands = app.service.bulk_transition_candidates(
                list(selected_tags),
                [TaskStatus(s) for s in selected_sources],
                TaskStatus(target["v"]))
            preview.value = L.UI.BULK_PREVIEW.format(n=len(cands))
            apply_btn.disabled = not cands
        safe_update(preview, apply_btn)

    def _apply(e):
        n = app.service.bulk_transition_by_tag(
            list(selected_tags),
            [TaskStatus(s) for s in selected_sources],
            TaskStatus(target["v"]))
        page.pop_dialog()
        app._show_snackbar(L.UI.BULK_DONE.format(n=n))
        app.refresh_all()

    apply_btn.on_click = _apply

    def _toggle_source(value: str, chip: ft.Container):
        selected_sources.discard(value) if value in selected_sources else selected_sources.add(value)
        on = value in selected_sources
        color = _status_color(value)
        chip.bgcolor = color if on else COLORS["bg_button"]
        chip.content.color = "#ffffff" if on else COLORS["text_secondary"]
        chip.content.weight = ft.FontWeight.W_600 if on else ft.FontWeight.NORMAL
        safe_update(chip)
        _recount()

    def _status_chip(value: str) -> ft.Container:
        on = value in selected_sources
        color = _status_color(value)
        chip = ft.Container(
            content=ft.Text(L.STATUS_LABEL[value], size=11,
                            color="#ffffff" if on else COLORS["text_secondary"],
                            weight=ft.FontWeight.W_600 if on else ft.FontWeight.NORMAL),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor=color if on else COLORS["bg_button"],
            border=ft.Border.all(1, color),
            border_radius=RADIUS_CHIP,
        )
        chip.on_click = lambda e, v=value, c=chip: _toggle_source(v, c)
        return chip

    source_chips = ft.Row([_status_chip(s.value) for s in TaskStatus],
                          wrap=True, spacing=6, run_spacing=6)

    def _on_target(e):
        target["v"] = target_dd.value
        _recount()

    target_dd = _dropdown(
        width=200,
        options=[ft.dropdown.Option(s.value, text=L.STATUS_LABEL[s.value]) for s in TaskStatus],
        value=target["v"], on_select=_on_target,
        text_style=ft.TextStyle(size=13, color=COLORS["text_primary"]),
    )

    picker = (_TagPicker(page, catalog, selected_tags, on_change=_recount) if catalog
              else ft.Text(L.UI.BULK_NO_TAGS, size=11, color=COLORS["text_secondary"]))

    def _section(label: str) -> ft.Text:
        return ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=COLORS["text_secondary"])

    body = ft.Column([
        ft.Text(L.UI.BULK_HINT, size=11, color=COLORS["text_secondary"]),
        picker,
        _section(L.UI.BULK_FROM),
        source_chips,
        _section(L.UI.BULK_TO),
        target_dd,
        ft.Divider(color=COLORS["border_color"]),
        preview,
    ], tight=True, width=420, spacing=10, scroll=ft.ScrollMode.AUTO)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(L.UI.BULK_TITLE, size=18, weight=ft.FontWeight.BOLD),
        content=body,
        actions=[
            ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog()),
            apply_btn,
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    _recount()
    page.show_dialog(dlg)
