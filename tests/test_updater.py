"""AutoUpdater — version comparison and the discovery ladder (web → API).

No network and no filesystem writes: discovery helpers are monkeypatched.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.updater import AutoUpdater, get_current_version, normalize_version


def _u(cur="1.0.0", *, frozen=True):
    u = AutoUpdater("owner", "repo", cur)
    u.is_frozen = frozen          # so _platform_asset() yields a real asset name
    return u


# ── version comparison (packaging / PEP 440) ────────────────────────────

@pytest.mark.parametrize("newer,older", [
    ("1.1", "1.0"),
    ("2.0", "1.9"),
    ("1.1.1", "1.1.0"),
    ("v2.0", "v1.0"),                                   # 'v' prefix tolerated
    ("1.1.0", "1.1.0b"),                                # stable > beta
    ("1.1.0rc1", "1.1.0b2"),                            # rc > beta
    ("1.1.0b2", "1.1.0b1"),
    ("1.0.0.0.0.0.2.1.17.b", "1.0.0.0.0.0.2.1.16.b"),   # legacy N-component scheme
    ("1.1.0", "1.0.0.0.0.0.2.1.16.b"),                  # semver outranks the legacy scheme
    ("v.1.0.0.0.0.0.2.1.17.b", "1.0.0.0.0.0.2.1.16.b"),
])
def test_is_newer(newer, older):
    assert AutoUpdater._is_newer_version(newer, older)
    assert not AutoUpdater._is_newer_version(older, newer)


def test_equal_is_not_newer():
    assert not AutoUpdater._is_newer_version("1.2.3", "1.2.3")
    assert not AutoUpdater._is_newer_version("v1.2.3", "1.2.3")


def test_normalize_version():
    assert normalize_version("v.1.0.0.0.0.0.2.1.16.b") == "1.0.0.0.0.0.2.1.16.b"
    assert normalize_version("  V1.1.0\n") == "1.1.0"
    assert normalize_version(".1.2.3") == "1.2.3"


def test_get_current_version_is_a_real_string():
    v = get_current_version()
    assert isinstance(v, str) and v and v != "unknown"


# ── init contract ──────────────────────────────────────────────────────

def test_init_urls():
    u = AutoUpdater("TestOwner", "TestRepo", "1.0.0")
    assert u.api_url == "https://api.github.com/repos/TestOwner/TestRepo"
    assert u.web_url == "https://github.com/TestOwner/TestRepo"
    assert isinstance(u.TIMEOUT_API, int) and u.TIMEOUT_API <= 10


def test_platform_asset_name():
    name = _u()._platform_asset()
    assert name in ("TaskManager-windows.exe", "TaskManager-linux", "TaskManager-macos")


# ── discovery ladder: atom feed first, API only as fallback ─────────────

def test_web_discovery_finds_newer(monkeypatch):
    u = _u("1.0.0")
    monkeypatch.setattr(u, "_atom_tags", lambda: ["v1.2.0", "v1.1.0", "v1.0.0"])
    monkeypatch.setattr(u, "_asset_available", lambda url: True)
    monkeypatch.setattr(u, "_api_get", lambda url: pytest.fail(f"API hit: {url}"))

    has, ver, url = u.check_for_updates()
    assert has is True
    assert ver == "v1.2.0"
    assert "/releases/download/v1.2.0/" in url


def test_web_discovery_up_to_date(monkeypatch):
    u = _u("1.2.0")
    monkeypatch.setattr(u, "_atom_tags", lambda: ["v1.2.0", "v1.1.0"])
    monkeypatch.setattr(u, "_api_get", lambda url: pytest.fail(f"API hit: {url}"))

    has, ver, url = u.check_for_updates()
    assert has is False
    assert url is None


def test_web_discovery_release_published_but_asset_not_ready(monkeypatch):
    u = _u("1.0.0")
    monkeypatch.setattr(u, "_atom_tags", lambda: ["v1.2.0"])
    monkeypatch.setattr(u, "_asset_available", lambda url: False)   # CI still uploading

    has, ver, url = u.check_for_updates()
    assert has is False
    assert ver == "v1.2.0"
    assert url is None


def test_falls_through_to_api_when_atom_empty(monkeypatch):
    u = _u("1.0.0")
    asset = u._platform_asset()          # windows/linux/macos — keep the test portable
    monkeypatch.setattr(u, "_atom_tags", lambda: [])
    seen = []

    def fake_api_get(url):
        seen.append(url)
        if "releases?per_page" in url:
            return [{"tag_name": "v2.0.0", "assets": [
                {"name": asset, "browser_download_url": "https://host/app"}]}]
        return None

    monkeypatch.setattr(u, "_api_get", fake_api_get)

    has, ver, url = u.check_for_updates()
    assert (has, ver, url) == (True, "v2.0.0", "https://host/app")
    assert any("releases?per_page" in s for s in seen)


def test_never_raises_and_is_fast_on_total_failure(monkeypatch):
    u = _u("1.0.0")
    monkeypatch.setattr(u, "_atom_tags", lambda: [])
    monkeypatch.setattr(u, "_api_get", lambda url: None)

    t0 = time.time()
    result = u.check_for_updates()
    assert result == (False, None, None)
    assert time.time() - t0 < 5
