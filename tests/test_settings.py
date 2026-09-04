"""AppSettings / SettingsStore validation + the palette override layering."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.settings import AppSettings, SettingsStore


def test_defaults():
    s = AppSettings()
    assert s.theme_mode == "dark"
    assert s.accent_color == "#0a84ff"
    assert s.custom_colors == {}
    assert 1 <= s.notify_hours_before <= 720


def test_invalid_values_fall_back():
    s = AppSettings(theme_mode="rainbow", accent_color="not-a-hex")
    assert s.theme_mode == "dark"
    assert s.accent_color == "#0a84ff"


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
