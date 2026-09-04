"""AutoUpdater download path: progress model, size guards, error handling,
backup/restore, checksums. Network is mocked; all writes go to tmp_path."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.updater import AutoUpdater, DownloadProgress, UpdateError


def _updater():
    return AutoUpdater("owner", "repo", "1.0.0")


def _resp(*, header="1024", chunks=(b"x" * 512, b"y" * 512, b"")):
    r = Mock()
    r.getheader.return_value = header
    r.read.side_effect = list(chunks)
    r.__enter__ = Mock(return_value=r)
    r.__exit__ = Mock(return_value=False)
    return r


# ── DownloadProgress model ─────────────────────────────────────────────

def test_download_progress_defaults():
    p = DownloadProgress()
    assert p.bytes_downloaded == 0
    assert p.total_bytes == 0
    assert p.percent == 0.0
    assert not p.is_complete


def test_download_progress_is_complete():
    assert not DownloadProgress(bytes_downloaded=50, total_bytes=100).is_complete
    assert DownloadProgress(bytes_downloaded=100, total_bytes=100).is_complete
    assert not DownloadProgress(bytes_downloaded=50, total_bytes=200).is_complete


# ── _download_with_progress ────────────────────────────────────────────

def test_download_succeeds_with_valid_stream(tmp_path):
    cb = Mock()
    with patch("utils.updater.urlopen", return_value=_resp()):
        ok, err = _updater()._download_with_progress(
            "http://test/update.zip", tmp_path / "update.zip", cb)
    assert ok is True
    assert err == ""
    assert cb.called
    assert (tmp_path / "update.zip").read_bytes() == b"x" * 512 + b"y" * 512


def test_download_rejects_too_small(tmp_path):
    with patch("utils.updater.urlopen", return_value=_resp(header="100", chunks=(b"",))):
        ok, err = _updater()._download_with_progress(
            "http://test/tiny.zip", tmp_path / "tiny.zip")
    assert ok is False
    assert "small" in err.lower()


def test_download_rejects_too_large(tmp_path):
    huge = str(600 * 1024 * 1024)
    with patch("utils.updater.urlopen", return_value=_resp(header=huge, chunks=(b"",))):
        ok, err = _updater()._download_with_progress(
            "http://test/huge.zip", tmp_path / "huge.zip")
    assert ok is False
    assert "large" in err.lower()


def test_download_handles_http_error(tmp_path):
    err_obj = HTTPError("http://test", 404, "Not Found", {}, None)
    with patch("utils.updater.urlopen", side_effect=err_obj):
        ok, err = _updater()._download_with_progress(
            "http://test/missing.zip", tmp_path / "missing.zip")
    assert ok is False
    assert "404" in err or "HTTP" in err


def test_download_handles_network_error(tmp_path):
    with patch("utils.updater.urlopen", side_effect=URLError("unreachable")):
        ok, err = _updater()._download_with_progress(
            "http://test/x.zip", tmp_path / "x.zip")
    assert ok is False
    assert "network" in err.lower() or "unreachable" in err.lower()


# ── backup / restore ──────────────────────────────────────────────────

def test_backup_captures_version_and_db(tmp_path):
    (tmp_path / "version.txt").write_text("1.0.0")
    (tmp_path / "requirements.txt").write_text("flet\n")
    db = tmp_path / "data" / "db"
    db.mkdir(parents=True)
    (db / "tasks.json").write_text("[]")

    u = _updater()
    u.app_dir = tmp_path
    backup = u._create_backup()

    assert backup is not None and backup.exists()
    assert (backup / "version.txt").read_text() == "1.0.0"
    assert (backup / "requirements.txt").exists()
    assert (backup / "data" / "db" / "tasks.json").read_text() == "[]"


def test_restore_rolls_back_changed_files(tmp_path):
    (tmp_path / "version.txt").write_text("1.0.0")
    (tmp_path / "requirements.txt").write_text("original\n")

    u = _updater()
    u.app_dir = tmp_path
    u._create_backup()

    (tmp_path / "version.txt").write_text("2.0.0")
    (tmp_path / "requirements.txt").write_text("tampered\n")

    assert u._restore_from_backup() is True
    assert (tmp_path / "version.txt").read_text() == "1.0.0"
    assert (tmp_path / "requirements.txt").read_text() == "original\n"


def test_restore_without_backup_is_false(tmp_path):
    u = _updater()
    u.app_dir = tmp_path
    assert u._restore_from_backup() is False


# ── checksum / errors ─────────────────────────────────────────────────

def test_checksum_is_deterministic_sha256(tmp_path):
    f = tmp_path / "blob"
    f.write_bytes(b"test content for checksum")
    u = _updater()
    digest = u._calculate_checksum(f)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == u._calculate_checksum(f)


def test_update_error_recoverable_flag():
    assert str(UpdateError("boom")) == "boom"
    assert UpdateError("boom").recoverable is True
    assert UpdateError("fatal", recoverable=False).recoverable is False
