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

DEFAULT_ACCENT = "#0a84ff"

# Neutrals per mode. The accent is injected by apply() as COLORS["accent_blue"]
# (kept under that key so the ~40 existing call sites don't need touching).
_DARK = {
    "bg_dark": "#0a0a0a",
    "bg_card": "#1c1c1e",
    "bg_card_hover": "#2c2c2e",
    "bg_button": "#3a3a3c",
    "text_primary": "#f5f5f7",
    "text_secondary": "#86868b",
    "border_color": "#38383a",
}
_LIGHT = {
    "bg_dark": "#f2f2f7",
    "bg_card": "#ffffff",
    "bg_card_hover": "#e8e8ed",
    "bg_button": "#e3e3e8",
    "text_primary": "#1c1c1e",
    "text_secondary": "#6c6c70",
    "border_color": "#d1d1d6",
}
# Secondary accents that are the same in both themes.
_FIXED_ACCENTS = {
    "accent_green": "#30d158",
    "accent_orange": "#ff9f0a",
    "accent_red": "#ff453a",
    "accent_purple": "#bf5af2",
}

COLORS: dict[str, str] = {}


def resolve_dark(mode: str, system_is_dark: bool = True) -> bool:
    """Whether the given ``theme_mode`` ('dark' | 'light' | 'system') is dark."""
    if mode == "light":
        return False
    if mode == "dark":
        return True
    return system_is_dark


def apply(mode: str, accent: str = DEFAULT_ACCENT, *, system_is_dark: bool = True) -> bool:
    """Rebuild ``COLORS`` for the mode + accent. Returns whether it is dark."""
    dark = resolve_dark(mode, system_is_dark)
    COLORS.clear()
    COLORS.update(_DARK if dark else _LIGHT)
    COLORS.update(_FIXED_ACCENTS)
    COLORS["accent_blue"] = accent or DEFAULT_ACCENT
    return dark


def _scheme(accent: str, dark: bool) -> ft.ColorScheme:
    if dark:
        return ft.ColorScheme(
            primary=accent, on_primary="#ffffff",
            primary_container="#1c3a5e", on_primary_container="#d0e4ff",
            secondary="#ff9f0a", on_secondary="#000000",
            tertiary="#30d158", on_tertiary="#000000",
            error="#ff453a", on_error="#ffffff",
            surface="#0a0a0a", on_surface="#f5f5f7", on_surface_variant="#86868b",
            surface_container="#1c1c1e", surface_container_low="#161618",
            surface_container_high="#2c2c2e",
            outline="#38383a", outline_variant="#48484a",
        )
    return ft.ColorScheme(
        primary=accent, on_primary="#ffffff",
        primary_container="#d6e6ff", on_primary_container="#0a2647",
        secondary="#c76b00", on_secondary="#ffffff",
        tertiary="#1a7f37", on_tertiary="#ffffff",
        error="#d70015", on_error="#ffffff",
        surface="#f2f2f7", on_surface="#1c1c1e", on_surface_variant="#6c6c70",
        surface_container="#ffffff", surface_container_low="#f7f7fa",
        surface_container_high="#e8e8ed",
        outline="#d1d1d6", outline_variant="#c7c7cc",
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


def build_theme(accent: str, dark: bool) -> ft.Theme:
    return ft.Theme(color_scheme_seed=accent,
                    color_scheme=_scheme(accent, dark),
                    text_theme=_TEXT_THEME)


apply("dark", DEFAULT_ACCENT)   # never leave COLORS empty at import time
