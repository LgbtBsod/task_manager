"""Dashboard view with statistics, priority breakdown, type breakdown, team workload, and progress tracking."""
import flet as ft
from typing import Optional, TYPE_CHECKING

from .app import COLORS

if TYPE_CHECKING:
    from .app import TaskManagerApp


class StatCard(ft.Container):
    """A single statistic card with title, value, subtitle, and accent color."""

    def __init__(self, title: str, value: str, color: str, subtitle: str = "",
                 icon: str = "", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.value_text = value
        self.subtitle_text = subtitle
        self.accent_color = color
        self.icon_name = icon
        self.content = self._build()

    def _build(self) -> ft.Control:
        header_row = []
        if self.icon_name:
            header_row.append(ft.Icon(self.icon_name, size=20, color=self.accent_color))
        header_row.append(ft.Text(self.title_text, size=12, color=COLORS["text_secondary"]))
        self._value_label = ft.Text(self.value_text, size=32, weight=ft.FontWeight.BOLD,
                                       color=self.accent_color)
        children = [ft.Row(header_row, spacing=6), self._value_label]
        if self.subtitle_text:
            self._subtitle_label = ft.Text(self.subtitle_text, size=11, color=COLORS["text_secondary"])
            children.append(self._subtitle_label)
        return ft.Column(children, spacing=2)

    def set_value(self, value: str, subtitle: str = ""):
        self._value_label.value = value
        self._value_label.update()
        if subtitle and hasattr(self, '_subtitle_label'):
            self._subtitle_label.value = subtitle
            self._subtitle_label.update()


class PriorityBar(ft.Container):
    """A horizontal bar showing count and proportion for a priority level."""

    def __init__(self, label: str, color: str, count: int, total: int, **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self.color = color
        self.count = count
        self.total = total
        self.content = self._build()

    def _build(self) -> ft.Control:
        pct = (self.count / self.total * 100) if self.total > 0 else 0
        self._count_text = ft.Text(f"{self.label}: {self.count}", size=13, color=COLORS["text_primary"])
        self._pct_text = ft.Text(f"{pct:.0f}%", size=12, color=COLORS["text_secondary"])
        self._bar = ft.Container(height=8, width=max(pct * 3, 0), bgcolor=self.color, border_radius=4)
        return ft.Column([
            ft.Row([self._count_text, ft.Container(expand=True), self._pct_text], spacing=8),
            ft.Container(content=self._bar, bgcolor=COLORS["bg_button"], border_radius=4, height=8,
                         clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
        ], spacing=4)

    def update_data(self, count: int, total: int):
        self.count = count
        self.total = total
        pct = (count / total * 100) if total > 0 else 0
        self._count_text.value = f"{self.label}: {count}"
        self._pct_text.value = f"{pct:.0f}%"
        self._bar.width = max(pct * 3, 0)
        self._count_text.update()
        self._pct_text.update()
        self._bar.update()


class TypeBar(ft.Container):
    """A horizontal bar for task type breakdown."""
    def __init__(self, label: str, color: str, count: int, total: int, **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self.color = color
        self.count = count
        self.total = total
        self.content = self._build()

    def _build(self) -> ft.Control:
        pct = (self.count / self.total * 100) if self.total > 0 else 0
        self._count_text = ft.Text(f"{self.label}: {self.count}", size=13, color=COLORS["text_primary"])
        self._pct_text = ft.Text(f"{pct:.0f}%", size=12, color=COLORS["text_secondary"])
        self._bar = ft.Container(height=8, width=max(pct * 3, 0), bgcolor=self.color, border_radius=4)
        return ft.Column([
            ft.Row([self._count_text, ft.Container(expand=True), self._pct_text], spacing=8),
            ft.Container(content=self._bar, bgcolor=COLORS["bg_button"], border_radius=4, height=8,
                         clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
        ], spacing=4)

    def update_data(self, count: int, total: int):
        self.count = count
        self.total = total
        pct = (count / total * 100) if total > 0 else 0
        self._count_text.value = f"{self.label}: {count}"
        self._pct_text.value = f"{pct:.0f}%"
        self._bar.width = max(pct * 3, 0)
        self._count_text.update()
        self._pct_text.update()
        self._bar.update()


class DashboardView:
    """Dashboard with statistics, priority/type breakdown, team workload, and progress."""

    def __init__(self, app: 'TaskManagerApp'):
        self.app = app
        self.container: Optional[ft.Control] = None
        self.stat_total: Optional[StatCard] = None
        self.stat_done: Optional[StatCard] = None
        self.stat_progress: Optional[StatCard] = None
        self.stat_overdue: Optional[StatCard] = None
        self.prio_bars: dict[str, PriorityBar] = {}
        self.type_bars: dict[str, TypeBar] = {}
        self._status_bars: dict[str, ft.Container] = {}
        self._status_labels: dict[str, ft.Text] = {}

    def build(self):
        self.stat_total = StatCard("Всего", "0", COLORS["accent_blue"], icon="task_alt",
                                     bgcolor=COLORS["bg_card"], border_radius=16, padding=20)
        self.stat_done = StatCard("Выполнено", "0", COLORS["accent_green"], icon="check_circle",
                                    bgcolor=COLORS["bg_card"], border_radius=16, padding=20)
        self.stat_progress = StatCard("В работе", "0", COLORS["accent_orange"], icon="pending",
                                        bgcolor=COLORS["bg_card"], border_radius=16, padding=20)
        self.stat_overdue = StatCard("Просрочено", "0", COLORS["accent_red"], icon="warning",
                                      bgcolor=COLORS["bg_card"], border_radius=16, padding=20)

        prio_section = []
        for prio, color in [("Low", "#4CAF50"), ("Medium", "#FF9800"), ("High", "#F44336"), ("Critical", "#FF1744")]:
            bar = PriorityBar(prio, color, 0, 1, padding=ft.padding.only(bottom=12))
            self.prio_bars[prio] = bar
            prio_section.append(bar)

        type_section = []
        type_config = [("Task", "#86868b"), ("Bug", "#ff453a"), ("Story", "#bf5af2"), ("Epic", "#ff9f0a"), ("Sub-task", "#30d158")]
        for ttype, color in type_config:
            bar = TypeBar(ttype, color, 0, 1, padding=ft.padding.only(bottom=12))
            self.type_bars[ttype] = bar
            type_section.append(bar)

        status_section = []
        status_config = [
            ("todo", "Todo", COLORS["accent_blue"]),
            ("in_progress", "В работе", COLORS["accent_orange"]),
            ("done", "Готово", COLORS["accent_green"]),
        ]
        for key, label, color in status_config:
            lbl = ft.Text(f"{label}: 0", size=13, color=COLORS["text_primary"])
            self._status_labels[key] = lbl
            bar_container = ft.Container(height=8, width=0, bgcolor=color, border_radius=4)
            self._status_bars[key] = bar_container
            status_section.append(ft.Column([
                ft.Row([lbl, ft.Container(expand=True)], spacing=8),
                ft.Container(content=bar_container, bgcolor=COLORS["bg_button"],
                             border_radius=4, height=8, clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
            ], spacing=4))

        self._workload_column = ft.Column(spacing=8)

        self.container = ft.Column([
            ft.Container(content=ft.Text("Dashboard", size=24, weight=ft.FontWeight.BOLD,
                                              color=COLORS["text_primary"]),
                           padding=ft.padding.only(left=20, top=15, bottom=20)),
            ft.Container(content=ft.Row([
                ft.Container(expand=1, content=self.stat_total),
                ft.Container(width=8),
                ft.Container(expand=1, content=self.stat_done),
                ft.Container(width=8),
                ft.Container(expand=1, content=self.stat_progress),
                ft.Container(width=8),
                ft.Container(expand=1, content=self.stat_overdue),
            ], spacing=0), padding=ft.padding.symmetric(horizontal=20)),
            ft.Container(height=16),
            ft.Container(content=ft.Row([
                ft.Container(content=ft.Column([
                    ft.Text("По приоритету", size=15, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                    ft.Container(height=8), *prio_section,
                ]), expand=1, padding=20, bgcolor=COLORS["bg_card"], border_radius=16),
                ft.Container(width=12),
                ft.Container(content=ft.Column([
                    ft.Text("По типу", size=15, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                    ft.Container(height=8), *type_section,
                ]), expand=1, padding=20, bgcolor=COLORS["bg_card"], border_radius=16),
            ], spacing=0), padding=ft.padding.symmetric(horizontal=20)),
            ft.Container(height=16),
            ft.Container(content=ft.Row([
                ft.Container(content=ft.Column([
                    ft.Text("По статусу", size=15, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                    ft.Container(height=8), *status_section,
                ]), expand=1, padding=20, bgcolor=COLORS["bg_card"], border_radius=16),
                ft.Container(width=12),
                ft.Container(content=ft.Column([
                    ft.Text("Нагрузка на команду", size=15, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                    ft.Container(height=8),
                ]), expand=1, padding=20, bgcolor=COLORS["bg_card"], border_radius=16),
            ], spacing=0), padding=ft.padding.symmetric(horizontal=20)),
            ft.Container(height=16),
            ft.Container(content=ft.Column([
                ft.Row([
                    ft.Text("Прогресс выполнения", size=15, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
                    ft.Container(expand=True),
                    ft.Text("Затрачено времени", size=13, color=COLORS["text_secondary"]),
                ]),
                ft.Container(height=8), self._build_progress_bar(),
            ]), padding=20, bgcolor=COLORS["bg_card"], border_radius=16,
            margin=ft.margin.only(left=20, right=20)),
            ft.Container(height=16),
        ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    def _build_progress_bar(self) -> ft.Control:
        self._progress_bar = ft.ProgressBar(width=400, height=10, color=COLORS["accent_green"],
                                              bgcolor=COLORS["bg_button"], border_radius=5)
        self._progress_label = ft.Text("0%", size=14, weight=ft.FontWeight.W_600,
                                          color=COLORS["text_primary"])
        self._time_label = ft.Text("0h", size=13, color=COLORS["text_secondary"])
        return ft.Row([
            ft.Container(expand=1, content=self._progress_bar),
            self._progress_label,
            ft.Container(width=16),
            self._time_label,
        ], spacing=12)

    def refresh(self):
        stats = self.app.service.get_statistics()
        total = stats["total"]

        if self.stat_total:
            self.stat_total.set_value(str(total))
            self.stat_done.set_value(str(stats["by_status"]["done"]))
            self.stat_progress.set_value(str(stats["by_status"]["in_progress"]))
            self.stat_overdue.set_value(str(stats["overdue"]))

        for prio, key in [("Low", "low"), ("Medium", "medium"), ("High", "high"), ("Critical", "critical")]:
            if prio in self.prio_bars:
                self.prio_bars[prio].update_data(stats['by_priority'].get(key, 0), total)

        all_tasks = self.app.service.get_all_tasks()
        type_counts = {}
        for t in all_tasks:
            type_counts[t.task_type] = type_counts.get(t.task_type, 0) + 1
        for ttype, bar in self.type_bars.items():
            bar.update_data(type_counts.get(ttype, 0), total)

        status_map = {
            "todo": stats["by_status"]["todo"],
            "in_progress": stats["by_status"]["in_progress"],
            "done": stats["by_status"]["done"],
        }
        status_labels_map = {"todo": "Todo", "in_progress": "В работе", "done": "Готово"}
        for key, count in status_map.items():
            pct = (count / total * 100) if total > 0 else 0
            if key in self._status_labels:
                self._status_labels[key].value = f"{status_labels_map[key]}: {count}"
                self._status_labels[key].update()
            if key in self._status_bars:
                self._status_bars[key].width = max(pct * 3, 0)
                self._status_bars[key].update()

        self._update_workload()

        if hasattr(self, '_progress_bar'):
            rate = stats['completion_rate']
            self._progress_bar.value = rate / 100
            self._progress_label.value = f"{rate}%"
            self._time_label.value = _format_time(stats['total_time_spent'])
            self._progress_bar.update()
            self._progress_label.update()
            self._time_label.update()

    def _update_workload(self):
        """Update team workload section."""
        try:
            workload = self.app.service.get_team_workload()
            # Clear existing content except the title + spacing
            while len(self._workload_column.controls) > 2:
                self._workload_column.controls.pop()
            if not workload:
                return
            for w in workload:
                name = w["assignee"]
                total = w["total"]
                in_prog = w["in_progress"]
                sp = w["story_points_sum"]
                time_s = w["total_time"]
                row = ft.Row([
                    ft.Icon("person", size=14, color=COLORS["accent_blue"]),
                    ft.Text(name, size=13, weight=ft.FontWeight.W_600, color=COLORS["text_primary"], width=100),
                    ft.Container(expand=True),
                    ft.Text(f"{total} задач", size=12, color=COLORS["text_secondary"]),
                    ft.Container(width=12),
                    ft.Text(f"{in_prog} в работе", size=12,
                            color=COLORS["accent_orange"] if in_prog > 0 else COLORS["text_secondary"]),
                    ft.Container(width=12),
                    ft.Text(f"SP:{sp}" if sp else "", size=12, color=COLORS["accent_purple"]),
                    ft.Container(width=12),
                    ft.Text(_format_time(time_s) if time_s > 0 else "", size=12, color=COLORS["text_secondary"]),
                ], spacing=4)
                self._workload_column.controls.append(row)
            self._workload_column.update()
        except Exception:
            pass


def _format_time(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)}m"
    h = int(hours)
    m = int((hours - h) * 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"
