"""Tiny Flet helpers shared across the view modules."""


def safe_update(*controls) -> None:
    """Repaint each control that is already mounted on a page; skip the rest.

    Lets a builder refresh eagerly without first checking whether its controls
    are on the page yet (an unmounted ``control.update()`` raises).
    """
    for ctl in controls:
        try:
            if getattr(ctl, "page", None) is not None:
                ctl.update()
        except (AttributeError, AssertionError, RuntimeError):
            pass
