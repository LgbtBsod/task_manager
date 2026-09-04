"""Self-update swap flow: the relaunch helper and the version-file SSOT.

The "reports the new version but runs the old .exe" bug was: the helper
DELETEd the running exe (fails on Win10/11) and version.txt was bumped
regardless. The helper now RENAMEs, and the running binary owns version.txt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.updater import AutoUpdater


def _updater(tmp_path) -> AutoUpdater:
    u = AutoUpdater("owner", "repo", "1.0.0")
    u.app_dir = tmp_path
    u.current_exe = tmp_path / "TaskManager-windows.exe"
    return u


def test_relaunch_vbs_renames_not_deletes_the_running_exe(tmp_path):
    vbs = _updater(tmp_path)._write_relaunch_vbs("TaskManager-windows.exe")
    txt = vbs.read_text(encoding="utf-16")

    assert "fso.MoveFile exe, old" in txt          # rename the running exe
    assert "fso.DeleteFile exe, True" not in txt   # never delete a running image
    assert "fso.MoveFile staged, exe" in txt       # swap the new one in
    assert "restored old exe" in txt               # failure -> restore, never brick
    assert "update_helper.log" in txt              # self-logging for post-mortems
    assert 'exe = fso.BuildPath(d, "TaskManager-windows.exe")' in txt


def test_relaunch_vbs_is_clean_utf16(tmp_path):
    vbs = _updater(tmp_path)._write_relaunch_vbs("x.exe")
    raw = vbs.read_bytes()
    assert raw[:2] == b"\xff\xfe"                  # UTF-16 LE BOM
    text = raw.decode("utf-16")
    assert "\r\r" not in text                      # no text-mode newline doubling
    assert text.startswith("Option Explicit\r\n")


def test_stage_and_relaunch_rejects_non_exe(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    monkeypatch.setattr(u, "_relaunch_after_update", lambda: pytest_fail())
    html = tmp_path / "not-really.exe"
    html.write_bytes(b"<!DOCTYPE html><html>404</html>" + b"\0" * 2_000_000)
    assert u._stage_and_relaunch(html) is False
    assert not (tmp_path / "TaskManager-windows.exe.updated").exists()


def test_stage_and_relaunch_stages_a_real_pe(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    called = []
    monkeypatch.setattr(u, "_relaunch_after_update", lambda: called.append(1))
    exe = tmp_path / "new.exe"
    exe.write_bytes(b"MZ" + b"\0" * 2_000_000)     # PE magic + bulk
    assert u._stage_and_relaunch(exe) is True
    staged = tmp_path / "TaskManager-windows.exe.updated"
    assert staged.exists() and staged.read_bytes()[:2] == b"MZ"
    assert called == [1]


def test_frozen_updater_never_writes_app_dir_version(tmp_path, monkeypatch):
    """_stage_and_relaunch must not touch app_dir/version.txt — a bump that
    outlives a failed swap is the whole bug."""
    u = _updater(tmp_path)
    (tmp_path / "version.txt").write_text("1.0.0\n")
    monkeypatch.setattr(u, "_relaunch_after_update", lambda: None)
    exe = tmp_path / "new.exe"
    exe.write_bytes(b"MZ" + b"\0" * 2_000_000)
    u._stage_and_relaunch(exe)
    assert (tmp_path / "version.txt").read_text() == "1.0.0\n"   # untouched


def pytest_fail():
    raise AssertionError("_relaunch_after_update should not run for a bad download")
