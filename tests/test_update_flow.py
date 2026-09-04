"""Self-update swap flow: the in-process binary swap and the version-file SSOT.

History: the "reports the new version but runs the old .exe" bug was a helper
that DELETEd the running exe (fails on Win10/11) — fixed by renaming instead.
That fix first shipped as a generated ``.vbs`` helper process; it's since been
inlined into the running binary itself (no script file ever touches disk) —
a freshly-written script that renames/moves files is exactly the shape
antivirus heuristics flag as a dropper, and a quarantined helper meant the
swap silently never applied. The running binary owns version.txt either way.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils import updater as updater_module
from utils.updater import AutoUpdater


def _updater(tmp_path) -> AutoUpdater:
    u = AutoUpdater("owner", "repo", "1.0.0")
    u.app_dir = tmp_path
    u.current_exe = tmp_path / "TaskManager-windows.exe"
    return u


def _target_and_staged(tmp_path, target_content=b"OLD", staged_content=b"NEW"):
    target = tmp_path / "TaskManager-windows.exe"
    staged = tmp_path / "TaskManager-windows.exe.updated"
    target.write_bytes(target_content)
    staged.write_bytes(staged_content)
    return target, staged


def test_swap_renames_running_exe_and_moves_staged_in(tmp_path):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)

    assert u._swap_windows_binary(target, staged) is True
    assert target.read_bytes() == b"NEW"                  # new binary now in place
    assert (tmp_path / "TaskManager-windows.exe.old").read_bytes() == b"OLD"
    assert not staged.exists()                            # staged file cleaned up


def test_swap_clears_a_stale_old_from_a_previous_run(tmp_path):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    (tmp_path / "TaskManager-windows.exe.old").write_bytes(b"STALE")

    assert u._swap_windows_binary(target, staged) is True
    assert (tmp_path / "TaskManager-windows.exe.old").read_bytes() == b"OLD"


def test_swap_retries_the_rename_then_succeeds(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    monkeypatch.setattr(updater_module.time, "sleep", lambda s: None)

    real_rename = Path.rename
    calls = {"n": 0}

    def flaky_rename(self, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("locked")
        return real_rename(self, dst)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    assert u._swap_windows_binary(target, staged) is True
    assert calls["n"] == 3
    assert target.read_bytes() == b"NEW"


def test_swap_gives_up_after_max_retries_and_leaves_exe_untouched(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    monkeypatch.setattr(updater_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(Path, "rename", lambda self, dst: (_ for _ in ()).throw(OSError("locked")))

    assert u._swap_windows_binary(target, staged) is False
    assert target.read_bytes() == b"OLD"                  # never touched
    assert staged.exists()                                # update stays staged for a retry


def test_swap_restores_old_exe_if_the_move_fails(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    monkeypatch.setattr(Path, "replace", lambda self, dst: (_ for _ in ()).throw(OSError("no space")))

    real_copy2 = shutil.copy2

    def fake_copy2(src, dst):
        if Path(src).name == staged.name:
            raise OSError("no space")   # putting the new binary in place also fails...
        return real_copy2(src, dst)     # ...but restoring the .old backup still works

    monkeypatch.setattr(shutil, "copy2", fake_copy2)
    assert u._swap_windows_binary(target, staged) is False
    assert target.read_bytes() == b"OLD"                  # restored, app never bricked


def test_relaunch_windows_swaps_then_launches_direct_with_breakaway(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)))

    u._relaunch_windows(target, staged)

    assert target.read_bytes() == b"NEW"                  # swap happened first
    assert len(calls) == 1
    argv, kw = calls[0]
    assert argv[0] == str(target) and "--no-update" in argv
    assert kw["creationflags"] & 0x01000000                # CREATE_BREAKAWAY_FROM_JOB


def test_relaunch_windows_falls_back_to_explorer(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    calls = []

    def fake_popen(argv, **kw):
        calls.append(argv)
        if len(calls) == 1:
            raise OSError("breakaway denied")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    u._relaunch_windows(target, staged)

    assert len(calls) == 2
    assert calls[1] == ["explorer.exe", str(target)]


def test_relaunch_windows_skips_launch_if_swap_failed(tmp_path, monkeypatch):
    u = _updater(tmp_path)
    target, staged = _target_and_staged(tmp_path)
    monkeypatch.setattr(updater_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(Path, "rename", lambda self, dst: (_ for _ in ()).throw(OSError("locked")))
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append(argv))

    u._relaunch_windows(target, staged)
    assert calls == []                                    # never try to launch a broken swap


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
