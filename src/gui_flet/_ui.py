"""Tiny Flet helpers shared across the view modules."""
import flet as ft

from .palette import COLORS, RADIUS_FIELD


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


def field(**kw) -> ft.TextField:
    """A ``TextField`` pre-themed for the current palette.

    Flet's default field text does not follow the active ``ColorScheme`` once
    it's inside a dialog (renders near-black on the dark theme), so the palette
    colours are pinned explicitly here.
    """
    kw.setdefault("text_size", 14)
    kw.setdefault("border_radius", RADIUS_FIELD)
    kw.setdefault("color", COLORS["text_primary"])
    kw.setdefault("border_color", COLORS["border_color"])
    kw.setdefault("cursor_color", COLORS["accent_blue"])
    return ft.TextField(**kw)


def dropdown(**kw) -> ft.Dropdown:
    """A ``Dropdown`` pre-themed for the current palette (see :func:`field`)."""
    size = kw.pop("text_size", 14)
    kw.setdefault("border_radius", RADIUS_FIELD)
    kw.setdefault("border_color", COLORS["border_color"])
    kw.setdefault("text_style", ft.TextStyle(size=size, color=COLORS["text_primary"]))
    return ft.Dropdown(**kw)


def switch(**kw) -> ft.Switch:
    """A ``Switch`` whose label follows the palette (see :func:`field`)."""
    kw.setdefault("label_text_style", ft.TextStyle(color=COLORS["text_primary"]))
    kw.setdefault("active_color", COLORS["accent_blue"])
    return ft.Switch(**kw)
