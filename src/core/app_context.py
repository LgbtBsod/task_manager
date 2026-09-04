"""The application's composition root.

One object wires the whole app together — filesystem paths, the settings store,
the JSON repository and the service layer — built once in ``main()`` and passed
down. Nothing else constructs a ``TaskRepository`` / ``TaskService`` /
``SettingsStore`` directly.
"""
from dataclasses import dataclass

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
