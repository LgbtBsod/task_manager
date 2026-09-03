"""Read-only board analytics — statistics, workload, velocity, dashboards.

No mutation, no side effects; every method just aggregates over the repo.
Composed into :class:`TaskService` as ``self.analytics`` and reached through
the collaborator facade (``service.get_personal_dashboard()`` etc.).
"""
from datetime import datetime
from typing import Optional, List

from .models import Priority, SprintStatus, Task, TaskStatus
from .repository import TaskRepository


class BoardAnalytics:
    def __init__(self, repository: TaskRepository, sprints):
        self.repo = repository
        self.sprints = sprints            # SprintService, for report/velocity

    # ── simple pass-throughs ──

    def get_statistics(self) -> dict:
        return self.repo.get_statistics()

    def get_team_workload(self) -> List[dict]:
        lanes: dict[str, dict] = {}
        for t in self.repo.get_all():
            w = lanes.setdefault(t.assignee or "Unassigned", {
                "total": 0, "todo": 0, "in_progress": 0, "done": 0,
                "total_time": 0.0, "story_points_sum": 0})
            w["total"] += 1
            w[t.status.name.lower() if t.status != TaskStatus.IN_PROGRESS else "in_progress"] += 1
            w["total_time"] += t.time_spent
            w["story_points_sum"] += t.story_points or 0
        return [{"assignee": name, **w} for name, w in sorted(lanes.items())]

    def get_swimlanes(self, group_by: str = "assignee") -> dict:
        key_of = {
            "priority": lambda t: t.priority.value,
            "task_type": lambda t: t.task_type,
            "urgency": lambda t: t.urgency,
        }.get(group_by, lambda t: t.assignee or "Unassigned")
        lanes: dict = {}
        for t in self.repo.get_all():
            lane = lanes.setdefault(key_of(t), {"todo": [], "in_progress": [], "done": []})
            if t.status == TaskStatus.TODO:
                lane["todo"].append(t)
            elif t.status == TaskStatus.IN_PROGRESS:
                lane["in_progress"].append(t)
            elif t.status == TaskStatus.DONE:
                lane["done"].append(t)
        return lanes

    # ── velocity (needs the sprint service) ──

    def get_sprint_velocity(self, last_n: int = 5) -> List[dict]:
        completed = [s for s in self.repo.get_all_sprints()
                     if s.status == SprintStatus.COMPLETED.value]
        completed.sort(key=lambda s: s.created_at, reverse=True)
        out = []
        for sprint in completed[:last_n]:
            tasks = self.sprints.get_sprint_tasks(sprint.id)
            done = [t for t in tasks if t.status == TaskStatus.DONE]
            out.append({
                "sprint_id": sprint.id, "sprint_name": sprint.name,
                "completed_points": sum(t.story_points or 0 for t in done),
                "completed_tasks": len(done),
                "total_time_spent": round(sum(t.time_spent for t in tasks), 2),
            })
        return out

    def get_average_velocity(self, last_n: int = 5) -> float:
        vs = self.get_sprint_velocity(last_n)
        return round(sum(v["completed_points"] for v in vs) / len(vs), 1) if vs else 0.0

    # ── feeds / boards ──

    def get_activity_feed(self, limit: int = 50) -> List[dict]:
        feed = []
        for t in self.repo.get_all():
            for h in t.history:
                feed.append({"id": "", "timestamp": h.timestamp, "action": h.field_name,
                             "task_id": t.id, "task_title": t.title, "author": "",
                             "details": f"{h.old_value} -> {h.new_value}"})
            for c in t.comments:
                feed.append({"id": c.id, "timestamp": c.created_at, "action": "comment_added",
                             "task_id": t.id, "task_title": t.title, "author": c.author,
                             "details": c.text[:100]})
        feed.sort(key=lambda x: x["timestamp"], reverse=True)
        return feed[:limit]

    def get_board_data(self, sprint_id: Optional[str] = None) -> dict:
        tasks = self.repo.get_all()
        if sprint_id:
            tasks = [t for t in tasks if t.sprint_id == sprint_id]
        cols = [("todo", "Todo", TaskStatus.TODO),
                ("in_progress", "In Progress", TaskStatus.IN_PROGRESS),
                ("done", "Done", TaskStatus.DONE)]
        return {"columns": [
            {"id": cid, "title": title,
             "tasks": [t.to_dict() for t in tasks if t.status == st],
             "count": sum(1 for t in tasks if t.status == st)}
            for cid, title, st in cols
        ]}

    def get_personal_dashboard(self) -> dict:
        tasks = self.repo.get_all()
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)

        now = datetime.now()
        last_7 = [0] * 7
        for t in tasks:
            if t.status == TaskStatus.DONE and t.updated_at:
                try:
                    d = (now - datetime.fromisoformat(t.updated_at)).days
                    if 0 <= d < 7:
                        last_7[d] += 1
                except (ValueError, TypeError):
                    pass

        active = [s for s in self.repo.get_all_sprints() if s.is_active()]
        return {
            "total_tasks": total,
            "todo": sum(1 for t in tasks if t.status == TaskStatus.TODO),
            "in_progress": sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS),
            "done": done,
            "overdue": sum(1 for t in tasks if t.is_overdue()),
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
            "total_time_spent": round(sum(t.time_spent for t in tasks), 2),
            "total_original_estimate": round(sum(t.original_estimate for t in tasks), 2),
            "total_remaining_estimate": round(
                sum(max(0, t.original_estimate - t.time_spent) for t in tasks), 2),
            "priority_breakdown": {p.value: n for p in Priority
                                   if (n := sum(1 for t in tasks if t.priority == p))},
            "recent_tasks": [t.to_dict() for t in
                             sorted(tasks, key=lambda t: t.updated_at or "", reverse=True)[:10]],
            "overdue_tasks": [t.to_dict() for t in tasks if t.is_overdue()],
            "completion_last_7_days": last_7,
            "total_story_points": sum(t.story_points or 0 for t in tasks),
            "completed_story_points": sum(t.story_points or 0 for t in tasks
                                          if t.status == TaskStatus.DONE),
            "active_sprint": self.sprints.get_sprint_report(active[0].id) if active else None,
            "labels_count": len({lbl for t in tasks for lbl in t.labels}),
            "versions_count": len(self.repo.get_all_versions()),
            "categories_count": len(self.repo.get_all_categories()),
        }
