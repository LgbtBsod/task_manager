"""Background task that pops up a dialog when a task's deadline passes while
the app is open, and keeps the "due soon" card badges fresh.

Extracted from TaskManagerApp — it only needs the service, the settings and
the page, plus a callback to refresh the board.
"""
import asyncio
import logging
from collections.abc import Callable

import flet as ft

from core import strings as L

from .palette import COLORS

log = logging.getLogger(__name__)


class DeadlineWatcher:
    def __init__(self, service, settings, page: ft.Page,
                 on_refresh: Callable[[], None]):
        self.service = service
        self.settings = settings
        self.page = page
        self._on_refresh = on_refresh
        self._notified: set[str] = set()

    def reset(self) -> None:
        """Forget which tasks were already announced (called when the warning
        window changes in Settings)."""
        self._notified.clear()

    async def run(self) -> None:
        while True:
            # notify_check_seconds is a pydantic int in [15, 3600] — no guard needed.
            await asyncio.sleep(self.settings.get("notify_check_seconds"))
            if not self.settings.get("notifications_enabled"):
                continue
            try:
                self._check()
            except Exception:
                log.debug("deadline check failed", exc_info=True)

    def _check(self) -> None:
        from core.models import TaskStatus
        just_passed = []
        for t in self.service.get_all_tasks():
            if t.status == TaskStatus.DONE or t.on_hold or not t.due_date:
                continue
            secs = t.seconds_until_due()
            if secs is not None and secs < 0 and t.id not in self._notified:
                self._notified.add(t.id)
                just_passed.append(t)
        if just_passed:
            self._popup(just_passed)
        self._on_refresh()

    def _popup(self, tasks) -> None:
        from .app import ic
        names = "\n".join(L.UI.DEADLINE_POPUP_ITEM.format(title=t.title) for t in tasks[:8])
        extra = L.UI.DEADLINE_POPUP_MORE.format(n=len(tasks) - 8) if len(tasks) > 8 else ""
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ic("warning"), color=COLORS["accent_red"]),
                          ft.Text(L.UI.DEADLINE_POPUP_TITLE)], spacing=8),
            content=ft.Text(names + extra),
            actions=[ft.TextButton(L.UI.OK, on_click=lambda e: self.page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        ))
