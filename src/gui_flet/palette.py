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

from core._util import clean_hex
from core.settings import DEFAULT_ACCENT  # the one canonical primary accent

# ── SAP Horizon token table (the one place colours are declared) ──────
# "Morning Horizon" (light) / "Evening Horizon" (dark): the signature Horizon
# blue, cool blue-grey neutrals, Horizon semantics (positive green, critical
# mango, negative red). Every value is overridable from Settings.

_NEUTRALS = {
    "dark": {                       # Evening Horizon
        "bg_dark": "#12171c",       # area behind cards (shell background)
        "bg_card": "#1d232a",       # cards / tiles
        "bg_card_hover": "#242c34", # raised surface: zebra rows, hover, menus
        "bg_button": "#2a323c",     # fields, buttons
        "text_primary": "#eaecee",
        "text_secondary": "#a9b4be",
        "border_color": "#2f3a45",
    },
    "light": {                      # Morning Horizon
        "bg_dark": "#f5f6f7",
        "bg_card": "#ffffff",
        "bg_card_hover": "#eef1f3",
        "bg_button": "#e9eef1",
        "text_primary": "#131e29",  # SAP "Text and Titles", Morning Horizon
        "text_secondary": "#556b82",
        "border_color": "#d5dadd",
    },
}
# Horizon semantic accents — SAP's own spec swaps these per theme (a saturated
# hue tuned to read on white goes muddy on a dark surface), NOT one shared
# value: https://www.sap.com/design-system/fiori-design-web/v1-151/foundations/visual/colors/morning-horizon
# and .../colors/evening-horizon ("Semantic Foreground Colors").
_SEMANTIC = {
    "dark": {                       # Evening Horizon
        "accent_green": "#97dd40",   # positive
        "accent_orange": "#ffdf72",  # critical / in-progress (Horizon mango)
        "accent_red": "#fa6161",     # negative
        "accent_purple": "#d3b6ff",  # informative-alt / story (Horizon indigo)
    },
    "light": {                      # Morning Horizon
        "accent_green": "#256f3a",
        "accent_orange": "#e76500",
        "accent_red": "#aa0808",
        "accent_purple": "#5d36ff",
    },
}

# token -> RU label, in settings display order. The one source for CUSTOMISABLE.
_TOKEN_LABEL = {
    "bg_dark":        "Фон приложения",
    "bg_card":        "Фон карточек",
    "bg_button":      "Фон кнопок и полей",
    "bg_card_hover":  "Приподнятая поверхность",
    "text_primary":   "Основной текст",
    "text_secondary": "Второстепенный текст",
    "border_color":   "Границы и разделители",
    "accent_green":   "Акцент «выполнено»",
    "accent_orange":  "Акцент «в работе»",
    "accent_red":     "Акцент «ошибка»",
    "accent_purple":  "Акцент «история»",
}

# Ready-made swatches for the colour picker — Horizon blue-grey ramp + spectrum.
SWATCH_PALETTE: list[str] = [
    "#12171c", "#1d232a", "#2a323c", "#3a4552", "#556b82",
    "#788fa6", "#a9b4be", "#d5dadd", "#f5f6f7", "#ffffff",
    "#f53232", "#e76500", "#ffab1d", "#36a41d", "#049f9a",
    "#0070f2", "#1b90ff", "#4fb0ff", "#5d36ff", "#7858ff",
    "#a100c2", "#d21ac6", "#fa4f96", "#ee3939", "#c35500",
    "#1d2d3e", "#223548", "#2b4a6b", "#0a3d62", "#134f2c",
]

COLORS: dict[str, str] = {}

# Corner-radius scale (Horizon leans on rounded surfaces at a few fixed steps).
RADIUS_CHIP = 4          # tags, small badges
RADIUS_FIELD = 8         # text fields, buttons, swatches
RADIUS_MENU = 10         # dropdown / popup menus
RADIUS_CARD_COMPACT = 12 # kanban task cards / column frame (denser than a panel)
RADIUS_CARD = 16         # section panels, dialog panels, stat tiles

# Elevation scale: (blur_radius, y-offset, (light_opacity, dark_opacity)).
# Dark mode needs a higher opacity — a black shadow reads far fainter once the
# surface behind it is already dark, so the same alpha would look flat.
_ELEVATION = {
    1: (3, 1, (0.12, 0.35)),    # resting cards (kanban task card, stat tile)
    2: (8, 2, (0.16, 0.40)),    # raised / floating surfaces (popovers)
    3: (20, 8, (0.20, 0.50)),   # modals — reserved; Flet's own Dialog handles most of these
}


def elevation(level: int) -> ft.BoxShadow:
    """A named elevation shadow (1 = resting card … 3 = modal-level), tuned
    per the *current* theme so callers don't have to thread a dark/light
    flag through — read fresh at each rebuild, same as any ``COLORS[...]``
    lookup."""
    blur, dy, (light_op, dark_op) = _ELEVATION[level]
    dark = _relative_luminance(COLORS["bg_dark"]) < 0.5
    return ft.BoxShadow(blur_radius=blur, offset=ft.Offset(0, dy),
                        color=ft.Colors.with_opacity(dark_op if dark else light_op, "#000000"))


def resolve_dark(mode: str, system_is_dark: bool = True) -> bool:
    """Whether the given ``theme_mode`` ('dark' | 'light' | 'system') is dark."""
    if mode == "light":
        return False
    if mode == "dark":
        return True
    return system_is_dark


def base_colors(dark: bool) -> dict[str, str]:
    """The built-in palette for a mode (``accent_blue`` not included)."""
    mode = "dark" if dark else "light"
    return {**_NEUTRALS[mode], **_SEMANTIC[mode]}


# Every recolourable token, in display order — derived, never hand-listed.
CUSTOMISABLE: list[tuple[str, str]] = [
    (k, _TOKEN_LABEL[k]) for k in _TOKEN_LABEL if k in base_colors(True)
]


def _effective(dark: bool, overrides: dict[str, str] | None) -> dict[str, str]:
    """``base_colors(dark)`` with the user's per-token overrides layered on —
    the one place base + overrides are merged (apply() and build_theme())."""
    palette = base_colors(dark)
    if overrides:
        palette.update({k: v for k, v in overrides.items() if k in palette})
    return palette


def apply(mode: str, accent: str = DEFAULT_ACCENT, *, system_is_dark: bool = True,
          overrides: dict[str, str] | None = None) -> bool:
    """Rebuild ``COLORS`` for the mode + accent + any per-token ``overrides``
    (from ``settings.custom_colors``). Returns whether it is dark."""
    dark = resolve_dark(mode, system_is_dark)
    COLORS.clear()
    COLORS.update(_effective(dark, overrides))
    COLORS["accent_blue"] = accent or DEFAULT_ACCENT
    return dark


def _scheme(accent: str, dark: bool, pal: dict[str, str]) -> ft.ColorScheme:
    """Flet ColorScheme — surface / outline / text / semantic colours read from
    the (override-aware) ``pal``; only container tints and on-colours are fixed."""
    common = dict(
        primary=accent, on_primary="#ffffff",
        secondary=pal["accent_orange"], on_secondary="#ffffff",
        tertiary=pal["accent_green"], on_tertiary="#ffffff",
        error=pal["accent_red"], on_error="#ffffff",
        surface=pal["bg_dark"], on_surface=pal["text_primary"],
        on_surface_variant=pal["text_secondary"],
        surface_container=pal["bg_card"], surface_container_low=pal["bg_dark"],
        surface_container_high=pal["bg_card_hover"],
        outline=pal["border_color"], outline_variant=pal["border_color"],
    )
    if dark:
        return ft.ColorScheme(primary_container="#12325a",
                              on_primary_container="#d3e8ff", **common)
    return ft.ColorScheme(primary_container="#d8e9ff",
                          on_primary_container="#0a2f5e", **common)


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
    pal = _effective(dark, overrides)
    # Dropdown / popup menus: same fill as the main window, slightly see-through.
    menu_bg = ft.Colors.with_opacity(0.90, pal["bg_dark"])
    menu_style = ft.MenuStyle(
        bgcolor=menu_bg, elevation=6,
        shadow_color=ft.Colors.TRANSPARENT,
        shape=ft.RoundedRectangleBorder(radius=RADIUS_MENU),
        side=ft.BorderSide(1, pal["border_color"]),
    )
    return ft.Theme(
        color_scheme_seed=accent,
        color_scheme=_scheme(accent, dark, pal),
        text_theme=_TEXT_THEME,
        dropdown_theme=ft.DropdownTheme(menu_style=menu_style),
        popup_menu_theme=ft.PopupMenuTheme(color=menu_bg,
                                           shadow_color=ft.Colors.TRANSPARENT),
    )


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """``#rrggbb`` -> three 0..1 floats. Assumes a validated hex string."""
    r, g, b = bytes.fromhex(str(hex_color).removeprefix("#"))
    return r / 255, g / 255, b / 255


def is_hex(value: str) -> bool:
    return clean_hex(value) is not None


def _relative_luminance(hex_color: str) -> float:
    lin = [(c / 12.92) if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
           for c in hex_to_rgb01(hex_color)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours (1.0 … 21.0)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_variant(hex_color: str, bg_hex: str, min_ratio: float = 4.5) -> str:
    """``hex_color`` as-is if it already clears ``min_ratio`` contrast against
    ``bg_hex``; otherwise the same hue nudged toward white/black (whichever
    moves away from the background) until it does.

    Fiori's own dark-theme link/button-text tokens shift to a lighter tint
    rather than reusing brand blue as text — raw accents (chosen by the user,
    so never hardcoded here) can fail the 4.5:1 *text* bar even when they're
    fine as a solid fill or a decorative stripe. Use this only where an accent
    is the actual text/icon colour, not a background.
    """
    if contrast_ratio(hex_color, bg_hex) >= min_ratio:
        return hex_color
    # Tint toward white / shade toward black in RGB space (not a pure HSV
    # value bump): a fully-saturated hue like #0070f2 is luminance-capped —
    # blue's WCAG weight is only 0.0722, so even maximum brightness at full
    # saturation can't clear 4.5:1 on a dark surface. Blending toward
    # white/black lowers saturation too, exactly how Fiori's own lightened
    # dark-mode link colour (e.g. #4db1ff from #0070f2) reads as a paler tint.
    lighten = _relative_luminance(bg_hex) < 0.5
    r, g, b = hex_to_rgb01(hex_color)
    target = 1.0 if lighten else 0.0
    for step in range(1, 21):
        t = step / 20
        mixed = (r + (target - r) * t, g + (target - g) * t, b + (target - b) * t)
        candidate = "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in mixed))
        if contrast_ratio(candidate, bg_hex) >= min_ratio:
            return candidate
    return "#ffffff" if lighten else "#000000"


apply("dark", DEFAULT_ACCENT)   # never leave COLORS empty at import time
