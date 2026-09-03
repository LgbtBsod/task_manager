"""The application's composition root.

One object wires the whole app together — filesystem paths, the settings store,
the JSON repository and the service layer — built once in ``main()`` and passed
down. Nothing else constructs a ``TaskRepository`` / ``TaskService`` /
``SettingsStore`` directly.
"""
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .repository import TaskRepository
from .service import TaskService
from .settings import SettingsStore


@dataclass(frozen=True)
class AppContext:
    settings: SettingsStore
    repository: TaskRepository
    service: TaskService
    version: str

    @classmethod
    def create(cls) -> "AppContext":
        """Wire the real app: data dir under the exe / repo root."""
        paths.ensure_data_dir()
        repository = TaskRepository(db_path=str(paths.db_path))
        settings = SettingsStore(str(paths.settings_path))
        service = TaskService(repository=repository)
        return cls(settings=settings, repository=repository, service=service,
                   version=paths.read_version())

    @classmethod
    def for_testing(cls, tmp_path: Path) -> "AppContext":
        """Wire an isolated app rooted at ``tmp_path`` (no disk side effects
        outside it)."""
        db = tmp_path / "tasks.json"
        repository = TaskRepository(db_path=str(db))
        settings = SettingsStore(str(tmp_path / "settings.json"))
        service = TaskService(repository=repository)
        return cls(settings=settings, repository=repository, service=service,
                   version="test")
