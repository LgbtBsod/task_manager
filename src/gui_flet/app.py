"""Flet-based Task Manager application.
Main app module with routing, theme, and view switching.
"""
import flet as ft
from pathlib import Path
from typing import Optional

from . import labels as L

APP_DIR = Path(__file__).parent.parent.parent
DB_PATH = APP_DIR / "data" / "db" / "tasks.json"


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

DARK_THEME = ft.Theme(
    color_scheme_seed="#0a84ff",
    color_scheme=ft.ColorScheme(
        primary="#0a84ff",
        on_primary="#ffffff",
        primary_container="#1c3a5e",
        on_primary_container="#d0e4ff",
        secondary="#ff9f0a",
        on_secondary="#000000",
        secondary_container="#4a2d00",
        on_secondary_container="#ffd980",
        tertiary="#30d158",
        on_tertiary="#000000",
        tertiary_container="#003d13",
        on_tertiary_container="#a0f5b0",
        error="#ff453a",
        on_error="#ffffff",
        error_container="#93000a",
        on_error_container="#ffdad6",
        surface="#0a0a0a",
        on_surface="#f5f5f7",
        on_surface_variant="#86868b",
        surface_container="#1c1c1e",
        surface_container_low="#161618",
        surface_container_high="#2c2c2e",
        outline="#38383a",
        outline_variant="#48484a",
    ),
    text_theme=ft.TextTheme(
        body_large=ft.TextStyle(size=14, color="#f5f5f7"),
        body_medium=ft.TextStyle(size=12, color="#f5f5f7"),
        body_small=ft.TextStyle(size=11, color="#86868b"),
        label_large=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD, color="#f5f5f7"),
        label_medium=ft.TextStyle(size=12, color="#f5f5f7"),
        label_small=ft.TextStyle(size=11, color="#86868b"),
        title_large=ft.TextStyle(size=22, weight=ft.FontWeight.BOLD, color="#f5f5f7"),
        title_medium=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD, color="#f5f5f7"),
        title_small=ft.TextStyle(size=14, weight=ft.FontWeight.W_600, color="#f5f5f7"),
        headline_medium=ft.TextStyle(size=28, weight=ft.FontWeight.BOLD, color="#f5f5f7"),
    ),
)

COLORS = {
    "bg_dark": "#0a0a0a",
    "bg_card": "#1c1c1e",
    "bg_card_hover": "#2c2c2e",
    "bg_button": "#3a3a3c",
    "text_primary": "#f5f5f7",
    "text_secondary": "#86868b",
    "accent_blue": "#0a84ff",
    "accent_green": "#30d158",
    "accent_orange": "#ff9f0a",
    "accent_red": "#ff453a",
    "accent_purple": "#bf5af2",
    "border_color": "#38383a",
}

PRIORITY_COLORS = {"Low": "#4CAF50", "Medium": "#FF9800", "High": "#F44336", "Critical": "#FF1744"}

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

    def __init__(self, service=None, settings=None):
        # service / settings are shared across browser sessions; the rest of
        # this object (page, views, current_view, …) is strictly per-session.
        self.service = service
        self.settings = settings
        self.page: Optional[ft.Page] = None
        self.current_view: str = "kanban"
        self._search_query: str = ""
        self._sort_mode: str = "default"
        self._notified_overdue: set = set()

    def init_service(self):
        if self.service is not None and self.settings is not None:
            return
        import sys
        src_path = APP_DIR / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        from core.repository import TaskRepository
        from core.service import TaskService
        from core.settings import SettingsStore
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if self.service is None:
            self.service = TaskService(repository=TaskRepository(db_path=str(DB_PATH)))
        if self.settings is None:
            self.settings = SettingsStore(str(DB_PATH.parent / "settings.json"))

    def notify_hours_before(self) -> int:
        try:
            return int(self.settings.get("notify_hours_before"))
        except (TypeError, ValueError, AttributeError):
            return 24

    def main(self, page: ft.Page):
        self.init_service()
        self.page = page

        page.title = L.APP_TITLE
        page.theme = DARK_THEME
        page.dark_theme = DARK_THEME
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = COLORS["bg_dark"]
        page.padding = 0
        page.spacing = 0

        from .kanban_view import KanbanView
        from .gantt_view import GanttView
        from .dashboard_view import DashboardView

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
            page.run_task(self._deadline_watcher)
        except Exception:
            pass

        # Ask about a new release (only when frozen; never blocks startup).
        try:
            from .update_ui import check_on_start
            page.run_task(check_on_start, self)
        except Exception:
            pass

    async def _deadline_watcher(self):
        """Periodically flag tasks nearing their deadline and pop up overdue ones."""
        import asyncio
        while True:
            try:
                interval = int(self.settings.get("notify_check_seconds") or 60)
            except (TypeError, ValueError):
                interval = 60
            await asyncio.sleep(max(15, interval))
            if not self.settings.get("notifications_enabled"):
                continue
            try:
                self._check_deadlines()
            except Exception:
                pass

    def _check_deadlines(self):
        from core.models import TaskStatus
        just_passed = []
        for t in self.service.get_all_tasks():
            if t.status == TaskStatus.DONE or not t.due_date:
                continue
            secs = t.seconds_until_due()
            if secs is None:
                continue
            if secs < 0 and t.id not in self._notified_overdue:
                self._notified_overdue.add(t.id)
                just_passed.append(t)
        if just_passed:
            self._popup_overdue(just_passed)
        # keep "скоро" badges fresh
        if self.current_view == "kanban":
            self.refresh_all()

    def _popup_overdue(self, tasks):
        names = "\n".join(f"•  {t.title}" for t in tasks[:8])
        extra = f"\n… и ещё {len(tasks) - 8}" if len(tasks) > 8 else ""
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ic("warning"), color=COLORS["accent_red"]),
                          ft.Text("Наступил срок задач")], spacing=8),
            content=ft.Text(names + extra),
            actions=[ft.TextButton("Понятно", on_click=lambda e: self.page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _build_top_bar(self, page: ft.Page):
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

        self.search_field = ft.TextField(
            hint_text="\u041f\u043e\u0438\u0441\u043a...",
            width=200, height=36, text_size=13,
            prefix_icon=ic("search"), border_radius=8,
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
        self.sort_dropdown = ft.Dropdown(
            width=185, text_size=13,
            options=[
                ft.dropdown.Option("default", text="\u0411\u0435\u0437 \u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0438"),
                ft.dropdown.Option("priority", text="\u041f\u043e \u043f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442\u0443"),
                ft.dropdown.Option("due_date", text="\u041f\u043e \u0434\u0435\u0434\u043b\u0430\u0439\u043d\u0443"),
            ],
            value="default", filled=True,
            fill_color=COLORS["bg_button"],
            border_color=ft.Colors.TRANSPARENT, border_radius=8,
            on_select=self._on_sort,
            text_style=ft.TextStyle(size=13, height=1.0),
            content_padding=ft.Padding.only(left=10, right=6, top=0, bottom=0),
        )

        self.add_button = ft.Button(
            content="\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
            icon=ic("add"),
            on_click=lambda e: self.show_create_dialog(),
            style=ft.ButtonStyle(
                bgcolor=COLORS["accent_green"], color="#000000",
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
                    ft.IconButton(icon=ic("notifications_none"), icon_color=COLORS["text_secondary"],
                                  tooltip="Уведомления о сроках",
                                  on_click=lambda e: self.show_settings_dialog()),
                    self.add_button,
                ],
                spacing=4, alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=COLORS["bg_card"],
        )
        page.add(top_bar)

    def _build_status_bar(self, page: ft.Page):
        self.status_text = ft.Text("\u0413\u043e\u0442\u043e\u0432", size=11, color=COLORS["text_secondary"])
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
        from core.models import TaskStatus
        if self._search_query:
            q = self._search_query
            tasks = [t for t in tasks
                     if q in t.title.lower()
                     or q in t.description.lower()
                     or any(q in tag for tag in t.tags)]
        if self._sort_mode == "priority":
            prio_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            tasks = sorted(tasks, key=lambda t: prio_order.get(t.priority.value, 99))
        elif self._sort_mode == "due_date":
            tasks = sorted(tasks, key=lambda t: t.due_date or "9999-12-31")
        return tasks

    def refresh_all(self):
        from core.models import TaskStatus
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
            self.status_text.value = f"\u041d\u0430\u0439\u0434\u0435\u043d\u043e: {filtered} \u0438\u0437 {total}"
        else:
            self.status_text.value = f"\u0417\u0430\u0434\u0430\u0447: {total}"

    def show_create_dialog(self):
        from .task_dialog import show_task_dialog
        show_task_dialog(self.page, title="\u041d\u043e\u0432\u0430\u044f \u0437\u0430\u0434\u0430\u0447\u0430", on_save=self._on_create_task)

    def show_settings_dialog(self):
        s = self.settings
        enabled = ft.Switch(value=bool(s.get("notifications_enabled")),
                            label="\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u044f\u0442\u044c \u043e \u043f\u0440\u0438\u0431\u043b\u0438\u0436\u0435\u043d\u0438\u0438 \u0441\u0440\u043e\u043a\u043e\u0432")
        hours = ft.TextField(
            label="\u0417\u0430 \u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0447\u0430\u0441\u043e\u0432 \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0430\u0442\u044c",
            value=str(s.get("notify_hours_before")),
            width=200, text_size=14, border_radius=8,
        )
        auto_updates = ft.Switch(
            value=bool(s.get("check_updates_on_start")),
            label="\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u043f\u0440\u0438 \u0437\u0430\u043f\u0443\u0441\u043a\u0435",
        )
        err = ft.Text("", size=12, color=COLORS["accent_red"])

        def save(e):
            try:
                h = int(hours.value.strip())
                if not (1 <= h <= 24 * 30):
                    raise ValueError
            except ValueError:
                err.value = "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u043e \u0447\u0430\u0441\u043e\u0432 \u043e\u0442 1 \u0434\u043e 720"
                err.update()
                return
            s.update(notifications_enabled=enabled.value, notify_hours_before=h,
                     check_updates_on_start=auto_updates.value)
            self._notified_overdue.clear()
            self.page.pop_dialog()
            self.refresh_all()
            self._show_snackbar("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u044b")

        def check_updates_click(e):
            from .update_ui import check_now
            check_now(self)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                enabled,
                ft.Container(height=8),
                hours,
                ft.Text("\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u0441 \u043f\u0440\u0438\u0431\u043b\u0438\u0436\u0430\u044e\u0449\u0438\u043c\u0441\u044f \u0434\u0435\u0434\u043b\u0430\u0439\u043d\u043e\u043c \u043f\u043e\u0434\u0441\u0432\u0435\u0447\u0438\u0432\u0430\u044e\u0442\u0441\u044f; "
                        "\u043a\u043e\u0433\u0434\u0430 \u0441\u0440\u043e\u043a \u043d\u0430\u0441\u0442\u0443\u043f\u0430\u0435\u0442 \u2014 \u043f\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u043e\u043a\u043d\u043e.",
                        size=11, color=COLORS["text_secondary"]),
                ft.Divider(color=COLORS["border_color"]),
                auto_updates,
                ft.Row([
                    ft.TextButton("\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u0435\u0439\u0447\u0430\u0441", icon=ic("refresh"),
                                  on_click=check_updates_click),
                    ft.Text(f"v{_app_version()}", size=11, color=COLORS["text_secondary"]),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                err,
            ], tight=True, width=360, spacing=6),
            actions=[
                ft.TextButton("\u041e\u0442\u043c\u0435\u043d\u0430", on_click=lambda e: self.page.pop_dialog()),
                ft.Button("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", on_click=save,
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
        from core.models import TaskStatus, Priority

        def on_save(**kwargs):
            try:
                self.service.update_task(task.id, **kwargs)
                self.refresh_all()
            except ValueError as e:
                self._show_snackbar(str(e), error=True)

        show_task_dialog(self.page, title="\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
                               task=task, on_save=on_save)

    def delete_task(self, task):
        def close_dlg(e=None):
            self.page.pop_dialog()

        def on_confirm(e):
            self.service.delete_task(task.id)
            close_dlg()
            self.refresh_all()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443"),
            content=ft.Text(f'\u0423\u0434\u0430\u043b\u0438\u0442\u044c "{task.title}"?'),
            actions=[
                ft.TextButton("\u041e\u0442\u043c\u0435\u043d\u0430", on_click=close_dlg),
                ft.TextButton("\u0423\u0434\u0430\u043b\u0438\u0442\u044c", on_click=on_confirm),
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
                self._show_snackbar(f"Клонировано: {cloned.title}")
        except Exception as e:
            self._show_snackbar(str(e), error=True)

    def handle_drop(self, task, target_status_value: str):
        from core.models import TaskStatus
        STATUS_MAP = {
            "Todo": TaskStatus.TODO,
            "In Progress": TaskStatus.IN_PROGRESS,
            "Done": TaskStatus.DONE,
        }
        new_status = STATUS_MAP.get(target_status_value)
        if not new_status or new_status == task.status:
            return
        self.service.update_task_status(task.id, new_status)
        self.refresh_all()


def run_app(db_path: str = None, port: int = 8550):
    """Entry point for the Flet-based task manager.

    Args:
        db_path: Path to the tasks JSON file. If None, uses default.
        port: TCP port for the local web server.
    """
    import socket
    import webbrowser
    import flet as ft

    global DB_PATH
    if db_path:
        DB_PATH = Path(db_path)

    import os
    import time

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
                    print(f"Остановлен зависший экземпляр (PID {pid}) на порту {p}")
                except Exception:
                    pass

    if not _port_free(port):
        # 1) A healthy instance of us is already serving -> just open a tab at it.
        try:
            import urllib.request
            body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read(4096)
            if b"flutter" in body.lower() or b"flet" in body.lower():
                webbrowser.open(f"http://127.0.0.1:{port}/")
                print(f"Менеджер задач уже запущен: http://127.0.0.1:{port}/")
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
                    print(f"Порт {port} занят другим приложением, запуск на {cand}")
                    port = cand
                    break

    # IMPORTANT: a fresh TaskManagerApp per browser session. One shared instance
    # means a second tab/window overwrites self.page and the first session's
    # click handlers silently target the wrong page (the "F5 fixes it" bug).
    # The data layer (service + settings) IS shared so tabs stay consistent.
    import sys as _sys
    _src = APP_DIR / "src"
    if str(_src) not in _sys.path:
        _sys.path.insert(0, str(_src))
    from core.repository import TaskRepository
    from core.service import TaskService
    from core.settings import SettingsStore
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shared_service = TaskService(repository=TaskRepository(db_path=str(DB_PATH)))
    shared_settings = SettingsStore(str(DB_PATH.parent / "settings.json"))

    def session_main(page: ft.Page):
        TaskManagerApp(service=shared_service, settings=shared_settings).main(page)

    # Force the CanvasKit renderer: the default (AUTO -> SKWASM) needs
    # cross-origin isolation headers the local server doesn't send and renders
    # blank / grey in many browsers. CanvasKit works everywhere.
    ft.run(
        session_main,
        view=ft.AppView.WEB_BROWSER,
        port=port,
        web_renderer=ft.WebRenderer.CANVAS_KIT,
    )
