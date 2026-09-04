"""Flet-based Task Manager application.
Main app module with routing, theme, and view switching.
"""

import flet as ft

from core import paths
from core import strings as L
from core.models import TaskStatus
from core.settings import NOTIFY_HOURS_MAX

from ._ui import dropdown as _dropdown
from ._ui import field as _field
from ._ui import switch as _switch
from .palette import (
    COLORS,
    CUSTOMISABLE,
    DEFAULT_ACCENT,
    base_colors,
    build_theme,
    contrast_ratio,
    is_hex,
    resolve_dark,
)
from .palette import apply as apply_palette


def _app_version() -> str:
    try:
        from utils._version import get_version
        v = get_version()
        return v if v and v != "unknown" else "dev"
    except Exception:
        return "dev"


def ic(name):
    """Resolve a Material icon name to the ``ft.Icons`` enum member.

    Flet 0.86 no longer renders bare icon-name strings (``ft.Icon("edit")``
    shows nothing; ``ft.IconButton(icon="edit")`` throws a render error), so
    every icon reference must go through this.
    """
    if name is None or not isinstance(name, str):
        return name  # already an ft.Icons member (or None)
    return getattr(ft.Icons, name.upper().replace("-", "_"), None)

_NAV_PAD = ft.Padding.symmetric(horizontal=16, vertical=8)
_NAV_TEXT = ft.TextStyle(size=13, weight=ft.FontWeight.W_500)


def _nav_style(active: bool) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=COLORS["accent_blue"] if active else None,
        color="#ffffff" if active else COLORS["text_primary"],
        padding=_NAV_PAD, text_style=_NAV_TEXT,
    )


class TaskManagerApp:
    """Flet Task Manager application."""

    def __init__(self, context=None, service=None, settings=None):
        # The data layer (service + settings) is shared across browser sessions;
        # everything else on this object (page, views, …) is per-session.
        self.context = context
        self.service = context.service if context is not None else service
        self.settings = context.settings if context is not None else settings
        self.page: ft.Page | None = None
        self.current_view: str = "kanban"
        self._search_query: str = ""
        self._sort_mode: str = "default"
        self.deadline_watcher = None

    def _ensure_wired(self):
        """Build a default AppContext when the app was constructed bare
        (``TaskManagerApp()`` — used by tests / a plain ``run_app()``)."""
        if self.service is not None and self.settings is not None:
            return
        from core.app_context import AppContext
        self.context = AppContext.create()
        self.service = self.context.service
        self.settings = self.context.settings

    def notify_hours_before(self) -> int:
        return self.settings.get("notify_hours_before")   # pydantic int, 1..720

    def _apply_theme(self, page: ft.Page) -> None:
        """Rebuild the palette + Flet themes from the current settings.

        For ``"system"`` mode the effective brightness comes from
        ``page.platform_brightness`` so our ``COLORS`` dict and Flet's own
        widget chrome agree.
        """
        mode = self.settings.get("theme_mode") or "dark"
        accent = self.settings.get("accent_color") or DEFAULT_ACCENT
        overrides = self.settings.get("custom_colors") or {}
        system_is_dark = getattr(page, "platform_brightness", None) != ft.Brightness.LIGHT
        apply_palette(mode, accent, system_is_dark=system_is_dark, overrides=overrides)
        page.theme = build_theme(accent, dark=False, overrides=overrides)
        page.dark_theme = build_theme(accent, dark=True, overrides=overrides)
        page.theme_mode = ft.ThemeMode(mode)   # "dark" | "light" | "system"
        page.bgcolor = COLORS["bg_dark"]

    def set_theme(self, *, mode: str | None = None, accent: str | None = None,
                  colors: dict | None = None) -> None:
        """Apply a new theme mode / accent / per-token colours, persist, repaint."""
        changes = {}
        if mode is not None:
            changes["theme_mode"] = mode
        if accent is not None:
            changes["accent_color"] = accent
        if colors is not None:
            changes["custom_colors"] = colors
        if changes:
            self.settings.update(**changes)
        self._apply_theme(self.page)
        # Views cache COLORS[...] at build time -> rebuild + remount them.
        for v in self.views_map.values():
            v.build()
        if self.page is not None and hasattr(self, "_view_host_index"):
            self.page.controls[self._view_host_index] = self.views_map[self.current_view].container
        self._build_top_bar(self.page, replace=True)
        self._build_status_bar(self.page, replace=True)
        self.refresh_all()
        self.page.update()

    def main(self, page: ft.Page):
        self._ensure_wired()
        self.page = page

        page.title = L.APP_TITLE
        page.padding = 0
        page.spacing = 0
        self._apply_theme(page)
        # Re-theme live when the OS flips light/dark and we're on "system".
        page.on_platform_brightness_change = lambda e: (
            self.set_theme() if self.settings.get("theme_mode") == "system" else None
        )

        from .dashboard_view import DashboardView
        from .gantt_view import GanttView
        from .kanban_view import KanbanView

        self.kanban_view = KanbanView(app=self)
        self.gantt_view = GanttView(app=self)
        self.dashboard_view = DashboardView(app=self)

        self.views_map = {
            "kanban": self.kanban_view,
            "gantt": self.gantt_view,
            "dashboard": self.dashboard_view,
        }

        # Build every view once; switching tabs only swaps + refreshes.
        for v in self.views_map.values():
            v.build()

        self.current_view = "kanban"
        self._build_top_bar(page)
        self._view_host_index = len(page.controls)
        page.add(self.kanban_view.container)
        self._build_status_bar(page)

        self.refresh_all()
        page.update()

        # In-app deadline checker.
        try:
            from .deadline_watcher import DeadlineWatcher
            self.deadline_watcher = DeadlineWatcher(
                self.service, self.settings, page,
                on_refresh=lambda: self.refresh_all() if self.current_view == "kanban" else None,
            )
            page.run_task(self.deadline_watcher.run)
        except Exception:
            pass

        # Ask about a new release (only when frozen; never blocks startup).
        try:
            from .update_ui import check_on_start
            page.run_task(check_on_start, self)
        except Exception:
            pass

    def _theme_toggle_button(self) -> ft.IconButton:
        mode = self.settings.get("theme_mode") or "dark"
        icon = {"dark": "dark_mode", "light": "light_mode", "system": "brightness_auto"}[mode]
        nxt = {"dark": "light", "light": "system", "system": "dark"}[mode]
        return ft.IconButton(
            icon=ic(icon), icon_color=COLORS["text_secondary"],
            tooltip=L.UI.THEME_SWITCH.format(mode=L.UI.THEME_MODE_LABEL[mode],
                                             next=L.UI.THEME_MODE_LABEL[nxt]),
            on_click=lambda e: self.set_theme(mode=nxt),
        )

    def _build_top_bar(self, page: ft.Page, replace: bool = False):
        self.nav_buttons = {}
        nav_items = [
            ("kanban", L.NAV["kanban"], "view_kanban"),
            ("gantt", L.NAV["gantt"], "bar_chart"),
            ("dashboard", L.NAV["dashboard"], "dashboard"),
        ]

        nav_buttons_row = []
        for view_id, label, icon in nav_items:
            btn = ft.Button(
                content=label,
                icon=ic(icon),
                on_click=lambda e, v=view_id: self.switch_view(v),
                style=_nav_style(view_id == self.current_view),
            )
            self.nav_buttons[view_id] = btn
            nav_buttons_row.append(btn)

        self.search_field = _field(
            hint_text=L.UI.SEARCH,
            width=200, height=36, text_size=13,
            prefix_icon=ic("search"),
            filled=True, fill_color=COLORS["bg_button"],
            focused_bgcolor=COLORS["bg_card_hover"],
            border_color=ft.Colors.TRANSPARENT,
            on_change=self._on_search,
            content_padding=ft.Padding.only(left=36, top=4, bottom=4),
        )

        # Flet's Material dropdown ignores a small ``height=`` and renders at its
        # ~48 px min touch target, so it towered over the 36 px search field.
        # Pinning ``text_style.height`` + zero vertical content-padding brings it
        # down to the same line as the rest of the top bar.
        self.sort_dropdown = _dropdown(
            width=185,
            options=[ft.dropdown.Option(k, text=v) for k, v in L.UI.SORT.items()],
            value="default", filled=True,
            fill_color=COLORS["bg_button"],
            border_color=ft.Colors.TRANSPARENT,
            on_select=self._on_sort,
            text_style=ft.TextStyle(size=13, height=1.0, color=COLORS["text_primary"]),
            content_padding=ft.Padding.only(left=10, right=6, top=0, bottom=0),
        )

        self.add_button = ft.Button(
            content=L.UI.ADD,
            icon=ic("add"),
            on_click=lambda e: self.show_create_dialog(),
            style=ft.ButtonStyle(
                bgcolor=COLORS["accent_green"], color="#ffffff",
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            ),
        )

        top_bar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(L.APP_TITLE, size=18, weight=ft.FontWeight.BOLD,
                            color=COLORS["text_primary"]),
                    ft.Container(width=20),
                    *nav_buttons_row,
                    ft.Container(expand=True),
                    self.search_field,
                    self.sort_dropdown,
                    self._theme_toggle_button(),
                    ft.IconButton(icon=ic("settings"), icon_color=COLORS["text_secondary"],
                                  tooltip=L.UI.SETTINGS,
                                  on_click=lambda e: self.show_settings_dialog()),
                    self.add_button,
                ],
                spacing=4, alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=COLORS["bg_card"],
        )
        if replace and getattr(self, "_top_bar_index", None) is not None:
            page.controls[self._top_bar_index] = top_bar
        else:
            self._top_bar_index = len(page.controls)
            page.add(top_bar)

    def _build_status_bar(self, page: ft.Page, replace: bool = False):
        self.status_text = ft.Text(L.UI.SB_READY, size=11, color=COLORS["text_secondary"])
        status_bar = ft.Container(
            content=ft.Row(
                controls=[
                    self.status_text,
                    ft.Container(expand=True),
                    ft.Text(f"v{_app_version()}", size=11, color=COLORS["text_secondary"]),
                ],
                spacing=0,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=6),
            bgcolor=COLORS["bg_card"],
        )
        if replace and getattr(self, "_status_bar_index", None) is not None:
            page.controls[self._status_bar_index] = status_bar
        else:
            self._status_bar_index = len(page.controls)
            page.add(status_bar)

    def switch_view(self, view_name: str):
        view = self.views_map.get(view_name)
        if not view:
            return
        self.current_view = view_name

        for vid, btn in self.nav_buttons.items():
            btn.style = _nav_style(vid == view_name)

        # Views are built once in main(); switching only swaps the mounted
        # container and refreshes its data — no teardown/rebuild.
        if self.page is not None and hasattr(self, "_view_host_index"):
            self.page.controls[self._view_host_index] = view.container
        self.refresh_all()

    def _debounce(self, key: str, delay: float, fn):
        """Run ``fn`` after ``delay`` seconds, cancelling any pending call under
        the same ``key``. Keeps per-keystroke handlers from rebuilding the board
        on every character."""
        import threading
        timers = self.__dict__.setdefault("_debounce_timers", {})
        pending = timers.get(key)
        if pending is not None:
            pending.cancel()
        t = threading.Timer(delay, fn)
        t.daemon = True
        timers[key] = t
        t.start()

    def _on_search(self, e):
        self._search_query = (self.search_field.value or "").strip().lower()
        self._debounce("search", 0.25, self.refresh_all)

    def _on_sort(self, e):
        self._sort_mode = self.sort_dropdown.value or "default"
        self.refresh_all()

    def _filter_and_sort(self, tasks):
        if self._search_query:
            q = self._search_query
            tasks = [t for t in tasks
                     if q in t.title.lower()
                     or q in t.description.lower()
                     or any(q in tag for tag in t.tags)]
        if self._sort_mode == "priority":
            tasks = sorted(tasks, key=lambda t: t.priority.sort_index)
        elif self._sort_mode == "due_date":
            tasks = sorted(tasks, key=lambda t: t.due_date or "9999-12-31")
        return tasks

    def refresh_all(self):
        all_tasks = self._filter_and_sort(self.service.get_all_tasks())

        if self.current_view == "kanban":
            self.kanban_view.update_tasks(
                todo=[t for t in all_tasks if t.status == TaskStatus.TODO],
                in_progress=[t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS],
                done=[t for t in all_tasks if t.status == TaskStatus.DONE],
            )
        elif self.current_view == "gantt":
            self.gantt_view.refresh()
        elif self.current_view == "dashboard":
            self.dashboard_view.refresh()

        self.refresh_status_bar()
        if self.page:
            self.page.update()

    def refresh_status_bar(self):
        stats = self.service.get_statistics()
        total = stats["total"]
        if self._search_query:
            filtered = len(self._filter_and_sort(self.service.get_all_tasks()))
            self.status_text.value = L.UI.SB_FOUND.format(shown=filtered, total=total)
        else:
            self.status_text.value = L.UI.SB_TASKS.format(total=total)

    def show_create_dialog(self):
        from .task_dialog import show_task_dialog
        show_task_dialog(self.page, title=L.UI.NEW_TASK, on_save=self._on_create_task)

    def show_settings_dialog(self):
        s = self.settings
        enabled = _switch(value=bool(s.get("notifications_enabled")),
                          label=L.UI.SET_NOTIFY_ENABLED)
        hours = _field(
            label=L.UI.SET_HOURS_BEFORE,
            value=str(s.get("notify_hours_before")),
            width=200, keyboard_type=ft.KeyboardType.NUMBER,
        )
        auto_updates = _switch(
            value=bool(s.get("check_updates_on_start")),
            label=L.UI.SET_CHECK_ON_START,
        )
        err = ft.Text("", size=12, color=COLORS["accent_red"])

        # Theme: mode buttons apply on Save; swatches apply live.
        from core.settings import ACCENT_PRESETS

        chosen = {"mode": s.get("theme_mode") or "dark",
                  "accent": s.get("accent_color") or DEFAULT_ACCENT}

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
            self.set_theme(accent=hex_)   # accent preview is safe & instant

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
        chosen["colors"] = dict(s.get("custom_colors") or {})
        _dark_now = resolve_dark(chosen["mode"],
                                 getattr(self.page, "platform_brightness", None)
                                 != ft.Brightness.LIGHT)
        _defaults = base_colors(_dark_now)
        color_fields: dict[str, tuple[ft.TextField, ft.Container]] = {}

        contrast_warn = ft.Text(L.UI.SET_COLORS_LOW_CONTRAST, size=10,
                                color=COLORS["accent_red"], visible=False)

        def _check_contrast():
            eff = {**_defaults, **chosen["colors"]}
            bad = min(contrast_ratio(eff["text_primary"], eff["bg_card"]),
                      contrast_ratio(eff["text_secondary"], eff["bg_card"])) < 3.0
            if contrast_warn.visible != bad:
                contrast_warn.visible = bad
                try:
                    contrast_warn.update()
                except Exception:
                    pass

        def _preview_colors():
            self.set_theme(colors=dict(chosen["colors"]))
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
            sw.bgcolor = chosen["colors"].get(key, _defaults[key])
            sw.update()
            _preview_colors()

        def _pick_from_palette(key: str, label: str):
            from .color_picker import show_color_picker
            show_color_picker(
                self.page,
                initial=chosen["colors"].get(key) or _defaults[key],
                title=label,
                on_pick=lambda hx: _set_color(key, hx),
                on_default=lambda: _set_color(key, ""),
            )

        color_rows = []
        for key, label in CUSTOMISABLE:
            fld = _field(
                value=chosen["colors"].get(key, ""), hint_text=_defaults[key],
                width=100, text_size=12, dense=True,
                on_change=lambda e, k=key: _set_color(k, e.control.value),
            )
            sw = ft.Container(width=24, height=24, border_radius=6,
                              bgcolor=chosen["colors"].get(key, _defaults[key]),
                              border=ft.Border.all(1, COLORS["border_color"]),
                              tooltip=L.UI.SET_COLORS,
                              on_click=lambda e, k=key, lbl=label: _pick_from_palette(k, lbl))
            color_fields[key] = (fld, sw)
            color_rows.append(ft.Row(
                [sw, ft.Text(label, size=12, color=COLORS["text_secondary"],
                             expand=True), fld],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        def _reset_colors(e):
            chosen["colors"].clear()
            for k, (fld, sw) in color_fields.items():
                fld.value = ""
                sw.bgcolor = _defaults[k]
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
                     check_updates_on_start=auto_updates.value)
            if self.deadline_watcher is not None:
                self.deadline_watcher.reset()
            self.page.pop_dialog()
            if chosen["mode"] != s.get("theme_mode") or chosen["accent"] != s.get("accent_color"):
                self.set_theme(mode=chosen["mode"], accent=chosen["accent"])
            else:
                self.refresh_all()
            self._show_snackbar(L.UI.SET_SAVED)

        def check_updates_click(e):
            from .update_ui import check_now
            check_now(self)

        data_dir = str(paths.data_dir)

        def open_data_dir(e):
            try:
                import subprocess as _sp
                import sys as _sys
                if _sys.platform == "win32":
                    _sp.Popen(["explorer.exe", data_dir])
                elif _sys.platform == "darwin":
                    _sp.Popen(["open", data_dir])
                else:
                    _sp.Popen(["xdg-open", data_dir])
            except OSError:
                self._show_snackbar(data_dir)

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
                ft.TextButton(L.UI.CANCEL, on_click=lambda e: self.page.pop_dialog()),
                ft.Button(L.UI.SAVE, on_click=save,
                          style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _on_create_task(self, **kwargs):
        try:
            self.service.create_task(**kwargs)
            self.refresh_all()
        except ValueError as e:
            self._show_snackbar(str(e), error=True)

    def show_edit_dialog(self, task):
        from .task_dialog import show_task_dialog

        def on_save(**kwargs):
            try:
                self.service.update_task(task.id, **kwargs)
                self.refresh_all()
            except ValueError as e:
                self._show_snackbar(str(e), error=True)

        show_task_dialog(self.page, title=L.UI.EDIT_TASK, task=task, on_save=on_save)

    def delete_task(self, task):
        def close_dlg(e=None):
            self.page.pop_dialog()

        def on_confirm(e):
            self.service.delete_task(task.id)
            close_dlg()
            self.refresh_all()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(L.UI.DELETE_TASK_TITLE),
            content=ft.Text(L.UI.DELETE_TASK_CONFIRM.format(title=task.title)),
            actions=[
                ft.TextButton(L.UI.CANCEL, on_click=close_dlg),
                ft.TextButton(L.UI.DELETE, on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _show_snackbar(self, message: str, error: bool = False):
        self.page.show_dialog(ft.SnackBar(
            content=ft.Text(message),
            bgcolor=COLORS["accent_red"] if error else COLORS["accent_green"],
            duration=3000,
        ))

    def _clone_task(self, task):
        try:
            cloned = self.service.clone_task(task.id)
            if cloned:
                self.refresh_all()
                self._show_snackbar(L.UI.CLONED.format(title=cloned.title))
        except Exception as e:
            self._show_snackbar(str(e), error=True)

    def handle_drop(self, task, target_status_value: str):
        try:
            new_status = TaskStatus(target_status_value)
        except ValueError:
            return
        if new_status == task.status:
            return
        self.service.update_task_status(task.id, new_status)
        self.refresh_all()


def run_app(context=None, port: int = 8550):
    """Entry point for the Flet-based task manager.

    Args:
        context: a built ``AppContext`` (from ``main()``); one is created here
            if omitted.
        port: TCP port for the local web server.
    """
    import os
    import socket
    import time
    import webbrowser

    import flet as ft

    from core.app_context import AppContext
    context = context or AppContext.create()

    def _port_free(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", p)) != 0

    def _kill_stale_on_port(p: int) -> None:
        """Terminate a *previous instance of this app* that is holding the port
        (a crashed / orphaned server). Never touches unrelated processes."""
        import sys as _s
        if _s.platform != "win32":
            return
        me = os.getpid()
        try:
            out = __import__("subprocess").run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-NetTCPConnection -LocalPort {p} -State Listen -EA SilentlyContinue "
                 "| Select-Object -Expand OwningProcess -Unique"],
                capture_output=True, text=True, timeout=8,
            ).stdout
        except Exception:
            return
        for line in out.split():
            try:
                pid = int(line.strip())
            except ValueError:
                continue
            if pid == me:
                continue
            try:
                import subprocess as _sp
                info = _sp.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}';"
                     "\"$($p.Name)|$($p.CommandLine)\""],
                    capture_output=True, text=True, timeout=8,
                ).stdout.lower()
            except Exception:
                info = ""
            is_ours = ("taskmanager.exe" in info
                       or ("python" in info and ("main.py" in info or "task_manager" in info)))
            if is_ours:
                try:
                    _sp.run(["powershell", "-NoProfile", "-Command",
                             f"Stop-Process -Id {pid} -Force -EA SilentlyContinue"],
                            capture_output=True, timeout=8)
                    print(L.APP.KILLED_STALE.format(pid=pid, port=p))
                except Exception:
                    pass

    if not _port_free(port):
        # 1) A healthy instance of us is already serving -> just open a tab at it.
        try:
            import urllib.request
            body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read(4096)
            if b"flutter" in body.lower() or b"flet" in body.lower():
                webbrowser.open(f"http://127.0.0.1:{port}/")
                print(L.APP.ALREADY_RUNNING.format(port=port))
                return
        except Exception:
            pass
        # 2) Port busy but not answering -> a hung old instance of ours: kill it.
        _kill_stale_on_port(port)
        for _ in range(15):                 # wait up to ~3s for the OS to release it
            if _port_free(port):
                break
            time.sleep(0.2)
        # 3) Still busy (a foreign process) -> take the next free port.
        if not _port_free(port):
            for cand in range(port + 1, port + 40):
                if _port_free(cand):
                    print(L.APP.PORT_BUSY.format(port=port, alt=cand))
                    port = cand
                    break

    # IMPORTANT: a fresh TaskManagerApp per browser session. One shared instance
    # means a second tab/window overwrites self.page and the first session's
    # click handlers silently target the wrong page (the "F5 fixes it" bug).
    # The AppContext (service + settings) IS shared so tabs stay consistent.
    def session_main(page: ft.Page):
        TaskManagerApp(context=context).main(page)

    # Force the CanvasKit renderer: the default (AUTO -> SKWASM) needs
    # cross-origin isolation headers the local server doesn't send and renders
    # blank / grey in many browsers. CanvasKit works everywhere.
    ft.run(
        session_main,
        view=ft.AppView.WEB_BROWSER,
        port=port,
        web_renderer=ft.WebRenderer.CANVAS_KIT,
    )
