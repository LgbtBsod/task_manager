"""Tiny shared helpers."""


def clean_hex(value: object) -> str | None:
    """Normalise a ``#rrggbb`` colour to lower-case, or ``None`` if invalid.

    The single hex-colour check — ``settings.AppSettings`` validates with it
    and ``gui_flet.palette`` derives ``is_hex`` from it.
    """
    s = str(value).strip().lower()
    if len(s) == 7 and s[0] == "#":
        try:
            int(s[1:], 16)
            return s
        except ValueError:
            pass
    return None


def apply_kwargs(obj: object, kwargs: dict) -> object:
    """Set each non-None ``kwargs`` value on ``obj`` if it has that attribute.
    Used by every ``update_<entity>(id, **kwargs)`` method."""
    for key, val in kwargs.items():
        if val is not None and hasattr(obj, key):
            setattr(obj, key, val)
    return obj
