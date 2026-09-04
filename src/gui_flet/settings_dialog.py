"""The Settings dialog.

Split out of :class:`gui_flet.app.TaskManagerApp` (it was a ~240-line method).
Takes the app object and drives it through the same public surface the rest of
the GUI uses: ``app.settings``, ``app.set_theme(...)``, ``app._show_snackbar``.

Theme edits preview live via ``set_theme(..., persist=False)``; **Save** commits
with ``persist=True``, **Cancel** restores the on-open snapshot.
"""
from typing import TYPE_CHECKING

import flet as ft

from core import paths
from core import strings as L
from core.settings import ACCENT_PRESETS, NOTIFY_HOURS_MAX

from ._ui import field as _field
from ._ui import safe_update
from ._ui import switch as _switch
from .app import COLORS, _app_version, ic
from .palette import (
    CUSTOMISABLE,
    DEFAULT_ACCENT,
    RADIUS_CHIP,
    base_colors,
    contrast_ratio,
    is_hex,
    resolve_dark,
)

if TYPE_CHECKING:
    from .app import TaskManagerApp

_MIN_CONTRAST = 3.0


def show_settings_dialog(app: "TaskManagerApp") -> None:
    s = app.settings
    page = app.page

    # Theme state as it was when the dialog opened — accent / per-token colour
    # edits preview live (persist=False); Cancel restores this.
    snapshot = {
        "mode": s.get("theme_mode") or "dark",
        "accent": s.get("accent_color") or DEFAULT_ACCENT,
        "colors": dict(s.get("custom_colors") or {}),
    }
    chosen = {
        "mode": snapshot["mode"],
        "accent": snapshot["accent"],
        "colors": dict(snapshot["colors"]),
    }

    enabled = _switch(value=bool(s.get("notifications_enabled")),
                      label=L.UI.SET_NOTIFY_ENABLED)
    hours = _field(label=L.UI.SET_HOURS_BEFORE, value=str(s.get("notify_hours_before")),
                   width=200, keyboard_type=ft.KeyboardType.NUMBER)
    auto_updates = _switch(value=bool(s.get("check_updates_on_start")),
                           label=L.UI.SET_CHECK_ON_START)
    auto_start_unblocked = _switch(value=bool(s.get("auto_start_unblocked")),
                                   label=L.UI.SET_AUTO_START_UNBLOCKED)
    auto_close_epic = _switch(value=bool(s.get("auto_close_epic")),
                              label=L.UI.SET_AUTO_CLOSE_EPIC)
    err = ft.Text("", size=12, color=COLORS["accent_red"])

    # ── theme mode (Утро / Вечер / Системная) ──
    mode_buttons: dict[str, ft.Button] = {}

    def _mode_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor=chosen["accent"] if active else COLORS["bg_button"],
            color="#ffffff" if active else COLORS["text_primary"],
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        )

    def _pick_mode(m: str):
        chosen["mode"] = m
        for k, b in mode_buttons.items():
            b.style = _mode_style(k == m)
            b.update()

    for m, lbl in L.UI.THEME_MODE_LABEL.items():
        mode_buttons[m] = ft.Button(content=lbl, style=_mode_style(m == chosen["mode"]),
                                    on_click=lambda e, mm=m: _pick_mode(mm))
    mode_row = ft.Row(list(mode_buttons.values()), spacing=6)

    # ── accent presets (live preview) ──
    swatches: list[ft.Container] = []

    def _pick_accent(hex_: str):
        chosen["accent"] = hex_
        for sw in swatches:
            sw.border = ft.Border.all(
                2, COLORS["text_primary"] if sw.bgcolor.lower() == hex_.lower()
                else ft.Colors.TRANSPARENT)
            sw.update()
        for k, b in mode_buttons.items():
            b.style = _mode_style(k == chosen["mode"])
            b.update()
        app.set_theme(accent=hex_, persist=False)   # live preview only

    for hex_ in ACCENT_PRESETS.values():
        sel = (chosen["accent"] or "").lower() == hex_.lower()
        sw = ft.Container(
            width=26, height=26, bgcolor=hex_, border_radius=13,
            border=ft.Border.all(2, COLORS["text_primary"] if sel else ft.Colors.TRANSPARENT),
            tooltip=hex_, on_click=lambda e, h=hex_: _pick_accent(h),
        )
        swatches.append(sw)
    accent_row = ft.Row(swatches, spacing=8, wrap=True)

    # ── per-token colour overrides (live preview on a complete #rrggbb) ──
    dark_now = resolve_dark(chosen["mode"],
                            getattr(page, "platform_brightness", None) != ft.Brightness.LIGHT)
    defaults = base_colors(dark_now)
    color_fields: dict[str, tuple[ft.TextField, ft.Container]] = {}

    contrast_warn = ft.Text(L.UI.SET_COLORS_LOW_CONTRAST, size=10,
                            color=COLORS["accent_red"], visible=False)

    def _check_contrast():
        eff = {**defaults, **chosen["colors"]}
        # Text must stay legible on both surfaces it lands on: cards and the
        # shell behind them.
        bad = min(contrast_ratio(eff["text_primary"], eff["bg_card"]),
                  contrast_ratio(eff["text_secondary"], eff["bg_card"]),
                  contrast_ratio(eff["text_primary"], eff["bg_dark"]),
                  contrast_ratio(eff["text_secondary"], eff["bg_dark"])) < _MIN_CONTRAST
        if contrast_warn.visible != bad:
            contrast_warn.visible = bad
            try:
                contrast_warn.update()
            except Exception:
                pass

    def _preview_colors():
        app.set_theme(colors=dict(chosen["colors"]), persist=False)
        _check_contrast()

    def _set_color(key: str, hex_or_empty: str):
        fld, sw = color_fields[key]
        hex_or_empty = hex_or_empty.strip().lower()
        if not hex_or_empty:
            chosen["colors"].pop(key, None)
        elif is_hex(hex_or_empty):
            chosen["colors"][key] = hex_or_empty
        else:
            return
        if fld.value != hex_or_empty:
            fld.value = hex_or_empty
            fld.update()
        sw.bgcolor = chosen["colors"].get(key, defaults[key])
        sw.update()
        _preview_colors()

    def _pick_from_palette(key: str, label: str):
        from .color_picker import show_color_picker
        show_color_picker(
            page,
            initial=chosen["colors"].get(key) or defaults[key],
            title=label,
            on_pick=lambda hx: _set_color(key, hx),
            on_default=lambda: _set_color(key, ""),
        )

    color_rows = []
    for key, label in CUSTOMISABLE:
        # Apply on blur / Enter, not per keystroke: a half-typed "#1a2" is not a
        # colour and each attempt would repaint the whole app.
        fld = _field(
            value=chosen["colors"].get(key, ""), hint_text=defaults[key],
            width=100, text_size=12, dense=True,
            on_blur=lambda e, k=key: _set_color(k, e.control.value),
            on_submit=lambda e, k=key: _set_color(k, e.control.value),
        )
        sw = ft.Container(width=24, height=24, border_radius=6,
                          bgcolor=chosen["colors"].get(key, defaults[key]),
                          border=ft.Border.all(1, COLORS["border_color"]),
                          tooltip=L.UI.SET_COLORS,
                          on_click=lambda e, k=key, lbl=label: _pick_from_palette(k, lbl))
        color_fields[key] = (fld, sw)
        color_rows.append(ft.Row(
            [sw, ft.Text(label, size=12, color=COLORS["text_secondary"], expand=True), fld],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))

    def _reset_colors(e):
        chosen["colors"].clear()
        for k, (fld, sw) in color_fields.items():
            fld.value = ""
            sw.bgcolor = defaults[k]
            fld.update()
            sw.update()
        _preview_colors()

    colors_expander = ft.ExpansionTile(
        title=ft.Text(L.UI.SET_COLORS, size=12, weight=ft.FontWeight.BOLD,
                      color=COLORS["text_secondary"]),
        tile_padding=ft.Padding.symmetric(horizontal=0),
        controls_padding=ft.Padding.only(bottom=8),
        text_color=COLORS["text_secondary"], collapsed_text_color=COLORS["text_secondary"],
        icon_color=COLORS["text_secondary"], collapsed_icon_color=COLORS["text_secondary"],
        controls=[
            ft.Text(L.UI.SET_COLORS_HINT, size=10, color=COLORS["text_secondary"]),
            ft.Container(height=4),
            *color_rows,
            contrast_warn,
            ft.Container(height=4),
            ft.TextButton(L.UI.SET_COLORS_RESET, on_click=_reset_colors),
        ],
    )
    _check_contrast()

    # ── tag registry ──
    tag_rows = ft.Column(spacing=6, tight=True)

    def _rebuild_tags():
        tag_rows.controls.clear()
        breakdown = {r["name"]: r["count"] for r in app.service.tag_breakdown()}
        tags = app.service.list_tags()
        if not tags:
            tag_rows.controls.append(
                ft.Text(L.UI.SET_TAGS_EMPTY, size=11, color=COLORS["text_secondary"]))
        for tag in tags:
            tag_rows.controls.append(_tag_row(tag, breakdown.get(tag.name, 0)))
        tag_rows.controls.append(_tag_add_row())
        safe_update(tag_rows)

    def _tag_row(tag, uses: int) -> ft.Row:
        sw = ft.Container(
            width=22, height=22, border_radius=RADIUS_CHIP, bgcolor=tag.color,
            border=ft.Border.all(1, COLORS["border_color"]), tooltip=tag.color,
            on_click=lambda e: _recolor(tag),
        )
        name_fld = _field(value=tag.name, text_size=12, dense=True, expand=True,
                          on_blur=lambda e: _rename(tag, e.control.value),
                          on_submit=lambda e: _rename(tag, e.control.value))
        return ft.Row([
            sw, name_fld,
            ft.Text(L.UI.SET_TAG_USES.format(n=uses), size=11,
                    color=COLORS["text_secondary"]),
            ft.IconButton(ic("delete_outline"), icon_size=16,
                          icon_color=COLORS["text_secondary"],
                          tooltip=L.UI.DELETE, on_click=lambda e: _delete(tag, uses)),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _tag_add_row() -> ft.Row:
        new_fld = _field(hint_text=L.UI.SET_TAGS_NEW, text_size=12, dense=True, expand=True)

        def _add(_e=None):
            name = (new_fld.value or "").strip()
            if not name:
                return
            try:
                app.service.tags.create_tag(name)
            except ValueError:
                return
            _after_change()

        new_fld.on_submit = _add
        return ft.Row([
            new_fld,
            ft.TextButton(L.UI.SET_TAGS_ADD, icon=ic("add"), on_click=_add),
        ], spacing=6)

    def _after_change():
        _rebuild_tags()
        app.refresh_all()

    def _recolor(tag):
        from .color_picker import show_color_picker
        show_color_picker(page, initial=tag.color, title=tag.name,
                          on_pick=lambda hx: (app.service.tags.update_tag(tag.id, color=hx),
                                              _after_change()))

    def _rename(tag, new_name: str):
        new_name = (new_name or "").strip().lower()
        if not new_name or new_name == tag.name:
            return
        try:
            app.service.tags.update_tag(tag.id, name=new_name)
        except ValueError:
            app._show_snackbar(L.UI.SET_TAG_EXISTS, error=True)
        _after_change()

    def _delete(tag, uses: int):
        def _confirm(_e):
            page.pop_dialog()
            app.service.tags.delete_tag(tag.id)
            _after_change()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(L.UI.SET_TAG_DELETE_TITLE),
            content=ft.Text(L.UI.SET_TAG_DELETE_CONFIRM.format(name=tag.name, n=uses)),
            actions=[
                ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog()),
                ft.TextButton(L.UI.DELETE, on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    _rebuild_tags()
    tags_expander = ft.ExpansionTile(
        title=ft.Text(L.UI.SET_TAGS, size=12, weight=ft.FontWeight.BOLD,
                      color=COLORS["text_secondary"]),
        tile_padding=ft.Padding.symmetric(horizontal=0),
        controls_padding=ft.Padding.only(bottom=8),
        text_color=COLORS["text_secondary"], collapsed_text_color=COLORS["text_secondary"],
        icon_color=COLORS["text_secondary"], collapsed_icon_color=COLORS["text_secondary"],
        controls=[
            ft.Text(L.UI.SET_TAGS_HINT, size=10, color=COLORS["text_secondary"]),
            ft.Container(height=4),
            tag_rows,
        ],
    )

    # ── actions ──
    def save(e):
        try:
            h = int(hours.value.strip())
            if not (1 <= h <= NOTIFY_HOURS_MAX):
                raise ValueError
        except ValueError:
            err.value = L.ERR.HOURS_RANGE
            err.update()
            return
        s.update(notifications_enabled=enabled.value, notify_hours_before=h,
                 check_updates_on_start=auto_updates.value,
                 auto_start_unblocked=auto_start_unblocked.value,
                 auto_close_epic=auto_close_epic.value)
        if app.deadline_watcher is not None:
            app.deadline_watcher.reset()
        page.pop_dialog()
        # Commit the theme choices — accent / colours were preview-only so far.
        app.set_theme(mode=chosen["mode"], accent=chosen["accent"],
                      colors=dict(chosen["colors"]), persist=True)
        app._show_snackbar(L.UI.SET_SAVED)

    def cancel(e=None):
        page.pop_dialog()
        touched = (s.get("theme_mode") != snapshot["mode"]
                   or s.get("accent_color") != snapshot["accent"]
                   or s.get("custom_colors") != snapshot["colors"])
        if touched:   # undo the live preview
            app.set_theme(mode=snapshot["mode"], accent=snapshot["accent"],
                          colors=dict(snapshot["colors"]), persist=False)

    def check_updates_click(e):
        from .update_ui import check_now
        check_now(app)

    data_dir = str(paths.data_dir)

    def open_data_dir(e):
        if not paths.open_in_file_manager(paths.data_dir):
            app._show_snackbar(data_dir)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(L.UI.SETTINGS, size=18, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text(L.UI.SET_SECTION_NOTIFY, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            enabled,
            hours,
            ft.Text(L.UI.SET_NOTIFY_HINT, size=11, color=COLORS["text_secondary"]),
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.SET_THEME, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            mode_row,
            ft.Text(L.UI.SET_ACCENT, size=11, color=COLORS["text_secondary"]),
            accent_row,
            colors_expander,
            ft.Divider(color=COLORS["border_color"]),
            tags_expander,
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.SET_SECTION_WORKFLOW, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            auto_start_unblocked,
            ft.Text(L.UI.SET_AUTO_START_UNBLOCKED_HINT, size=10, color=COLORS["text_secondary"]),
            auto_close_epic,
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.SET_UPDATES, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            auto_updates,
            ft.Row([
                ft.TextButton(L.UI.SET_CHECK_NOW, icon=ic("refresh"),
                              on_click=check_updates_click),
                ft.Text(f"v{_app_version()}", size=11, color=COLORS["text_secondary"]),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(color=COLORS["border_color"]),
            ft.Text(L.UI.SET_DATA, size=12, weight=ft.FontWeight.BOLD,
                    color=COLORS["text_secondary"]),
            ft.Text(data_dir, size=11, color=COLORS["text_secondary"],
                    selectable=True, max_lines=2),
            ft.TextButton(L.UI.SET_OPEN_DATA_DIR, icon=ic("folder_open"),
                          on_click=open_data_dir),
            err,
        ], tight=True, width=380, spacing=6, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton(L.UI.CANCEL, on_click=cancel),
            ft.Button(L.UI.SAVE, on_click=save,
                      style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff")),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
