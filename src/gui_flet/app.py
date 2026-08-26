"""Flet-based Task Manager application.
Main app module with routing, theme, and view switching.
"""
import flet as ft
from pathlib import Path
from typing import Optional

APP_DIR = Path(__file__).parent.parent.parent
DB_PATH = APP_DIR / "tasks.json"

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


class TaskManagerApp:
    """Flet Task Manager application."""

    def __init__(self):
        self.service = None
        self.page: Optional[ft.Page] = None
        self.current_view: str = "kanban"
        self._search_query: str = ""
        self._sort_mode: str = "default"

    def init_service(self):
        import sys
        src_path = APP_DIR / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        from core.repository import TaskRepository
        from core.service import TaskService
        self.service = TaskService(repository=TaskRepository(db_path=str(DB_PATH)))

    def main(self, page: ft.Page):
        self.init_service()
        self.page = page

        page.title = "Task Manager"
        page.theme = DARK_THEME
        page.dark_theme = DARK_THEME
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = COLORS["bg_dark"]
        page.padding = 0
        page.spacing = 0

        self.views_container = ft.Column(spacing=0, expand=True)

        self._build_top_bar(page)
        page.add(self.views_container)
        self._build_status_bar(page)

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

        self.switch_view("kanban")
        page.update()

    def _build_top_bar(self, page: ft.Page):
        self.nav_buttons = {}
        nav_items = [
            ("kanban", "Kanban", "view_kanban"),
            ("gantt", "Gantt", "bar_chart"),
            ("dashboard", "Dashboard", "dashboard"),
        ]

        nav_buttons_row = []
        for view_id, label, icon in nav_items:
            btn = ft.Button(
                content=label,
                icon=icon,
                on_click=lambda e, v=view_id: self.switch_view(v),
                style=ft.ButtonStyle(
                    color=ft.Colors.TRANSPARENT,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_500),
                ),
            )
            self.nav_buttons[view_id] = btn
            nav_buttons_row.append(btn)

        self.search_field = ft.TextField(
            hint_text="\u041f\u043e\u0438\u0441\u043a...",
            width=200, height=36, text_size=13,
            prefix_icon="search", border_radius=8,
            filled=True, fill_color=COLORS["bg_button"],
            focused_bgcolor=COLORS["bg_card_hover"],
            border_color=ft.Colors.TRANSPARENT,
            on_change=self._on_search,
            content_padding=ft.Padding.only(left=36, top=4, bottom=4),
        )

        self.sort_dropdown = ft.Dropdown(
            width=120, height=36, text_size=13,
            options=[
                ft.dropdown.Option("default", text="\u0411\u0435\u0437 \u0441\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u043a\u0438"),
                ft.dropdown.Option("priority", text="\u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442"),
                ft.dropdown.Option("due_date", text="\u0414\u0435\u0434\u043b\u0430\u0439\u043d"),
            ],
            value="default", filled=True,
            fill_color=COLORS["bg_button"],
            border_color=ft.Colors.TRANSPARENT, border_radius=8,
            on_select=self._on_sort,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        )

        self.add_button = ft.Button(
            content="\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
            icon="add",
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
                    ft.Text("Task Manager", size=18, weight=ft.FontWeight.BOLD,
                            color=COLORS["text_primary"]),
                    ft.Container(width=20),
                    *nav_buttons_row,
                    ft.Container(expand=True),
                    self.search_field,
                    self.sort_dropdown,
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
                controls=[self.status_text, ft.Container(expand=True)], spacing=0,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=6),
            bgcolor=COLORS["bg_card"],
        )
        page.add(status_bar)

    def switch_view(self, view_name: str):
        self.current_view = view_name

        for vid, btn in self.nav_buttons.items():
            if vid == view_name:
                btn.style = ft.ButtonStyle(
                    bgcolor=COLORS["accent_blue"], color="#ffffff",
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_500),
                )
            else:
                btn.style = ft.ButtonStyle(
                    color=ft.Colors.TRANSPARENT,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_500),
                )
            btn.update()

        self.views_container.controls.clear()
        view = self.views_map.get(view_name)
        if view:
            view.build()
            self.views_container.controls.append(view.container)
            if view_name == "gantt":
                self.gantt_view.refresh()
            elif view_name == "dashboard":
                self.dashboard_view.refresh()

        self.views_container.update()
        self.refresh_status_bar()

    def _on_search(self, e):
        self._search_query = self.search_field.value.strip().lower() if self.search_field.value else ""
        self.refresh_all()

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
            prio_order = {"High": 0, "Medium": 1, "Low": 2}
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

    def refresh_status_bar(self):
        stats = self.service.get_statistics()
        total = stats["total"]
        if self._search_query:
            filtered = len(self._filter_and_sort(self.service.get_all_tasks()))
            self.status_text.value = f"\u041d\u0430\u0439\u0434\u0435\u043d\u043e: {filtered} \u0438\u0437 {total}"
        else:
            self.status_text.value = f"\u0417\u0430\u0434\u0430\u0447: {total}"
        self.status_text.update()

    def show_create_dialog(self):
        from .task_dialog import show_task_dialog
        show_task_dialog(self.page, title="\u041d\u043e\u0432\u0430\u044f \u0437\u0430\u0434\u0430\u0447\u0430", on_save=self._on_create_task)

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
        def on_confirm(e):
            self.service.delete_task(task.id)
            self.refresh_all()
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0437\u0430\u0434\u0430\u0447\u0443"),
            content=ft.Text(f'\u0423\u0434\u0430\u043b\u0438\u0442\u044c "{task.title}"?'),
            actions=[
                ft.TextButton("\u041e\u0442\u043c\u0435\u043d\u0430", on_click=lambda e: close_dlg(e)),
                ft.TextButton("\u0423\u0434\u0430\u043b\u0438\u0442\u044c", on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

        def close_dlg(e):
            dlg.open = False
            self.page.update()

    def _show_snackbar(self, message: str, error: bool = False):
        snack = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=COLORS["accent_red"] if error else COLORS["accent_green"],
            duration=3000,
        )
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

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


def run_app(db_path: str = None):
    """Entry point for the Flet-based task manager.

    Args:
        db_path: Path to the tasks JSON file. If None, uses default.
    """
    import flet as ft
    global DB_PATH
    if db_path:
        DB_PATH = Path(db_path)
    app = TaskManagerApp()
    ft.app(target=app.main, view=ft.AppView.WEB_BROWSER, port=8550)
