"""AppSettings / SettingsStore validation + the palette override layering."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.settings import DEFAULT_ACCENT, AppSettings, SettingsStore


def test_defaults():
    s = AppSettings()
    assert s.theme_mode == "dark"
    assert s.accent_color == DEFAULT_ACCENT == "#0070f2"
    assert s.custom_colors == {}
    assert 1 <= s.notify_hours_before <= 720


def test_invalid_values_fall_back():
    s = AppSettings(theme_mode="rainbow", accent_color="not-a-hex")
    assert s.theme_mode == "dark"
    assert s.accent_color == DEFAULT_ACCENT


def test_notify_ranges_reject_out_of_bounds():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AppSettings(notify_hours_before=0)
    with pytest.raises(ValidationError):
        AppSettings(notify_check_seconds=5)


def test_custom_colors_keeps_only_valid_hex():
    s = AppSettings(custom_colors={
        "bg_card": "#101010",
        "text_primary": "#ABCDEF",     # upper-case -> lowercased
        "border_color": "blue",        # dropped
        "accent_green": "#12345",      # too short -> dropped
        "bogus_token": "#000000",      # kept (palette filters unknown keys)
    })
    assert s.custom_colors == {
        "bg_card": "#101010",
        "text_primary": "#abcdef",
        "bogus_token": "#000000",
    }


def test_store_roundtrips_custom_colors(tmp_path):
    p = tmp_path / "settings.json"
    store = SettingsStore(str(p))
    store.set("custom_colors", {"bg_card": "#222222", "bad": "x"})
    store.set("accent_color", "#30d158")
    store.save()

    reloaded = SettingsStore(str(p))
    assert reloaded.get("custom_colors") == {"bg_card": "#222222"}
    assert reloaded.get("accent_color") == "#30d158"


def test_store_tolerates_missing_and_corrupt_file(tmp_path):
    assert SettingsStore(str(tmp_path / "nope.json")).get("theme_mode") == "dark"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert SettingsStore(str(bad)).get("theme_mode") == "dark"


def test_set_does_not_write_update_does(tmp_path):
    """The Settings-dialog live-preview path (``set_theme(persist=False)``)
    relies on ``store.set`` NOT touching the file; only Save (``update``) does."""
    p = tmp_path / "settings.json"
    store = SettingsStore(str(p))
    store.set("accent_color", "#30d158")
    assert not p.exists()                     # preview only, nothing persisted
    store.update(accent_color="#30d158")
    assert p.exists() and SettingsStore(str(p)).get("accent_color") == "#30d158"


def test_settings_dialog_module_imports_clean():
    from gui_flet.settings_dialog import show_settings_dialog
    assert callable(show_settings_dialog)


def test_single_instance_port_helpers():
    from gui_flet._single_instance import port_is_free, resolve_port
    # A port nobody is listening on resolves to itself.
    assert resolve_port(59_137) == 59_137
    assert port_is_free(59_137) is True


def test_readable_variant_leaves_passing_colors_alone():
    from gui_flet.palette import contrast_ratio, readable_variant
    assert readable_variant("#000000", "#ffffff") == "#000000"


def test_readable_variant_fixes_failing_dark_mode_accent_text():
    from gui_flet.palette import contrast_ratio, readable_variant
    fixed = readable_variant("#0070f2", "#1d232a")   # accent_blue on a dark card
    assert contrast_ratio("#0070f2", "#1d232a") < 4.5   # confirms the case is real
    assert contrast_ratio(fixed, "#1d232a") >= 4.5
    assert fixed != "#0070f2"


def test_readable_variant_fixes_failing_light_mode_accent_text():
    from gui_flet.palette import contrast_ratio, readable_variant
    fixed = readable_variant("#e76500", "#ffffff")   # accent_orange on a light card
    assert contrast_ratio("#e76500", "#ffffff") < 4.5
    assert contrast_ratio(fixed, "#ffffff") >= 4.5


def test_resolve_port_always_kills_and_reclaims_a_busy_port(monkeypatch):
    """No more 'reuse a healthy instance' branch — a busy port is always
    treated as an earlier instance of us and killed, so at most one instance
    ever holds it (closing the browser tab doesn't stop the local server, so
    without this a relaunch would just pile up another orphan)."""
    from gui_flet import _single_instance as si

    busy_then_free = iter([False, True])
    monkeypatch.setattr(si, "port_is_free", lambda p: next(busy_then_free, True))
    killed = []
    monkeypatch.setattr(si, "_kill_stale_on_port", lambda p: killed.append(p))
    monkeypatch.setattr(si.time, "sleep", lambda s: None)

    assert si.resolve_port(59_138) == 59_138
    assert killed == [59_138]


def test_resolve_port_falls_back_to_next_port_if_kill_does_not_free_it(monkeypatch):
    from gui_flet import _single_instance as si

    monkeypatch.setattr(si, "port_is_free", lambda p: p == 59_140)  # only the fallback is free
    monkeypatch.setattr(si, "_kill_stale_on_port", lambda p: None)
    monkeypatch.setattr(si.time, "sleep", lambda s: None)

    assert si.resolve_port(59_139) == 59_140


def test_palette_apply_layers_overrides():
    from gui_flet.palette import COLORS, apply, base_colors

    apply("dark", "#0a84ff", overrides={"bg_card": "#123456", "unknown": "#fff000"})
    assert COLORS["bg_card"] == "#123456"          # override wins
    assert COLORS["accent_blue"] == "#0a84ff"      # primary accent untouched
    assert "unknown" not in COLORS                 # unknown key filtered out

    apply("dark", "#0a84ff")                       # no overrides -> defaults
    assert COLORS["bg_card"] == base_colors(dark=True)["bg_card"]


def test_palette_is_hex():
    from gui_flet.palette import is_hex
    assert is_hex("#0a84ff")
    assert is_hex("#ABCDEF")
    assert not is_hex("0a84ff")
    assert not is_hex("#123")
    assert not is_hex("#gggggg")
