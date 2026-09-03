"""Small JSON-backed settings store (lives next to tasks.json)."""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "notifications_enabled": True,
    "notify_hours_before": 24,      # flag a task this many hours before its deadline
    "notify_check_seconds": 60,     # how often the in-app checker runs
    "check_updates_on_start": True, # look for a new release when the app opens
    "skipped_update_version": "",   # a release the user chose to skip
}


class SettingsStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data.update({k: raw[k] for k in raw if k in DEFAULTS})
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            log.warning("Bad settings file %s (%s); using defaults", self.path, exc)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("Could not save settings: %s", exc)

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        if key in DEFAULTS:
            self._data[key] = value

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            self.set(k, v)
        self.save()
