"""Runtime colour palette — the single source of truth for GUI colours.

``COLORS`` is rebuilt in place by :func:`apply` whenever the user changes the
theme mode or accent colour in Settings, so every view that reads
``COLORS["…"]`` at build time picks up the change on the next rebuild. Flet's
own widgets (dialogs, dropdowns, pickers) follow ``page.theme`` /
``page.theme_mode`` via the :class:`ft.Theme` objects from :func:`build_theme`.

Priority / task-type accents are NOT here — they live on the enums
(``Priority.color``) because they must read the same in both themes.
"""
import flet as ft

# Tuned to the SAP Horizon design language — "Morning Horizon" (light) and
# "Evening Horizon" (dark): the signature Horizon blue, cool blue-grey
# neutrals, and Horizon's semantic colours (positive green, critical mango,
# negative red). Every value is overridable from Settings.
DEFAULT_ACCENT = "#0070f2"          # Horizon blue

# Neutrals per mode. The accent is injected by apply() as COLORS["accent_blue"]
# (kept under that key so the ~40 existing call sites don't need touching).
_DARK = {                           # Evening Horizon
    "bg_dark": "#12171c",           # area behind cards (shell background)
    "bg_card": "#1d232a",           # cards / tiles
    "bg_card_hover": "#2a323c",
    "bg_button": "#2a323c",         # fields, buttons
    "text_primary": "#eaecee",
    "text_secondary": "#a9b4be",    # labels
    "border_color": "#2f3a45",
}
_LIGHT = {                          # Morning Horizon
    "bg_dark": "#f5f6f7",           # area behind cards (shell background)
    "bg_card": "#ffffff",
    "bg_card_hover": "#eef1f3",
    "bg_button": "#e9eef1",
    "text_primary": "#1d2d3e",      # Horizon dark blue-grey
    "text_secondary": "#556b82",    # Horizon label colour
    "border_color": "#d5dadd",
}
# Horizon semantic colours — same hue both modes.
_FIXED_ACCENTS = {
    "accent_green": "#36a41d",      # positive
    "accent_orange": "#e76500",     # critical / in-progress (Horizon mango)
    "accent_red": "#f53232",        # negative
    "accent_purple": "#7858ff",     # informative-alt / story (Horizon indigo)
}

# Every COLORS key the user may recolour in Settings, with its RU label and a
# section hint. The primary accent (``accent_blue``) is handled separately by
# the accent-preset swatches.
CUSTOMISABLE: list[tuple[str, str]] = [
    ("bg_dark",        "Фон приложения"),
    ("bg_card",        "Фон карточек"),
    ("bg_card_hover",  "Карточка при наведении"),
    ("bg_button",      "Фон кнопок и полей"),
    ("text_primary",   "Основной текст"),
    ("text_secondary", "Второстепенный текст"),
    ("border_color",   "Границы и разделители"),
    ("accent_green",   "Акцент «выполнено»"),
    ("accent_orange",  "Акцент «в работе»"),
    ("accent_red",     "Акцент «ошибка»"),
    ("accent_purple",  "Акцент «история»"),
]

# Ready-made swatches for the settings colour picker — Horizon blue-grey
# ramp + the Horizon accent spectrum.
SWATCH_PALETTE: list[str] = [
    "#12171c", "#1d232a", "#2a323c", "#3a4552", "#556b82",
    "#788fa6", "#a9b4be", "#d5dadd", "#f5f6f7", "#ffffff",
    "#f53232", "#e76500", "#ffab1d", "#36a41d", "#049f9a",
    "#0070f2", "#1b90ff", "#4fb0ff", "#5d36ff", "#7858ff",
    "#a100c2", "#d21ac6", "#fa4f96", "#ee3939", "#c35500",
    "#1d2d3e", "#223548", "#2b4a6b", "#0a3d62", "#134f2c",
]

COLORS: dict[str, str] = {}


def resolve_dark(mode: str, system_is_dark: bool = True) -> bool:
    """Whether the given ``theme_mode`` ('dark' | 'light' | 'system') is dark."""
    if mode == "light":
        return False
    if mode == "dark":
        return True
    return system_is_dark


def base_colors(dark: bool) -> dict[str, str]:
    """The built-in palette for a mode (``accent_blue`` not included).

    Used both by :func:`apply` and by the settings dialog to show / restore
    a token's default.
    """
    return {**(_DARK if dark else _LIGHT), **_FIXED_ACCENTS}


def apply(mode: str, accent: str = DEFAULT_ACCENT, *, system_is_dark: bool = True,
          overrides: dict[str, str] | None = None) -> bool:
    """Rebuild ``COLORS`` for the mode + accent + any per-token ``overrides``
    (from ``settings.custom_colors``). Returns whether it is dark."""
    dark = resolve_dark(mode, system_is_dark)
    COLORS.clear()
    COLORS.update(base_colors(dark))
    if overrides:
        COLORS.update({k: v for k, v in overrides.items() if k in COLORS})
    COLORS["accent_blue"] = accent or DEFAULT_ACCENT
    return dark


def _scheme(accent: str, dark: bool) -> ft.ColorScheme:
    if dark:                                   # Evening Horizon
        return ft.ColorScheme(
            primary=accent, on_primary="#ffffff",
            primary_container="#12325a", on_primary_container="#d3e8ff",
            secondary="#e76500", on_secondary="#ffffff",
            tertiary="#36a41d", on_tertiary="#ffffff",
            error="#f53232", on_error="#ffffff",
            surface="#12171c", on_surface="#eaecee", on_surface_variant="#a9b4be",
            surface_container="#1d232a", surface_container_low="#171c22",
            surface_container_high="#2a323c",
            outline="#2f3a45", outline_variant="#3a4552",
        )
    return ft.ColorScheme(                      # Morning Horizon
        primary=accent, on_primary="#ffffff",
        primary_container="#d8e9ff", on_primary_container="#0a2f5e",
        secondary="#c35500", on_secondary="#ffffff",
        tertiary="#1e7a12", on_tertiary="#ffffff",
        error="#e00a0a", on_error="#ffffff",
        surface="#f5f6f7", on_surface="#1d2d3e", on_surface_variant="#556b82",
        surface_container="#ffffff", surface_container_low="#fafbfb",
        surface_container_high="#eef1f3",
        outline="#d5dadd", outline_variant="#c4cbd0",
    )


# One text theme for both modes: no explicit colour, so text follows
# on_surface / on_surface_variant of whichever scheme is active.
_TEXT_THEME = ft.TextTheme(
    body_large=ft.TextStyle(size=14),
    body_medium=ft.TextStyle(size=12),
    body_small=ft.TextStyle(size=11),
    label_large=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
    label_medium=ft.TextStyle(size=12),
    label_small=ft.TextStyle(size=11),
    title_large=ft.TextStyle(size=22, weight=ft.FontWeight.BOLD),
    title_medium=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD),
    title_small=ft.TextStyle(size=14, weight=ft.FontWeight.W_600),
    headline_medium=ft.TextStyle(size=28, weight=ft.FontWeight.BOLD),
)


def build_theme(accent: str, dark: bool, *,
                overrides: dict[str, str] | None = None) -> ft.Theme:
    palette = base_colors(dark)
    if overrides:
        palette.update({k: v for k, v in overrides.items() if k in palette})
    # Dropdown / popup menus: same fill as the main window, slightly see-through.
    menu_bg = ft.Colors.with_opacity(0.90, palette["bg_dark"])
    menu_style = ft.MenuStyle(
        bgcolor=menu_bg, elevation=6,
        shadow_color=ft.Colors.TRANSPARENT,
        shape=ft.RoundedRectangleBorder(radius=10),
        side=ft.BorderSide(1, palette["border_color"]),
    )
    return ft.Theme(
        color_scheme_seed=accent,
        color_scheme=_scheme(accent, dark),
        text_theme=_TEXT_THEME,
        dropdown_theme=ft.DropdownTheme(menu_style=menu_style),
        popup_menu_theme=ft.PopupMenuTheme(color=menu_bg,
                                           shadow_color=ft.Colors.TRANSPARENT),
    )


def is_hex(value: str) -> bool:
    v = str(value).strip()
    if len(v) != 7 or v[0] != "#":
        return False
    try:
        int(v[1:], 16)
        return True
    except ValueError:
        return False


def _relative_luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [(c / 12.92) if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
           for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours (1.0 … 21.0)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


apply("dark", DEFAULT_ACCENT)   # never leave COLORS empty at import time
