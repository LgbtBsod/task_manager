"""Tiny shared helpers for the service layer."""


def apply_kwargs(obj: object, kwargs: dict) -> object:
    """Set each non-None ``kwargs`` value on ``obj`` if it has that attribute.
    Used by every ``update_<entity>(id, **kwargs)`` method."""
    for key, val in kwargs.items():
        if val is not None and hasattr(obj, key):
            setattr(obj, key, val)
    return obj
