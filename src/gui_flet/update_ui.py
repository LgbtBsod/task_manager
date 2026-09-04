"""In-app software update: check quietly on start, *ask* before downloading.

A user without GitHub access must never be blocked — the check runs in the
background after the window is already up, every failure is swallowed, and
nothing is downloaded without an explicit click.
"""
import asyncio
import sys

import flet as ft

from core import strings as L

from .app import COLORS, ic

REPO_OWNER = "LgbtBsod"
REPO_NAME = "task_manager"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _make_updater(current_version: str):
    from utils.updater import AutoUpdater
    return AutoUpdater(REPO_OWNER, REPO_NAME, current_version)


async def check_on_start(app) -> None:
    """Silent background check when the app opens. Prompts only on success."""
    if not _is_frozen() or "--no-update" in sys.argv:
        return
    try:
        if not app.settings.get("check_updates_on_start"):
            return
        from utils.updater import _recently_checked
        if _recently_checked():
            return
        await _run_check(app, manual=False)
    except Exception:
        pass


def check_now(app) -> None:
    """Manual 'check for updates' — always reports back to the user."""
    if not _is_frozen():
        app._show_snackbar(L.UPDATE.ONLY_FROZEN)
        return
    app.page.run_task(_run_check, app, manual=True)


async def _run_check(app, *, manual: bool) -> None:
    from utils.updater import _mark_checked, get_current_version

    current = get_current_version()
    updater = _make_updater(current)
    has_update, version, url = await asyncio.to_thread(updater.check_for_updates)

    if not (updater._rate_limited or not updater._network_reachable):
        _mark_checked()

    if has_update and url:
        if not manual and version and version == app.settings.get("skipped_update_version"):
            return
        _prompt(app, current, version, url)
        return

    if not manual:
        return

    if updater._rate_limited:
        app._show_snackbar(L.UPDATE.RATE_LIMITED, error=True)
    elif not updater._network_reachable:
        app._show_snackbar(L.UPDATE.NO_SERVER, error=True)
    elif has_update and not url:
        app._show_snackbar(L.UPDATE.NOT_READY.format(version=version))
    else:
        app._show_snackbar(L.UPDATE.UP_TO_DATE)


def _prompt(app, current: str, version: str, url: str) -> None:
    page = app.page

    def close():
        page.pop_dialog()

    def later(e):
        close()

    def skip(e):
        app.settings.update(skipped_update_version=version)
        close()
        app._show_snackbar(L.UPDATE.SKIPPED)

    def download(e):
        close()
        page.run_task(_download_and_restart, app, url, version)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([ft.Icon(ic("system_update"), color=COLORS["accent_blue"]),
                      ft.Text(L.UPDATE.AVAILABLE_TITLE)], spacing=8),
        content=ft.Column([
            ft.Text(L.UPDATE.NEW_VERSION.format(version=version), size=14, weight=ft.FontWeight.W_600),
            ft.Text(L.UPDATE.CURRENT_VERSION.format(current=current), size=12,
                    color=COLORS["text_secondary"]),
            ft.Container(height=6),
            ft.Text(L.UPDATE.CONFIRM, size=12, color=COLORS["text_secondary"]),
        ], tight=True, width=380, spacing=2),
        actions=[
            ft.TextButton(L.UPDATE.BTN_SKIP, on_click=skip),
            ft.TextButton(L.UPDATE.BTN_LATER, on_click=later),
            ft.Button(L.UPDATE.BTN_UPDATE, on_click=download,
                      style=ft.ButtonStyle(bgcolor=COLORS["accent_blue"], color="#ffffff")),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


async def _download_and_restart(app, url: str, version: str) -> None:
    from utils.updater import get_current_version

    page = app.page
    bar = ft.ProgressBar(value=0, bar_height=8, color=COLORS["accent_blue"],
                         bgcolor=COLORS["bg_button"])
    status = ft.Text(L.UPDATE.DOWNLOADING, size=12, color=COLORS["text_secondary"])
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(L.UPDATE.DOWNLOADING_TO.format(version=version), size=16,
                      weight=ft.FontWeight.BOLD),
        content=ft.Column([status, ft.Container(height=8), bar],
                          tight=True, width=360, spacing=0),
    )
    page.show_dialog(dlg)

    def on_progress(p):
        try:
            if p.total_bytes:
                bar.value = max(0.0, min(1.0, p.percent / 100))
            status.value = (f"{p.percent:.0f}%   {p.formatted_speed}"
                            if p.total_bytes
                            else L.UPDATE.KB.format(n=p.bytes_downloaded // 1024))
            page.update()
        except Exception:
            pass

    updater = _make_updater(get_current_version())
    updater.progress_callback = on_progress

    ok = await asyncio.to_thread(updater.download_update, url, version)
    page.pop_dialog()

    if not ok:
        app._show_snackbar(L.UPDATE.INSTALL_FAILED, error=True)
        return

    # download_update has already swapped in the new binary and spawned the
    # relaunch helper; this process must exit so the helper can start it.
    done = ft.AlertDialog(
        modal=True,
        title=ft.Row([ft.Icon(ic("check_circle"), color=COLORS["accent_green"]),
                      ft.Text(L.UPDATE.INSTALLED_TITLE)], spacing=8),
        content=ft.Text(L.UPDATE.INSTALLED_BODY, size=12),
    )
    page.show_dialog(done)
    await asyncio.sleep(1.5)
    import os
    os._exit(0)
