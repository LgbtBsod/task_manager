"""A designer-style colour picker for the settings dialog.

Flet has no native picker, so this builds one from layered gradients + a
``GestureDetector``: a saturation/value square, a hue slider, a hex field
and the ready-made swatch grid. ``on_pick(hex)`` fires live while dragging.
"""
import colorsys

import flet as ft

from core import strings as L

from ._ui import field as _field
from .palette import COLORS, SWATCH_PALETTE, is_hex

_SQ_W, _SQ_H = 264, 168
_HUE_H = 14
_HUE_STOPS = ["#ff0000", "#ffff00", "#00ff00", "#00ffff",
              "#0000ff", "#ff00ff", "#ff0000"]


def _hex_to_hsv(hx: str) -> tuple[float, float, float]:
    hx = hx.lstrip("#")
    r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def _hsv_to_hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(max(s, 0), 1), min(max(v, 0), 1))
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return round(r * 255), round(g * 255), round(b * 255)


def show_color_picker(page: ft.Page, initial: str, title: str,
                      on_pick, on_default=None) -> None:
    h, s, v = _hex_to_hsv(initial if is_hex(initial) else "#0070f2")
    st = {"h": h, "s": s, "v": v}

    sq_base = ft.Container(width=_SQ_W, height=_SQ_H, border_radius=8)
    sq_white = ft.Container(width=_SQ_W, height=_SQ_H, border_radius=8,
                            gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                                                       colors=["#ffffffff", "#ffffff00"]))
    sq_black = ft.Container(width=_SQ_W, height=_SQ_H, border_radius=8,
                            gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1),
                                                       colors=["#00000000", "#000000ff"]))
    sq_dot = ft.Container(width=14, height=14, border_radius=7,
                          border=ft.Border.all(2, "#ffffff"),
                          shadow=ft.BoxShadow(blur_radius=3, color="#00000070"))
    hue_track = ft.Container(width=_SQ_W, height=_HUE_H, border_radius=7,
                             gradient=ft.LinearGradient(begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0),
                                                        colors=_HUE_STOPS))
    hue_dot = ft.Container(width=6, height=_HUE_H + 8, border_radius=3, bgcolor="#ffffff",
                           border=ft.Border.all(1, "#00000070"), top=-4)

    preview = ft.Container(width=44, height=44, border_radius=8,
                           border=ft.Border.all(1, COLORS["border_color"]))
    hex_field = _field(width=104, text_size=13, dense=True)
    rgb_label = ft.Text(size=11, color=COLORS["text_secondary"])

    def _cur() -> str:
        return _hsv_to_hex(st["h"], st["s"], st["v"])

    def _sync(emit: bool = True) -> None:
        cur = _cur()
        sq_base.bgcolor = _hsv_to_hex(st["h"], 1, 1)
        sq_dot.left = st["s"] * _SQ_W - 7
        sq_dot.top = (1 - st["v"]) * _SQ_H - 7
        hue_dot.left = st["h"] * _SQ_W - 3
        preview.bgcolor = cur
        hex_field.value = cur
        r, g, b = _rgb(st["h"], st["s"], st["v"])
        rgb_label.value = f"RGB {r}, {g}, {b}"
        for c in (sq_base, sq_dot, hue_dot, preview, hex_field, rgb_label):
            try:
                c.update()
            except Exception:
                pass
        if emit:
            on_pick(cur)

    def _sv_at(e):
        pos = e.local_position
        st["s"] = min(max(pos.x / _SQ_W, 0.0), 1.0)
        st["v"] = 1.0 - min(max(pos.y / _SQ_H, 0.0), 1.0)
        _sync()

    def _hue_at(e):
        st["h"] = min(max(e.local_position.x / _SQ_W, 0.0), 1.0)
        _sync()

    def _from_hex(e):
        val = (hex_field.value or "").strip().lower()
        if is_hex(val):
            st["h"], st["s"], st["v"] = _hex_to_hsv(val)
            _sync()

    def _from_swatch(hx: str):
        st["h"], st["s"], st["v"] = _hex_to_hsv(hx)
        _sync()

    hex_field.on_blur = _from_hex
    hex_field.on_submit = _from_hex

    sv_gd = ft.GestureDetector(
        content=ft.Stack([sq_base, sq_white, sq_black, sq_dot], width=_SQ_W, height=_SQ_H),
        on_tap_down=_sv_at, on_pan_start=_sv_at, on_pan_update=_sv_at)
    hue_gd = ft.GestureDetector(
        content=ft.Stack([hue_track, hue_dot], width=_SQ_W, height=_HUE_H),
        on_tap_down=_hue_at, on_pan_start=_hue_at, on_pan_update=_hue_at)

    swatches = ft.Row(
        [ft.Container(width=22, height=22, border_radius=5, bgcolor=c,
                      border=ft.Border.all(1, COLORS["border_color"]),
                      on_click=lambda e, c=c: _from_swatch(c))
         for c in SWATCH_PALETTE],
        wrap=True, spacing=5, run_spacing=5)

    _sync(emit=False)

    def _done(e):
        page.pop_dialog()
        on_pick(_cur())

    actions = []
    if on_default is not None:
        actions.append(ft.TextButton(L.UI.SET_COLOR_DEFAULT,
                                     on_click=lambda e: (page.pop_dialog(), on_default())))
    actions += [
        ft.TextButton(L.UI.CANCEL, on_click=lambda e: page.pop_dialog()),
        ft.Button(L.UI.SAVE, on_click=_done),
    ]

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=ft.Text(title, size=15, weight=ft.FontWeight.BOLD),
        content=ft.Container(ft.Column([
            sv_gd,
            ft.Container(height=12),
            hue_gd,
            ft.Container(height=14),
            ft.Row([preview, ft.Column([hex_field, rgb_label], spacing=2, tight=True)], spacing=12),
            ft.Container(height=10),
            swatches,
        ], tight=True, spacing=0), width=_SQ_W),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    ))
