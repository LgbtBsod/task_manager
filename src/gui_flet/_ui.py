"""Tiny Flet helpers shared across the view modules."""
import flet as ft

from .palette import COLORS, RADIUS_CHIP, RADIUS_FIELD


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
    """A ``Switch`` whose label follows the palette (see :func:`field`).

    Pins an explicit label size instead of inheriting the theme's body
    size: switches sit in dense settings rows next to 10-12px helper text,
    and a longer Russian label at full body size overflows the narrow
    dialog width Switch's non-wrapping label can't recover from.
    """
    kw.setdefault("label_text_style", ft.TextStyle(size=13, color=COLORS["text_primary"]))
    kw.setdefault("active_color", COLORS["accent_blue"])
    return ft.Switch(**kw)


def toggle_chip(label: str, color: str, on: bool, on_click) -> ft.Container:
    """A pill-shaped toggle chip: filled + white text when ``on``, outlined
    when not. Shared by every tag/status picker (task_dialog._TagPicker,
    bulk_dialog's source-status chips) so the on/off look stays one place."""
    return ft.Container(
        content=ft.Text(label, size=11,
                        color="#ffffff" if on else COLORS["text_secondary"],
                        weight=ft.FontWeight.W_600 if on else ft.FontWeight.NORMAL),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        bgcolor=color if on else COLORS["bg_button"],
        border=ft.Border.all(1, color),
        border_radius=RADIUS_CHIP,
        on_click=on_click,
    )


def restyle_toggle_chip(chip: ft.Container, on: bool, color: str) -> None:
    """Flip a :func:`toggle_chip`'s on/off visual state in place. Caller is
    responsible for ``safe_update(chip)`` afterward."""
    chip.bgcolor = color if on else COLORS["bg_button"]
    chip.content.color = "#ffffff" if on else COLORS["text_secondary"]
    chip.content.weight = ft.FontWeight.W_600 if on else ft.FontWeight.NORMAL
