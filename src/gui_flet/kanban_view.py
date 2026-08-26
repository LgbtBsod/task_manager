"""Kanban board view with Drag-and-Drop support via Flet Draggable/DragTarget.
"""
import flet as ft
from typing import Optional, TYPE_CHECKING

from .app import COLORS, PRIORITY_COLORS

if TYPE_CHECKING:
    from .app import TaskManagerApp


STATUS_CONFIG = {
    "Todo": {"color": "#0a84ff", "icon": "radio_button_unchecked"},
    "In Progress": {"color": "#ff9f0a", "icon": "pending"},
    "Done": {"color": "#30d158", "icon": "check_circle"},
}


def _format_due_info(task) -> tuple:
    if not task.due_date:
        return "", ""
    days = task.days_until_due()
    if days is None:
        return task.due_date, "#86868b"
    if task.status.value == "Done":
        return task.due_date, "#86868b"
    if days < 0:
        return f"Просрочен: {task.due_date}", "#F44336"
    if days == 0:
        return f"Сегодня: {task.due_date}", "#ff9f0a"
    if days <= 3:
        return f"Скоро: {task.due_date}", "#ff9f0a"
    return task.due_date, "#86868b"


def _format_time(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)}m"
    h = int(hours)
    m = int((hours - h) * 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


class TaskCard(ft.Draggable):
    """A draggable task card with tags and subtask progress."""

    def __init__(self, task_id: str, task, app: 'TaskManagerApp', **kwargs):
        super().__init__(data=task_id, content=self._build_card(task, app), **kwargs)
        self.task = task

    def _build_card(self, task, app) -> ft.Control:
        priority_color = PRIORITY_COLORS.get(task.priority.value, "#FF9800")
        due_text, due_color = _format_due_info(task)

        time_text = ""
        if task.time_spent > 0:
            time_text = _format_time(task.time_spent)

        desc_preview = ""
        if task.description:
            desc_preview = task.description[:80]
            if len(task.description) > 80:
                desc_preview += "..."

        # ── Header row: type badge + title + actions ──
        type_colors = {"Bug": "#ff453a", "Story": "#bf5af2", "Epic": "#ff9f0a", "Sub-task": "#30d158"}
        type_color = type_colors.get(task.task_type, "#86868b")
        header_right = []
        if task.task_type != "Task":
            header_right.append(ft.Container(
                content=ft.Text(task.task_type, size=9, color=type_color, weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                bgcolor=f"{type_color}20", border_radius=4,
            ))
        if task.story_points is not None:
            header_right.append(ft.Container(
                content=ft.Text(f"SP:{task.story_points}", size=9, color="#86868b"),
                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                bgcolor=COLORS["bg_button"], border_radius=4,
            ))

        tag_chips = []
        for tag in task.tags[:4]:
            tag_chips.append(
                ft.Container(
                    content=ft.Text(tag, size=9, color=COLORS["accent_blue"]),
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                    bgcolor="#0a84ff20", border_radius=6,
                )
            )
        if len(task.tags) > 4:
            tag_chips.append(ft.Text(f"+{len(task.tags) - 4}", size=9, color="#86868b"))

        bottom_items = []
        if task.assignee:
            bottom_items.append(ft.Row([
                ft.Icon('person', size=12, color="#86868b"),
                ft.Text(task.assignee, size=10, color="#86868b"),
            ], spacing=3))
        if due_text:
            bottom_items.append(ft.Row([
                ft.Icon('calendar_today', size=12, color=due_color),
                ft.Text(due_text, size=10, color=due_color),
            ], spacing=3))
        if time_text:
            bottom_items.append(ft.Row([
                ft.Icon('timer_outlined', size=12, color="#86868b"),
                ft.Text(time_text, size=10, color="#86868b"),
            ], spacing=3))
        if task.comments:
            bottom_items.append(ft.Row([
                ft.Icon('chat_bubble_outline', size=12, color="#86868b"),
                ft.Text(str(len(task.comments)), size=10, color="#86868b"),
            ], spacing=3))

        subtask_info = None
        if task.subtasks:
            done_count = sum(1 for st in task.subtasks if st.done)
            total_count = len(task.subtasks)
            progress = done_count / total_count if total_count > 0 else 0
            subtask_info = ft.Row([
                ft.Icon('checklist', size=12, color="#86868b"),
                ft.Text(f"{done_count}/{total_count}", size=10, color="#86868b"),
                ft.Container(expand=1),
                ft.ProgressBar(width=60, height=4, value=progress,
                              color=COLORS["accent_green"],
                              bgcolor=COLORS["bg_button"], border_radius=2),
            ], spacing=4)

        action_btns = [
            ft.IconButton(
                icon='content_copy', icon_size=14, icon_color="#86868b",
                on_click=lambda e, t=task: app._clone_task(t),
                tooltip="Клонировать",
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
            ft.IconButton(
                icon='edit_outlined', icon_size=14, icon_color="#86868b",
                on_click=lambda e, t=task: app.show_edit_dialog(t),
                tooltip="Редактировать",
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
            ft.IconButton(
                icon='delete_outline', icon_size=14, icon_color="#86868b",
                on_click=lambda e, t=task: app.delete_task(t),
                tooltip="Удалить",
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
        ]

        card_children = [
            ft.Row([
                ft.Container(width=4, height=32, bgcolor=priority_color, border_radius=2),
                ft.Text(task.title, size=13, weight=ft.FontWeight.W_600,
                        color=COLORS["text_primary"], expand=True,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                *header_right,
            ], spacing=8),
        ]

        if desc_preview:
            card_children.append(ft.Text(desc_preview, size=11, color=COLORS["text_secondary"],
                                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS))

        if tag_chips:
            card_children.append(ft.Row(tag_chips, spacing=4))

        card_children.append(
            ft.Row([
                ft.Column(bottom_items, spacing=3),
                ft.Container(expand=True),
                ft.Row(action_btns, spacing=0),
            ]) if (bottom_items or action_btns) else ft.Container()
        )

        if subtask_info:
            card_children.append(ft.Container(height=4))
            card_children.append(subtask_info)

        card = ft.Container(
            content=ft.Column(card_children, spacing=5),
            padding=12, bgcolor=COLORS["bg_card"], border_radius=12,
        )
        return card


class DropColumn:
    """A Kanban column that acts as a DragTarget."""

    def __init__(self, app: 'TaskManagerApp', title: str, color: str,
                 status_value: str, icon: str = ""):
        self.app = app
        self.title = title
        self.color = color
        self.status_value = status_value
        self.icon = icon

    def build(self) -> ft.Control:
        self._badge = ft.Text("0", size=12, color=COLORS["text_secondary"])

        header = ft.Container(
            content=ft.Row([
                ft.Icon(self.icon, size=16, color=self.color),
                ft.Text(self.title, size=13, weight=ft.FontWeight.BOLD,
                        color=COLORS["text_primary"]),
                ft.Container(expand=True),
                ft.Container(content=self._badge,
                             padding=ft.padding.symmetric(horizontal=8, vertical=2),
                             bgcolor=COLORS["bg_button"], border_radius=10),
            ], spacing=8),
            padding=ft.padding.only(left=8, right=8, top=12, bottom=8),
        )

        self._list_view = ft.ListView(expand=True, spacing=4,
                                         padding=ft.padding.only(left=8, right=8, bottom=8),
                                         auto_scroll=True)

        self._border_container = ft.Container(
            content=self._list_view, expand=True,
            border=ft.border.all(1, COLORS["border_color"]),
            border_radius=12, bgcolor=ft.Colors.TRANSPARENT,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self._drag_target = ft.DragTarget(
            group="kanban", content=self._border_container,
            on_accept=self._on_accept, on_will_accept=self._on_will_accept,
            on_leave=self._on_leave,
        )

        return ft.Column(controls=[header, self._drag_target], spacing=0, expand=True)

    def _on_will_accept(self, e):
        self._border_container.border = ft.border.all(2, COLORS["accent_blue"])
        self._border_container.update()
        e.control.update()

    def _on_leave(self, e):
        self._border_container.border = ft.border.all(1, COLORS["border_color"])
        self._border_container.update()

    def _on_accept(self, e):
        self._border_container.border = ft.border.all(1, COLORS["border_color"])
        self._border_container.update()

        task_id = e.data if e.data else ""
        if task_id:
            task = self.app.service.get_task(task_id)
            if task:
                self.app.handle_drop(task, self.status_value)

    def set_cards(self, cards: list):
        self._list_view.controls = [c for c in cards]
        self._badge.value = str(len(cards))
        self._list_view.update()
        self._badge.update()


class KanbanView:
    """Kanban board view with DnD support."""

    def __init__(self, app: 'TaskManagerApp'):
        self.app = app
        self.container: Optional[ft.Control] = None
        self.todo_col: Optional[DropColumn] = None
        self.progress_col: Optional[DropColumn] = None
        self.done_col: Optional[DropColumn] = None

    def build(self):
        self.todo_col = DropColumn(self.app, "Todo", "#0a84ff", "Todo", icon="radio_button_unchecked")
        self.progress_col = DropColumn(self.app, "In Progress", "#ff9f0a", "In Progress", icon="pending")
        self.done_col = DropColumn(self.app, "Done", "#30d158", "Done", icon="check_circle")

        self.container = ft.Container(
            content=ft.Row([
                self.todo_col.build(),
                ft.Container(width=6),
                self.progress_col.build(),
                ft.Container(width=6),
                self.done_col.build(),
            ], spacing=0, expand=True),
            padding=12, expand=True,
        )

    def update_tasks(self, todo, in_progress, done):
        if self.todo_col is None:
            return
        self.todo_col.set_cards([TaskCard(t.id, t, self.app) for t in todo])
        self.progress_col.set_cards([TaskCard(t.id, t, self.app) for t in in_progress])
        self.done_col.set_cards([TaskCard(t.id, t, self.app) for t in done])
