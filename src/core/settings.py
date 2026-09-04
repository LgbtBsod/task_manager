"""Typed, JSON-backed application settings (lives next to tasks.json).

Reuses the pydantic dependency the models already pull in: fields are typed
and range-checked, unknown keys in the file are ignored, and an invalid value
falls back to the field default instead of raising.
"""
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ._atomic import atomic_write_text
from ._util import clean_hex

log = logging.getLogger(__name__)

# Named accent presets offered in the settings dialog — SAP Horizon blue plus
# accents that don't collide with the reserved semantic tokens
# (green/orange/red/purple back Done / in-progress / error and must stay
# distinguishable from the primary accent).
ACCENT_PRESETS: dict[str, str] = {
    "Horizon": "#0070f2",
    "Индиго": "#5d36ff",
    "Аметист": "#a100c2",
    "Бирюзовый": "#049f9a",
    "Небесный": "#4fb0ff",
    "Розовый": "#fa4f96",
    "Слива": "#d21ac6",
    "Кобальт": "#2b4a6b",
}

DEFAULT_ACCENT = ACCENT_PRESETS["Horizon"]        # the one canonical primary accent
NOTIFY_HOURS_MAX = 24 * 30                        # deadline-warning window ceiling
THEME_MODES = ("dark", "light", "system")


class AppSettings(BaseModel):
    """User-editable preferences."""
    model_config = ConfigDict(validate_assignment=True)

    notifications_enabled: bool = True
    notify_hours_before: int = Field(default=24, ge=1, le=NOTIFY_HOURS_MAX)
    notify_check_seconds: int = Field(default=60, ge=15, le=3600)
    check_updates_on_start: bool = True
    skipped_update_version: str = ""
    theme_mode: str = "dark"                 # dark | light | system
    accent_color: str = DEFAULT_ACCENT       # primary accent, hex "#rrggbb"
    # per-token palette overrides: {"bg_card": "#101010", ...}. Empty keys use
    # the built-in theme colour. Unknown keys are ignored by the palette.
    custom_colors: dict[str, str] = Field(default_factory=dict)
    # opt-in workflow auto-advance (TaskService.update_task_status kwargs) —
    # both default off so a board never reshuffles itself unasked.
    auto_start_unblocked: bool = False
    auto_close_epic: bool = False

    @field_validator("theme_mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        return v if v in THEME_MODES else "dark"

    @field_validator("accent_color")
    @classmethod
    def _valid_hex(cls, v: str) -> str:
        return clean_hex(v) or DEFAULT_ACCENT

    @field_validator("custom_colors")
    @classmethod
    def _valid_colors(cls, v: dict) -> dict:
        return {str(k): h for k, val in (v or {}).items() if (h := clean_hex(val))}


class SettingsStore:
    """Load / save an :class:`AppSettings` to a JSON file, atomically,
    tolerating a missing or corrupt file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.data: AppSettings = self._load()

    def _load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings.model_validate(raw)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            if self.path.exists():
                log.warning("Bad settings file %s (%s); using defaults", self.path, exc)
            return AppSettings()

    def save(self) -> None:
        try:
            atomic_write_text(self.path, self.data.model_dump_json(indent=2))
        except OSError as exc:
            log.warning("Could not save settings: %s", exc)

    # ── dict-style access used across the GUI ──

    def get(self, key: str) -> Any:
        return getattr(self.data, key, None)

    def set(self, key: str, value: Any) -> None:
        if key in AppSettings.model_fields:
            try:
                setattr(self.data, key, value)   # validated (validate_assignment)
            except ValidationError as exc:
                log.warning("Rejected settings %s=%r (%s)", key, value, exc)

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            self.set(k, v)
        self.save()
