"""
Task Manager - Auto Updater Module

Responsibilities:
- Query GitHub releases for a newer version.
- Download a ZIP update bundle with progress tracking.
- Verify file integrity using checksums.
- Apply the update to the project root or the frozen EXE directory.
- Rollback on failure to maintain system stability.
- Relaunch the app after update installation.

This module keeps the update logic isolated from the GUI and startup flow.
"""
import hashlib
import json
import logging
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext | None:
    """A TLS context trusting certifi's CA bundle, or ``None`` (urlopen's own
    default) if certifi is unavailable.

    A frozen PyInstaller .exe can't always enumerate the OS trust store the
    way the interpreter's default context does — a stale/incomplete Windows
    cert store, antivirus TLS interception, or a machine with no configured
    trust anchors all surface as ``SSLCertVerificationError`` wrapped in a
    plain ``URLError`` here, which we can't tell apart from "no internet" and
    report as "no server access". Bundling certifi's own CA list sidesteps
    the OS store entirely — the standard fix for this exact failure mode in
    frozen Python apps (independently confirmed against another project's
    self-updater that hit the same symptom).
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None

SKIP_PATTERNS = {"venv", ".git", "__pycache__", "tasks.json", "data", "logs"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".tmp"}


def normalize_version(raw: str) -> str:
    """Strip a release-tag prefix (``v``, ``v.``, ``V.``) and surrounding
    punctuation so ``v.1.0.0.0.0.0.2.1.10.b`` becomes ``1.0.0.0.0.0.2.1.10.b``.

    Used both when writing ``version.txt`` and when reading it back, so the two
    always agree.
    """
    return str(raw).strip().lstrip("vV").strip(". \t\r\n")


@dataclass
class DownloadProgress:
    """Snapshot of an in-flight download, handed to the progress callback."""
    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0

    @property
    def percent(self) -> float:
        return self.bytes_downloaded / self.total_bytes * 100 if self.total_bytes else 0.0

    @property
    def is_complete(self) -> bool:
        return self.total_bytes > 0 and self.bytes_downloaded >= self.total_bytes

    @property
    def speed_mbps(self) -> float:
        return self.speed_bps / (1024 * 1024)

    @property
    def formatted_speed(self) -> str:
        if self.speed_bps < 1024:
            return f"{max(self.speed_bps, 0):.0f} B/s"
        if self.speed_bps < 1024 * 1024:
            return f"{self.speed_bps / 1024:.1f} KB/s"
        return f"{self.speed_mbps:.2f} MB/s"


class UpdateError(Exception):
    """Custom exception for update-related errors."""
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


class AutoUpdater:
    """Responsible only for checking and applying app updates."""

    TIMEOUT_API = 5
    TIMEOUT_DOWNLOAD = 120
    CHUNK_SIZE = 8192
    MIN_UPDATE_SIZE = 1024  # Minimum expected update size in bytes
    MAX_UPDATE_SIZE = 500 * 1024 * 1024  # 500 MB max update size

    def __init__(self, repo_owner: str, repo_name: str, current_version: str = "unknown"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version
        # Discovery goes through github.com (releases.atom + direct download
        # URLs) which is NOT subject to the 60-req/hour api.github.com limit.
        # The API is only a fallback. Both bases can be overridden for tests /
        # a self-hosted mirror.
        api_override = os.environ.get("TASKMANAGER_UPDATE_API", "").rstrip("/")
        web_override = os.environ.get("TASKMANAGER_UPDATE_WEB", "").rstrip("/")
        self.api_url = api_override or f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.web_url = web_override or f"https://github.com/{repo_owner}/{repo_name}"
        from core import paths
        self.is_frozen = paths.frozen
        self.app_dir = paths.app_dir
        self.current_exe = paths.exe_path
        self.backup_dir: Path | None = None
        self.progress_callback: Callable[[DownloadProgress], None] | None = None
        self._network_reachable: bool = True
        self._rate_limited: bool = False
        self._last_error: str | None = None
        self._ssl_context = _build_ssl_context()

    def _create_request(self, url: str) -> Request:
        req = Request(url)
        req.add_header("User-Agent", f"TaskManager/{self.current_version}")
        return req

    def _urlopen(self, req: Request, timeout: float):
        return urlopen(req, timeout=timeout, context=self._ssl_context)

    def _api_get(self, url: str) -> Any | None:
        try:
            with self._urlopen(self._create_request(url), self.TIMEOUT_API) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            # Server answered -> network is fine. 403 + rate-limit header means
            # GitHub is throttling this IP; make that visible rather than
            # silently reporting "up to date".
            if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                self._rate_limited = True
                logger.warning("GitHub API rate limit hit — update check skipped this run")
            else:
                logger.debug("API request failed: %s", exc)
            return None
        except (URLError, TimeoutError) as exc:
            self._last_error = str(getattr(exc, "reason", exc))
            logger.debug("Network unreachable: %s", exc)
            self._network_reachable = False
            return None
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("Unexpected API error: %s", exc)
            self._network_reachable = False
            return None

    def _download_with_progress(
        self,
        url: str,
        dest_path: Path,
        progress_callback: Callable[[DownloadProgress], None] | None = None
    ) -> tuple[bool, str]:
        """Download a file with progress tracking and validation.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            req = self._create_request(url)
            req.add_header('Accept', 'application/octet-stream')

            with self._urlopen(req, self.TIMEOUT_DOWNLOAD) as resp:
                # Handle redirects by following them automatically
                final_url = resp.url if hasattr(resp, 'url') else url

                # Try to get Content-Length, may not be available for all URLs
                total_size = int(resp.getheader('Content-Length', 0))

                # For GitHub releases, the size might not be available initially
                # In this case, we'll download without size validation
                if total_size == 0 and 'github' in final_url.lower():
                    logger.debug("GitHub URL detected, size validation skipped")

                downloaded = 0
                start_time = time.monotonic()
                progress = DownloadProgress(total_bytes=total_size)
                last_update_time = start_time

                with open(dest_path, 'wb') as dest_file:
                    while chunk := resp.read(self.CHUNK_SIZE):
                        dest_file.write(chunk)
                        downloaded += len(chunk)
                        progress.bytes_downloaded = downloaded

                        now = time.monotonic()
                        if now - last_update_time >= 0.5:
                            elapsed = now - start_time
                            if elapsed > 0:
                                progress.speed_bps = downloaded / elapsed
                            last_update_time = now

                        if progress_callback:
                            progress_callback(progress)

                total_elapsed = time.monotonic() - start_time
                if total_elapsed > 0:
                    progress.speed_bps = downloaded / total_elapsed

                # Validate size only if we had a valid Content-Length header
                if total_size > 0:
                    if total_size < self.MIN_UPDATE_SIZE:
                        return False, f"Update file too small: {total_size} bytes"

                    if total_size > self.MAX_UPDATE_SIZE:
                        return False, f"Update file too large: {total_size} bytes"

                    if downloaded != total_size:
                        return False, f"Incomplete download: {downloaded}/{total_size} bytes"
                else:
                    # No size info available, just check we got something
                    if downloaded < self.MIN_UPDATE_SIZE:
                        return False, f"Downloaded file too small: {downloaded} bytes"

                logger.info("Download completed: %s (%.0f KB in %s, %.2f MB/s)",
                            dest_path.name, downloaded / 1024,
                            timedelta(seconds=round(total_elapsed)), progress.speed_mbps)
                return True, ""

        except HTTPError as exc:
            return False, f"HTTP error {exc.code}: {exc.reason}"
        except URLError as exc:
            return False, f"Network error: {exc.reason}"
        except Exception as exc:
            return False, f"Download failed: {str(exc)}"

    @staticmethod
    def _is_newer_version(latest: str, current: str) -> bool:
        """PEP 440 comparison via ``packaging``. The project uses semver
        (``2.2.0``) but older releases carry the legacy N-component scheme
        (``1.0.0.0.0.0.2.1.16.b``); ``packaging`` orders both correctly, and
        any semver release outranks every legacy tag, so the feed stays sane
        through the transition.
        """
        from packaging.version import InvalidVersion, Version
        try:
            return Version(normalize_version(latest)) > Version(normalize_version(current))
        except InvalidVersion:
            a, b = latest.strip(), current.strip()
            return a != b and a > b

    def _platform_asset(self) -> str | None:
        """The exact release-asset filename for this OS (matches build.yml)."""
        if not self.is_frozen:
            return None
        return {"win32": "TaskManager-windows.exe",
                "darwin": "TaskManager-macos"}.get(sys.platform, "TaskManager-linux")

    def _asset_keywords(self) -> list:
        """Substrings that identify the release asset for this OS, best first."""
        if not self.is_frozen:
            return [".zip"]
        if sys.platform == "win32":
            return ["windows", ".exe"]
        if sys.platform == "darwin":
            return ["macos", "mac", "darwin", ".app", ".dmg"]
        return ["linux"]

    # ── Discovery via github.com (no API rate limit) ──────────────────────

    def _http_text(self, url: str) -> str | None:
        try:
            with self._urlopen(self._create_request(url), self.TIMEOUT_API) as resp:
                return resp.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code in (403, 429):
                self._rate_limited = True
            logger.debug("web GET %s failed: %s", url, exc)
        except (URLError, TimeoutError) as exc:
            self._last_error = str(getattr(exc, "reason", exc))
            logger.debug("web GET %s unreachable: %s", url, exc)
            self._network_reachable = False
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("web GET %s error: %s", url, exc)
        return None

    def _atom_tags(self) -> list[str]:
        """Release tags from ``<web>/releases.atom``, newest first. []  on failure."""
        import re
        xml = self._http_text(f"{self.web_url}/releases.atom")
        if not xml:
            return []
        # <link ... href=".../releases/tag/<TAG>"/>  — order = newest first
        return list(dict.fromkeys(re.findall(r"/releases/tag/([^\"'<>\s]+)", xml)))

    def _web_asset_url(self, tag: str) -> str | None:
        asset = self._platform_asset()
        return f"{self.web_url}/releases/download/{tag}/{asset}" if asset else None

    def _asset_available(self, url: str) -> bool:
        """True if the asset URL resolves to a real download (not a 404 because
        the release exists but CI is still uploading its binaries)."""
        try:
            req = self._create_request(url)
            req.add_header("Range", "bytes=0-0")
            with self._urlopen(req, self.TIMEOUT_API) as resp:
                return resp.status in (200, 206)
        except HTTPError as exc:
            return exc.code in (200, 206, 416)
        except Exception:
            return False

    def _check_via_web(self) -> tuple[bool, str | None, str | None] | None:
        """Atom-feed discovery. Returns a check_for_updates result, or None to
        let the caller fall through to the API."""
        tags = self._atom_tags()
        if not tags:
            return None
        newer = [t for t in tags if self._is_newer_version(t, self.current_version)]
        if not newer:
            logger.info("Up to date (newest tag: %s, current: %s)", tags[0], self.current_version)
            return False, tags[0], None
        newest = newer[0]                       # atom feed is newest-first
        url = self._web_asset_url(newest)
        if url and self._asset_available(url):
            logger.info("New version available: %s (via releases.atom)", newest)
            return True, newest, url
        logger.info("Release %s is published but its asset isn't ready yet", newest)
        return False, newest, None

    def _resolve_download_url(self, release_info: dict[str, Any]) -> str | None:
        assets = release_info.get("assets") or []
        for keyword in self._asset_keywords():
            for asset in assets:
                name = str(asset.get("name") or "").lower()
                if keyword in name:
                    return asset.get("browser_download_url")
        # Source checkout (not frozen): fall back to the auto-generated zipball.
        if not self.is_frozen:
            return release_info.get("zipball_url")
        return None

    def _pick_release(self, releases: list) -> dict[str, Any] | None:
        """From a list of releases, the newest one that beats the current
        version *and* ships an asset for this platform.

        We don't lean on GitHub's ``/releases/latest`` pointer: the legacy
        non-semver tags (``v.1.0.0.0.0.0.2.1.9.b``) left it stuck on an older
        release, and picking by our own comparison is robust either way.
        """
        best: dict[str, Any] | None = None
        best_tag: str | None = None
        for rel in releases:
            if rel.get("draft"):
                continue
            tag = str(rel.get("tag_name") or "").strip()
            if not tag or not self._is_newer_version(tag, self.current_version):
                continue
            if not self._resolve_download_url(rel):
                logger.info("Release %s has no asset for this platform yet — skipping", tag)
                continue
            if best is None or self._is_newer_version(tag, best_tag or ""):
                best, best_tag = rel, tag
        return best

    def check_for_updates(self) -> tuple[bool, str | None, str | None]:
        # 1) github.com/releases.atom + a direct download URL — no API limit.
        web = self._check_via_web()
        if web is not None:
            return web

        # 2) API fallback. Prefer the full list (newest-first) over
        #    /releases/latest — see _pick_release for why "latest" can't be trusted.
        releases = self._api_get(f"{self.api_url}/releases?per_page=20")
        if isinstance(releases, list) and releases:
            chosen = self._pick_release(releases)
            if chosen:
                tag = str(chosen.get("tag_name") or "").strip()
                url = self._resolve_download_url(chosen)
                logger.info("New version available: %s", tag)
                return True, tag, url
            newest = str(releases[0].get("tag_name") or "unknown").strip()
            logger.info("Up to date (newest release: %s, current: %s)", newest, self.current_version)
            return False, newest, None

        release_info = self._api_get(f"{self.api_url}/releases/latest")
        if release_info:
            latest_version = str(release_info.get("tag_name") or "unknown").strip()
            zip_url = self._resolve_download_url(release_info)
            if zip_url and self._is_newer_version(latest_version, self.current_version):
                logger.info("New version available: %s", latest_version)
                return True, latest_version, zip_url
            return False, latest_version, None

        # No release found. Skip the commit-SHA fallback entirely when the
        # network is down (it would just burn another timeout).
        if not self._network_reachable:
            return False, None, None

        import re

        commit_info = self._api_get(f"{self.api_url}/commits/main")
        if commit_info:
            latest_sha = str(commit_info.get("sha") or "")[:7]
            zip_url = f"{self.api_url}/zipball/main"
            if (
                self.current_version != "unknown"
                and latest_sha
                and latest_sha != self.current_version[:7]
                and not re.match(r"^v?\d+\.\d+", self.current_version)
            ):
                return True, latest_sha, zip_url
        return False, None, None

    def _create_backup(self) -> Path | None:
        """Snapshot critical files + the user database before an update."""
        try:
            backup_base = self.app_dir / ".update_backup"
            backup_base.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self.backup_dir = backup_base / f"backup_{stamp}"
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            for fname in ("version.txt", "requirements.txt"):
                src = self.app_dir / fname
                if src.exists():
                    shutil.copy2(src, self.backup_dir / fname)

            data_src = self.app_dir / "data" / "db"
            if data_src.is_dir():
                shutil.copytree(data_src, self.backup_dir / "data" / "db",
                                dirs_exist_ok=True)

            # Keep only the 5 most recent backups.
            old_backups = sorted(
                (d for d in backup_base.glob("backup_*") if d.is_dir()),
                key=lambda d: d.name,
            )
            for old in old_backups[:-5]:
                shutil.rmtree(old, ignore_errors=True)

            logger.info("Backup created at: %s", self.backup_dir)
            return self.backup_dir

        except Exception as exc:
            logger.warning("Failed to create backup: %s", exc)
            return None

    def _restore_from_backup(self) -> bool:
        """Restore from backup if update fails."""
        if not self.backup_dir or not self.backup_dir.exists():
            logger.warning("No backup available for restoration")
            return False

        try:
            for item in self.backup_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, self.app_dir / item.name)
            data_backup = self.backup_dir / "data" / "db"
            if data_backup.is_dir():
                shutil.copytree(data_backup, self.app_dir / "data" / "db",
                                dirs_exist_ok=True)
            logger.info("Successfully restored from backup")
            return True

        except Exception as exc:
            logger.error("Failed to restore from backup: %s", exc)
            return False

    def _cleanup_backup(self) -> None:
        """Clean up backup directory after successful update."""
        if self.backup_dir and self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir, ignore_errors=True)
                logger.debug("Backup cleaned up successfully")
            except Exception as exc:
                logger.warning("Failed to cleanup backup: %s", exc)

    def _calculate_checksum(self, file_path: Path, algorithm: str = "sha256") -> str:
        """File checksum for integrity verification / logging."""
        with open(file_path, "rb") as f:
            return hashlib.file_digest(f, algorithm).hexdigest()

    def _find_source_root(self, extracted_dir: Path) -> Path:
        for candidate in sorted(extracted_dir.iterdir(), key=lambda p: p.name.lower()):
            if candidate.is_dir():
                return candidate
        return extracted_dir

    def _find_exe_in_bundle(self, source_folder: Path, preferred_name: str | None = None) -> Path | None:
        candidates = list(source_folder.rglob("*.exe"))
        if not candidates:
            return None
        preferred = (preferred_name or "").lower()
        return next((i for i in candidates if i.name.lower() == preferred), candidates[0])

    def _copy_update_files(self, source_folder: Path) -> int:
        files_copied = 0
        for item in source_folder.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(source_folder)
            parts = rel.parts
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in SKIP_PATTERNS for p in parts):
                continue
            if item.suffix.lower() in SKIP_EXTENSIONS:
                continue
            dest = self.app_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, dest)
                files_copied += 1
            except PermissionError:
                logger.warning("Skipping locked file: %s", rel)
        return files_copied

    def _update_version_file(self, new_version: str) -> None:
        version_file = self.app_dir / "version.txt"
        clean = normalize_version(new_version)
        try:
            version_file.write_text(clean + "\n", encoding="utf-8")
            logger.info("Version updated to %s", clean)
        except Exception as exc:
            logger.warning("Could not update version.txt: %s", exc)

    def _relaunch_after_update(self) -> None:
        """Hand the binary swap + restart to a detached helper.

        The helper waits for THIS process to exit before touching the .exe, so
        the file is never swapped while it is still locked (the cause of the
        stuck ``TaskManager.exe.old`` and zombie processes users saw).
        """
        if not self.current_exe:
            return
        target = self.current_exe
        staged = self.app_dir / f"{target.name}.updated"
        if not staged.exists():
            return

        if sys.platform == "win32":
            self._relaunch_windows(target, staged)
        else:
            self._relaunch_posix(target, staged)

    def _swap_windows_binary(self, target: Path, staged: Path) -> bool:
        """Rename the running .exe to ``.old`` and move the staged update into
        its place — synchronously, in THIS process, before it exits.

        An earlier design handed this off to a generated ``.vbs`` helper (a
        separate detached process was assumed necessary to touch the .exe
        after we exit). But Windows allows *renaming* a running image
        immediately — only *deleting* it fails until every handle is gone —
        so there's nothing stopping the swap from happening right here, and
        nothing left for a helper to do. That helper turned into its own
        failure mode: a freshly-written ``.vbs`` that renames/moves files is
        exactly the shape antivirus heuristics flag as a dropper, and a
        quarantined helper meant "downloaded fine, but the update silently
        never applies" — which is what users were seeing. Doing the swap in
        our own already-running (already-trusted) binary removes that file
        from the picture entirely.

        Retries the rename for up to ~30s (AV real-time scanning or another
        handle can transiently hold the file); restores ``.old`` if the swap
        can't complete so the app is never left without a runnable .exe.
        """
        old = target.with_name(target.name + ".old")
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass

        renamed = False
        for _ in range(60):
            try:
                target.rename(old)
                renamed = True
                break
            except OSError:
                time.sleep(0.5)
        logger.info("Update swap: renamed running exe -> .old: %s", renamed)
        if not renamed:
            logger.error("Update swap: could not rename the running exe — "
                         "leaving it in place; the update stays staged.")
            return False

        try:
            staged.replace(target)
            logger.info("Update swap: staged update moved into place")
        except OSError as exc:
            logger.warning("Update swap: move failed (%s); trying copy", exc)
            try:
                shutil.copy2(staged, target)
            except OSError as exc2:
                logger.error("Update swap: copy also failed: %s", exc2)

        if not target.exists():
            try:
                shutil.copy2(old, target)
                logger.error("Update swap FAILED — restored the previous exe")
                return False
            except OSError as exc:
                logger.critical("Update swap FAILED and restore also failed: %s", exc)
                return False

        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def _relaunch_windows(self, target: Path, staged: Path) -> None:
        """Swap the binary in place, then relaunch outside this process's
        PyInstaller job object so exiting doesn't kill the new instance.

        A direct ``Popen`` with ``CREATE_BREAKAWAY_FROM_JOB`` is tried first
        (it can pass ``--no-update``); if the job disallows breakaway,
        ``explorer.exe <exe>`` — a completely separate process, unrelated to
        our job by construction — is the fallback (it can't forward args, so
        the new instance runs one ordinary startup update-check instead).
        """
        if not self._swap_windows_binary(target, staged):
            return

        DETACHED = 0x00000008 | 0x01000000   # DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB
        for how, argv, flags in (
            ("direct", [str(target), "--no-update"], DETACHED),
            ("explorer", ["explorer.exe", str(target)], 0),
        ):
            try:
                subprocess.Popen(argv, creationflags=flags, close_fds=True)
                logger.info("Relaunched via %s; exiting.", how)
                return
            except OSError as exc:
                logger.warning("Relaunch via %s failed (%s)", how, exc)
        logger.error("Update installed but could not relaunch — start the app manually.")

    def _relaunch_posix(self, target: Path, staged: Path) -> None:
        """POSIX keeps a running binary alive via its open inode, so we can
        replace the file in place and just spawn the new one detached."""
        try:
            os.replace(staged, target)   # atomic; the running process is unaffected
            target.chmod(0o755)
            subprocess.Popen([str(target), "--no-update"], start_new_session=True,
                             cwd=str(self.app_dir), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Update swapped in; new instance spawned.")
        except OSError as exc:
            logger.error("Update installed but relaunch failed (%s); "
                         "restart the app manually.", exc)

    def _install_frozen_update(self, source_folder: Path, latest_version: str) -> bool:
        if not self.current_exe:
            return False

        # The new version ships *inside* the bundled exe (its _MEIPASS/version.txt);
        # main.py mirrors that to app_dir/version.txt on the next start. We never
        # write app_dir/version.txt here — a bump that outlived a failed swap was
        # exactly the "reports new version, runs old code" bug.
        exe_name = self.current_exe.name
        bundled_exe = self._find_exe_in_bundle(source_folder, exe_name)
        if not bundled_exe:
            return False
        return self._stage_and_relaunch(bundled_exe)

    def _install_frozen_executable(self, downloaded_exe: Path, latest_version: str) -> bool:
        if not self.current_exe or not downloaded_exe.exists():
            return False
        return self._stage_and_relaunch(downloaded_exe)

    def _stage_and_relaunch(self, new_exe: Path) -> bool:
        """Copy *new_exe* to ``<exe>.updated`` and hand the swap to the helper.

        Rejects a download that isn't a Windows PE image (an HTML error page,
        a truncated file) before staging it.
        """
        try:
            with open(new_exe, "rb") as f:
                head = f.read(2)
        except OSError:
            return False
        if sys.platform == "win32" and head != b"MZ":
            logger.error("Downloaded update is not an .exe (starts %r) — aborting", head)
            return False

        staged_exe = self.app_dir / f"{self.current_exe.name}.updated"
        try:
            shutil.copy2(new_exe, staged_exe)
        except OSError as exc:
            logger.error("Could not stage the update: %s", exc)
            return False
        if not staged_exe.exists() or staged_exe.stat().st_size < self.MIN_UPDATE_SIZE:
            return False
        self._relaunch_after_update()
        return True

    def download_update(self, zip_url: str, latest_version: str) -> bool:
        """Download and install update with progress tracking and rollback support."""
        if not zip_url:
            return False

        temp_dir = None
        try:
            # Create backup before starting update
            self._create_backup()

            temp_base = Path(tempfile.gettempdir()) / "task_manager_update"
            temp_base.mkdir(parents=True, exist_ok=True)
            temp_dir = temp_base / f"update_{latest_version.replace('.', '_')}_{os.getpid()}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            zip_path = temp_dir / "update.zip"
            logger.info("Downloading update from %s", zip_url)

            # Download with progress tracking
            success, error_msg = self._download_with_progress(
                zip_url,
                zip_path,
                self.progress_callback
            )

            if not success:
                logger.error("Download failed: %s", error_msg)
                raise UpdateError(f"Download failed: {error_msg}", recoverable=True)

            # Verify downloaded file exists and has content
            if not zip_path.exists() or zip_path.stat().st_size < self.MIN_UPDATE_SIZE:
                raise UpdateError("Downloaded file is empty or missing", recoverable=True)

            # Calculate checksum for logging
            checksum = self._calculate_checksum(zip_path)
            logger.info("Download verified. SHA256: %s", checksum[:16])

            url_path = zip_url.lower().split("?", 1)[0]
            is_raw_binary = self.is_frozen and not url_path.endswith((".zip", ".tar.gz", ".tgz"))
            if is_raw_binary:
                result = self._install_frozen_executable(zip_path, latest_version)
                if result:
                    logger.info("Executable update staged successfully: %s", latest_version)
                    self._cleanup_backup()
                else:
                    self._restore_from_backup()
                return result

            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    # Verify ZIP integrity
                    bad_file = zf.testzip()
                    if bad_file is not None:
                        raise UpdateError(f"Corrupted ZIP entry: {bad_file}", recoverable=False)
                    zf.extractall(extracted_dir)
            except zipfile.BadZipFile as exc:
                raise UpdateError(f"Invalid ZIP archive: {exc}", recoverable=False) from exc

            source_folder = self._find_source_root(extracted_dir)

            if self.is_frozen:
                result = self._install_frozen_update(source_folder, latest_version)
            else:
                result = self._copy_update_files(source_folder) > 0
                self._update_version_file(latest_version)

            if result:
                logger.info("Update installed successfully: %s", latest_version)
                self._cleanup_backup()
            else:
                logger.warning("Update installation returned no changes")
                self._restore_from_backup()

            return result

        except UpdateError as exc:
            logger.error("Update error: %s", exc)
            if exc.recoverable:
                self._restore_from_backup()
            return False
        except Exception as exc:
            logger.error("Unexpected update error: %s", exc)
            self._restore_from_backup()
            return False
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _say(message: str) -> None:
        """Print to console if we have one, always mirror to the log."""
        logger.info(message)
        try:
            if sys.stdout is not None:
                print(message)
        except Exception:
            pass

    def run_update_check(self, auto: bool = False) -> bool:
        logger.info("Checking for updates (current: %s)", self.current_version)
        has_update, latest_version, download_url = self.check_for_updates()

        if not has_update:
            if self._rate_limited:
                self._say("[Update] GitHub is rate-limiting this network — will retry next launch.")
            elif not self._network_reachable:
                logger.warning("Update server unreachable — skipped update check (%s)",
                               self._last_error or "no details")
            elif download_url is None and latest_version and latest_version != "unknown" \
                    and self._is_newer_version(latest_version, self.current_version):
                self._say(f"[Update] {latest_version} is published but its download "
                          f"isn't ready yet — will retry next launch.")
            else:
                logger.info("Already up to date (current: %s)", self.current_version)
            return False

        if auto and download_url:
            self._say(f"[Update] New version {latest_version} — downloading...")
            ok = self.download_update(download_url, latest_version)
            self._say("[Update] Installed; the app will restart." if ok
                      else "[Update] Could not install the update.")
            return ok

        self._say(f"[Update] Version {latest_version} is available "
                  f"(current: {self.current_version}). Restart to apply.")
        return False


def get_current_version() -> str:
    from core import paths
    v = paths.read_version()
    if v != "unknown":
        return v

    if not paths.frozen:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=str(paths.app_dir),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    return "unknown"


_CHECK_INTERVAL_SECONDS = 30 * 60


def _check_stamp_path() -> Path:
    from core.paths import logs_dir
    return logs_dir / ".last_update_check"


def _recently_checked() -> bool:
    """True if an update check already ran in the last _CHECK_INTERVAL_SECONDS.

    Keeps a machine (and, on a shared IP, a whole office) from hammering the
    GitHub API — the unauthenticated limit is 60 requests/hour for the IP.
    """
    try:
        age = time.time() - _check_stamp_path().stat().st_mtime
        return 0 <= age < _CHECK_INTERVAL_SECONDS
    except OSError:
        return False


def _mark_checked() -> None:
    try:
        p = _check_stamp_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    except OSError:
        pass


def check_updates(repo_owner: str, repo_name: str, auto: bool = False,
                  force: bool = False) -> bool:
    if auto and not force and _recently_checked():
        logger.info("Update check skipped (ran within the last 30 min)")
        return False
    current_version = get_current_version()
    logger.info("Current version: %s", current_version)
    updater = AutoUpdater(repo_owner, repo_name, current_version)
    result = updater.run_update_check(auto=auto)
    if not updater._rate_limited and updater._network_reachable:
        _mark_checked()
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Task Manager - Проверка обновлений")
    print("=" * 50)
    check_updates("LgbtBsod", "task_manager", auto=False)
