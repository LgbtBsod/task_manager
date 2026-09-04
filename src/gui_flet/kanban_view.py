"""Kanban board view with Drag-and-Drop support via Flet Draggable/DragTarget.
"""
from typing import TYPE_CHECKING

import flet as ft

from core import strings as L

from ._ui import safe_update
from .app import COLORS, ic
from .palette import RADIUS_CARD_COMPACT, RADIUS_CHIP, elevation, readable_variant

if TYPE_CHECKING:
    from .app import TaskManagerApp


def _format_due_info(task) -> tuple:
    if not task.due_date:
        return "", ""
    from core.datetimeutil import display as _dsp
    shown = _dsp(task.due_date)
    days = task.days_until_due()
    if days is None or task.status.value == "Done":
        return shown, COLORS["text_secondary"]
    secs = task.seconds_until_due()
    # readable_variant: at 9-10sp these accents-as-text can fall short of the
    # 4.5:1 text bar (confirmed against Fiori Horizon's own tokens) even where
    # they're fine as a fill/stripe — nudge only when actually needed.
    if secs is not None and secs < 0:
        return (L.UI.D_OVERDUE_ON.format(when=shown),
                readable_variant(COLORS["accent_red"], COLORS["bg_card"]))
    if days == 0:
        return (L.UI.D_TODAY.format(when=shown),
                readable_variant(COLORS["accent_orange"], COLORS["bg_card"]))
    if days <= 3:
        return (L.UI.D_SOON.format(when=shown),
                readable_variant(COLORS["accent_orange"], COLORS["bg_card"]))
    return shown, COLORS["text_secondary"]




def _deadline_badge(task, app):
    """A prominent chip when a task is overdue or its deadline is within the
    configured warning window. Returns an ft.Container or None."""
    if not task.due_date or task.status.value == "Done":
        return None
    secs = task.seconds_until_due()
    if secs is None:
        return None
    window = app.notify_hours_before() * 3600
    if secs < 0:
        text, bg = L.UI.D_OVERDUE, COLORS["accent_red"]
    elif secs <= window:
        hrs = secs / 3600
        if hrs < 1:
            text = L.UI.D_MINUTES.format(n=int(secs // 60))
        elif hrs < 36:
            text = L.UI.D_HOURS.format(n=int(hrs))
        else:
            text = L.UI.D_DAYS.format(n=int(hrs // 24))
        bg = COLORS["accent_orange"]
    else:
        return None
    return ft.Container(
        content=ft.Row([ft.Icon(ic("schedule"), size=10, color="#ffffff"),
                        ft.Text(text, size=9, color="#ffffff", weight=ft.FontWeight.BOLD)],
                       spacing=3, tight=True),
        padding=ft.Padding.symmetric(horizontal=5, vertical=2),
        bgcolor=bg, border_radius=RADIUS_CHIP,
    )


class TaskCard:
    """A draggable task card with tags and subtask progress."""

    def __init__(self, task_id: str, task, app: 'TaskManagerApp', group: str = "tasks"):
        self.task_id = task_id
        self.task = task
        self.app = app
        self.group = group
        self.control = self._build_draggable(task, app)

    def _build_draggable(self, task, app) -> ft.Draggable:
        """Build the draggable wrapper around the card content.

        The real card is built once. The drag placeholder and the drag
        "feedback" (what follows the cursor) are cheap stand-ins so a board
        with dozens of tasks doesn't serialize the full card tree 3x each.
        """
        priority_color = task.priority.color
        return ft.Draggable(
            group=self.group,
            data=self.task_id,
            content=self._build_card(task, app),
            content_when_dragging=ft.Container(
                height=64, border_radius=RADIUS_CARD_COMPACT,
                bgcolor=COLORS["bg_button"], opacity=0.4,
            ),
            content_feedback=ft.Container(
                content=ft.Row([
                    ft.Container(width=4, height=28, bgcolor=priority_color, border_radius=2),
                    ft.Text(task.title, size=13, weight=ft.FontWeight.W_600,
                            color=COLORS["text_primary"], max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=8),
                bgcolor=COLORS["bg_card"], border_radius=RADIUS_CARD_COMPACT,
                padding=12, width=260,
            ),
        )

    def _build_card(self, task, app) -> ft.Control:
        priority_color = task.priority.color
        due_text, due_color = _format_due_info(task)

        time_text = ""
        if task.time_spent > 0:
            time_text = L.format_duration(task.time_spent)

        desc_preview = ""
        if task.description:
            desc_preview = task.description[:80]
            if len(task.description) > 80:
                desc_preview += "..."

        # ── Header row: type badge + title + actions ──
        type_color = L.type_color(task.task_type)
        header_right = []
        if app.service.is_blocked(task):
            blockers = app.service.blocking_tasks(task)
            header_right.append(ft.Container(
                content=ft.Row([ft.Icon(ic("lock"), size=10, color="#ffffff"),
                                ft.Text(L.UI.D_BLOCKED, size=9, color="#ffffff",
                                        weight=ft.FontWeight.BOLD)],
                               spacing=3, tight=True),
                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                bgcolor=COLORS["text_secondary"], border_radius=RADIUS_CHIP,
                tooltip=L.UI.D_BLOCKED_TOOLTIP.format(
                    titles=", ".join(b.title for b in blockers[:3])),
            ))
        if task.on_hold:
            header_right.append(ft.Container(
                content=ft.Text(L.UI.D_ON_HOLD, size=9, color=COLORS["text_secondary"],
                                weight=ft.FontWeight.W_600),
                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                bgcolor=COLORS["bg_button"], border_radius=RADIUS_CHIP,
            ))
        _dbadge = _deadline_badge(task, app)
        if _dbadge is not None:
            header_right.append(_dbadge)
        if task.task_type != "Task":
            header_right.append(ft.Container(
                content=ft.Text(L.task_type(task.task_type), size=9, color=type_color, weight=ft.FontWeight.W_600),
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                bgcolor=ft.Colors.with_opacity(0.15, type_color), border_radius=RADIUS_CHIP,
            ))
        if task.story_points is not None:
            header_right.append(ft.Container(
                content=ft.Text(f"{L.STORY_POINTS}:{task.story_points}", size=9, color=COLORS["text_secondary"]),
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                bgcolor=COLORS["bg_button"], border_radius=RADIUS_CHIP,
            ))

        tag_chips = []
        _tag_text_color = readable_variant(COLORS["accent_blue"], COLORS["bg_card"])
        for tag in task.tags[:4]:
            tag_chips.append(
                ft.Container(
                    content=ft.Text(tag, size=9, color=_tag_text_color),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    bgcolor=ft.Colors.with_opacity(0.15, COLORS["accent_blue"]), border_radius=6,
                )
            )
        if len(task.tags) > 4:
            tag_chips.append(ft.Text(f"+{len(task.tags) - 4}", size=9, color=COLORS["text_secondary"]))

        bottom_items = []
        if task.assignee:
            bottom_items.append(ft.Row([
                ft.Icon(ic('person'), size=12, color=COLORS["text_secondary"]),
                ft.Text(task.assignee, size=10, color=COLORS["text_secondary"]),
            ], spacing=3))
        if due_text:
            bottom_items.append(ft.Row([
                ft.Icon(ic('calendar_today'), size=12, color=due_color),
                ft.Text(due_text, size=10, color=due_color),
            ], spacing=3))
        if time_text:
            bottom_items.append(ft.Row([
                ft.Icon(ic('timer_outlined'), size=12, color=COLORS["text_secondary"]),
                ft.Text(time_text, size=10, color=COLORS["text_secondary"]),
            ], spacing=3))
        if task.comments:
            bottom_items.append(ft.Row([
                ft.Icon(ic('chat_bubble_outline'), size=12, color=COLORS["text_secondary"]),
                ft.Text(str(len(task.comments)), size=10, color=COLORS["text_secondary"]),
            ], spacing=3))

        subtask_info = None
        if task.subtasks:
            done_count = sum(1 for st in task.subtasks if st.done)
            total_count = len(task.subtasks)
            progress = done_count / total_count if total_count > 0 else 0
            subtask_info = ft.Row([
                ft.Icon(ic('checklist'), size=12, color=COLORS["text_secondary"]),
                ft.Text(f"{done_count}/{total_count}", size=10, color=COLORS["text_secondary"]),
                ft.Container(expand=1),
                ft.ProgressBar(width=60, height=4, value=progress,
                              color=COLORS["accent_green"],
                              bgcolor=COLORS["bg_button"], border_radius=2),
            ], spacing=4)

        action_btns = [
            ft.IconButton(
                icon=ic('play_circle_outline' if task.on_hold else 'pause_circle_outline'),
                icon_size=14, icon_color=COLORS["text_secondary"],
                on_click=lambda e, t=task: app.toggle_hold(t),
                tooltip=L.UI.ACTION_RESUME if task.on_hold else L.UI.ACTION_PAUSE,
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
            ft.IconButton(
                icon=ic('content_copy'), icon_size=14, icon_color=COLORS["text_secondary"],
                on_click=lambda e, t=task: app._clone_task(t),
                tooltip=L.UI.CLONE,
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
            ft.IconButton(
                icon=ic('edit_outlined'), icon_size=14, icon_color=COLORS["text_secondary"],
                on_click=lambda e, t=task: app.show_edit_dialog(t),
                tooltip=L.UI.EDIT,
                style=ft.ButtonStyle(overlay_color=ft.Colors.TRANSPARENT, padding=2),
            ),
            ft.IconButton(
                icon=ic('delete_outline'), icon_size=14, icon_color=COLORS["text_secondary"],
                on_click=lambda e, t=task: app.delete_task(t),
                tooltip=L.UI.DELETE,
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
            padding=12, bgcolor=COLORS["bg_card"], border_radius=RADIUS_CARD_COMPACT,
            shadow=elevation(1),
            opacity=0.6 if task.on_hold else 1.0,
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
                ft.Icon(ic(self.icon), size=16, color=self.color),
                ft.Text(self.title, size=13, weight=ft.FontWeight.BOLD,
                        color=COLORS["text_primary"]),
                ft.Container(expand=True),
                ft.Container(content=self._badge,
                             padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                             bgcolor=COLORS["bg_button"], border_radius=10),
            ], spacing=8),
            padding=ft.Padding.only(left=8, right=8, top=12, bottom=8),
            bgcolor=COLORS["bg_dark"],
            border_radius=8,
        )

        # ListView keeps the drop area filling the whole column even with zero
        # cards (a plain Column would collapse to nothing).
        self._list_view = ft.ListView(spacing=8, padding=0, expand=True)

        # The ENTIRE column (header + card list) is the drop target, so tasks
        # can be dropped anywhere on a column, empty or not.
        self._drop_body = ft.Container(
            content=ft.Column([header, self._list_view], spacing=8, expand=True),
            padding=10,
            border=ft.Border.all(1, COLORS["border_color"]),
            border_radius=RADIUS_CARD_COMPACT,
            bgcolor=COLORS["bg_card"],
            expand=True,
        )

        self._border_container = ft.DragTarget(
            group="tasks",
            expand=True,
            content=self._drop_body,
            on_accept=lambda e: self._on_drop(e),
            on_will_accept=lambda e: self._on_will_accept(e),
            on_leave=lambda e: self._on_leave(e),
        )

        # expand=1 on all three columns -> they split the board width evenly
        # and fill the screen (no fixed width, no empty gutter on the right).
        return ft.Container(
            content=self._border_container,
            expand=1,
        )

    def _on_will_accept(self, e):
        """Called when a draggable of a matching group hovers the target."""
        e.control.content.border = ft.Border.all(2, self.color)
        e.control.update()

    def _on_leave(self, e):
        """Called when the draggable leaves the target."""
        e.control.content.border = ft.Border.all(1, COLORS["border_color"])
        e.control.update()

    def _resolve_dragged_task_id(self, e):
        """Flet 0.86: the drop event carries src_id, not the Draggable's data."""
        src = getattr(e, "src", None)
        if src is None and getattr(e, "src_id", None) is not None:
            page = getattr(e, "page", None) or getattr(e.control, "page", None)
            if page is not None:
                src = page.get_control(e.src_id)
        return getattr(src, "data", None)

    def _on_drop(self, e):
        """Called when a draggable is dropped on the target."""
        e.control.content.border = ft.Border.all(1, COLORS["border_color"])
        task_id = self._resolve_dragged_task_id(e)
        if task_id:
            task = self.app.service.get_task(task_id)
            if task:
                self.app.handle_drop(task, self.status_value)
        e.control.update()

    def set_cards(self, cards: list):
        self._list_view.controls = [c.control for c in cards]
        self._badge.value = str(len(cards))
        # Repaint now if mounted; pre-mount callers rely on their page.update().
        safe_update(self._list_view, self._badge)


class KanbanView:
    """Kanban board view with DnD support."""

    def __init__(self, app: 'TaskManagerApp'):
        self.app = app
        self.container: ft.Control | None = None
        self.todo_col: DropColumn | None = None
        self.progress_col: DropColumn | None = None
        self.done_col: DropColumn | None = None

    def build(self):
        def _col(value: str) -> DropColumn:
            icon, ckey = L.status_style(value)
            return DropColumn(self.app, L.STATUS_LABEL[value], COLORS[ckey], value, icon=icon)

        self.todo_col = _col("Todo")
        self.progress_col = _col("In Progress")
        self.done_col = _col("Done")

        self.container = ft.Container(
            content=ft.Row(
                [
                    self.todo_col.build(),
                    self.progress_col.build(),
                    self.done_col.build(),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=12,
            bgcolor=COLORS["bg_dark"],
            expand=True,
        )

    def update_tasks(self, todo, in_progress, done):
        if self.todo_col is None:
            return
        self.todo_col.set_cards([TaskCard(t.id, t, self.app) for t in todo])
        self.progress_col.set_cards([TaskCard(t.id, t, self.app) for t in in_progress])
        self.done_col.set_cards([TaskCard(t.id, t, self.app) for t in done])
