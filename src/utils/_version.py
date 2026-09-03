"""Current version string. Thin wrapper over :func:`core.paths.read_version`
kept for the ``from utils._version import get_version`` call sites."""


def get_version() -> str:
    try:
        from core.paths import read_version
        return read_version()
    except Exception:
        return "unknown"
