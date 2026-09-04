"""The tag registry — named, colour-coded labels chosen from a list instead of
re-typed on every task.

A task still stores tags as lower-cased strings in ``Task.tags``; this service
owns the *catalog* (colour + description + analytics) and keeps the two in
sync: renaming or deleting a registered tag rewrites every task that used it,
and :meth:`sync_from_tasks` back-fills the catalog from tags typed before the
registry existed.

Composed into :class:`TaskService` and reached through the collaborator facade
(``service.list_tags()``, ``service.tag_breakdown()`` …).
"""
import logging

from ._util import clean_hex
from .models import TAG_DEFAULT_COLOR, Tag, TaskStatus, _normalize_tags
from .repository import TaskRepository

log = logging.getLogger(__name__)

# Colours handed out (in order, then cycled) to tags created by the migration,
# so a freshly-imported board isn't a wall of identical grey chips. Horizon
# accents + a few extra hues, none of them the reserved status colours.
_AUTO_COLORS = [
    "#0070f2", "#7858ff", "#049f9a", "#e76500", "#36a41d",
    "#d21ac6", "#4fb0ff", "#fa4f96", "#a100c2", "#2b4a6b",
]


class TagService:
    def __init__(self, repository: TaskRepository):
        self.repo = repository

    # ── registry CRUD ──

    def list_tags(self) -> list[Tag]:
        """Every registered tag, sorted by name."""
        return sorted(self.repo.tags.all(), key=lambda t: t.name)

    def get_tag(self, tag_id: str) -> Tag | None:
        return self.repo.tags.by_id(tag_id)

    def get_tag_by_name(self, name: str) -> Tag | None:
        want = name.strip().lower()
        return next((t for t in self.repo.tags.all() if t.name == want), None)

    def create_tag(self, name: str, color: str | None = None,
                   description: str = "") -> Tag:
        """Register a tag. If the name is already taken, return the existing
        entry (idempotent — the task dialog's inline "add" relies on this)."""
        canonical = _normalize_tags([name])
        if not canonical:
            raise ValueError("Tag name is empty")
        norm = canonical[0]
        if existing := self.get_tag_by_name(norm):
            return existing
        tag = Tag(
            name=norm,
            color=clean_hex(color) or self._next_auto_color(),
            description=description.strip(),
        )
        self.repo.tags.add(tag)
        log.info("Tag created: %s (%s)", tag.name, tag.color)
        return tag

    def update_tag(self, tag_id: str, *, name: str | None = None,
                   color: str | None = None, description: str | None = None) -> Tag | None:
        """Recolour / redescribe / rename a tag. A rename rewrites ``Task.tags``
        on every task that referenced the old name."""
        tag = self.repo.tags.by_id(tag_id)
        if tag is None:
            return None

        if color is not None and (hexc := clean_hex(color)):
            tag.color = hexc
        if description is not None:
            tag.description = description.strip()

        if name is not None:
            canonical = _normalize_tags([name])
            new_name = canonical[0] if canonical else ""
            if new_name and new_name != tag.name:
                clash = self.get_tag_by_name(new_name)
                if clash and clash.id != tag_id:
                    raise ValueError(f"A tag named {new_name!r} already exists")
                self._rewrite_task_tag(tag.name, new_name)
                log.info("Tag renamed: %s -> %s", tag.name, new_name)
                tag.name = new_name

        return self.repo.tags.update(tag)

    def delete_tag(self, tag_id: str, *, strip_from_tasks: bool = True) -> bool:
        tag = self.repo.tags.by_id(tag_id)
        if tag is None:
            return False
        if not self.repo.tags.delete(tag_id):
            return False
        if strip_from_tasks:
            self._rewrite_task_tag(tag.name, None)
        log.info("Tag deleted: %s", tag.name)
        return True

    # ── analytics ──

    def tag_usage(self, name: str) -> int:
        want = name.strip().lower()
        return sum(1 for t in self.repo.get_all() if want in t.tags)

    def tag_breakdown(self) -> list[dict]:
        """``[{name, color, description, count, done}]`` for every registered
        tag, most-used first. Feeds the Overview "По тегам" card."""
        tasks = self.repo.get_all()
        rows = []
        for tag in self.repo.tags.all():
            tagged = [t for t in tasks if tag.name in t.tags]
            rows.append({
                "name": tag.name, "color": tag.color,
                "description": tag.description, "count": len(tagged),
                "done": sum(1 for t in tagged if t.status == TaskStatus.DONE),
            })
        rows.sort(key=lambda r: (-r["count"], r["name"]))
        return rows

    # ── migration ──

    def sync_from_tasks(self) -> int:
        """Register any tag string found on a task but not yet in the catalog.
        Idempotent; returns how many were added. One file write."""
        known = {t.name for t in self.repo.tags.all()}
        seen: list[str] = []
        for task in self.repo.get_all():
            for name in task.tags:
                if name not in known and name not in seen:
                    seen.append(name)
        if not seen:
            return 0
        start = len(known)
        new = [Tag(name=n, color=_AUTO_COLORS[(start + i) % len(_AUTO_COLORS)])
               for i, n in enumerate(seen)]
        self.repo.add_tag_defs(new)
        log.info("Tag registry back-filled with %d tag(s): %s", len(new), ", ".join(seen))
        return len(new)

    # ── internals ──

    def _next_auto_color(self) -> str:
        used = {t.color for t in self.repo.tags.all()}
        for c in _AUTO_COLORS:
            if c not in used:
                return c
        return TAG_DEFAULT_COLOR

    def _rewrite_task_tag(self, old: str, new: str | None) -> None:
        """Replace (or drop, when ``new`` is None) the tag ``old`` on every task."""
        for task in self.repo.get_all():
            if old not in task.tags:
                continue
            replaced = [new if t == old else t for t in task.tags] if new \
                else [t for t in task.tags if t != old]
            task.tags = _normalize_tags(replaced)
            task.update_timestamp()
            self.repo.update(task)
