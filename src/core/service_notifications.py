"""User notifications (overdue / due-soon alerts).

Note: the Flet GUI has its own in-app deadline watcher; this store is kept
for API completeness and future headless use.
"""
import logging
from typing import Optional, List

from .models import Notification, TaskStatus
from .repository import TaskRepository

log = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    def get_notifications(self, unread_only: bool = False) -> List[Notification]:
        return (self.repo.get_unread_notifications() if unread_only
                else self.repo.get_all_notifications())

    def add_notification(self, ntype: str, title: str, message: str,
                         task_id: Optional[str] = None) -> Notification:
        notif = Notification(ntype=ntype, title=title.strip(),
                             message=message.strip(), task_id=task_id)
        self.repo.add_notification(notif)
        return notif

    def mark_notification_read(self, notif_id: str) -> bool:
        return self.repo.mark_notification_read(notif_id)

    def mark_all_notifications_read(self) -> int:
        return self.repo.mark_all_notifications_read()

    def delete_notification(self, notif_id: str) -> bool:
        return self.repo.delete_notification(notif_id)

    def generate_overdue_notifications(self) -> List[Notification]:
        created = []
        for t in self.repo.get_all():
            if t.status == TaskStatus.DONE:
                continue
            if t.is_overdue():
                created.append(self.add_notification(
                    "warning", "Просрочено",
                    f"{t.title} просрочена ({t.due_date})", task_id=t.id))
            elif t.days_until_due() is not None and 0 <= t.days_until_due() <= 2:
                created.append(self.add_notification(
                    "info", "Скоро дедлайн",
                    f"{t.title} — через {t.days_until_due()} дн.", task_id=t.id))
        self.repo.clear_old_notifications(100)
        return created
