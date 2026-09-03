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
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

SKIP_PATTERNS = {"venv", ".git", "__pycache__", "tasks.json", "data", "logs"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".tmp"}


@dataclass(frozen=True)
class UpdateJob:
    has_update: bool
    latest_version: Optional[str]
    download_url: Optional[str]


@dataclass
class DownloadProgress:
    """Tracks download progress with additional metadata."""
    bytes_downloaded: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    speed_bps: float = 0.0  # Bytes per second
    elapsed_time: float = 0.0  # Seconds since download started
    eta_seconds: float = 0.0  # Estimated time remaining
    
    def __post_init__(self):
        """Calculate percent if total_bytes is known."""
        if self.total_bytes > 0:
            object.__setattr__(self, 'percent', (self.bytes_downloaded / self.total_bytes) * 100)
    
    @property
    def is_complete(self) -> bool:
        return self.total_bytes > 0 and self.bytes_downloaded >= self.total_bytes
    
    @property
    def speed_mbps(self) -> float:
        """Return download speed in Mbps."""
        return self.speed_bps / (1024 * 1024)
    
    @property
    def formatted_eta(self) -> str:
        """Return formatted ETA string (MM:SS)."""
        if self.eta_seconds <= 0:
            return "--:--"
        # Cap at 99 hours to avoid very long strings
        capped_eta = min(self.eta_seconds, 99 * 3600 + 59 * 60 + 59)
        hours = int(capped_eta // 3600)
        minutes = int((capped_eta % 3600) // 60)
        seconds = int(capped_eta % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def formatted_speed(self) -> str:
        """Return formatted speed string (B/s, KB/s, or MB/s)."""
        if self.speed_bps < 0:
            return "0 B/s"
        if self.speed_bps < 1024:
            return f"{self.speed_bps:.0f} B/s"
        elif self.speed_bps < 1024 * 1024:
            return f"{self.speed_bps / 1024:.1f} KB/s"
        else:
            return f"{self.speed_mbps:.2f} MB/s"
    
    def update_progress(self, bytes_downloaded: int, elapsed_time: float, total_bytes: Optional[int] = None):
        """Update progress metrics and recalculate derived values.
        
        Args:
            bytes_downloaded: Total bytes downloaded so far
            elapsed_time: Time elapsed since download started (seconds)
            total_bytes: Optional new total bytes value
        """
        object.__setattr__(self, 'bytes_downloaded', bytes_downloaded)
        object.__setattr__(self, 'elapsed_time', elapsed_time)
        
        if total_bytes is not None:
            object.__setattr__(self, 'total_bytes', total_bytes)
        
        # Recalculate speed
        if elapsed_time > 0:
            object.__setattr__(self, 'speed_bps', bytes_downloaded / elapsed_time)
        
        # Recalculate percent
        if self.total_bytes > 0:
            object.__setattr__(self, 'percent', (bytes_downloaded / self.total_bytes) * 100)
        
        # Recalculate ETA
        if self.speed_bps > 0 and self.total_bytes > 0:
            remaining_bytes = max(0, self.total_bytes - bytes_downloaded)
            object.__setattr__(self, 'eta_seconds', remaining_bytes / self.speed_bps)
        else:
            object.__setattr__(self, 'eta_seconds', 0.0)


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
        # TASKMANAGER_UPDATE_API lets you point the updater at a self-hosted
        # GitHub-compatible endpoint (or a test server). Must expose
        # `<base>/releases/latest`.
        override = os.environ.get("TASKMANAGER_UPDATE_API", "").rstrip("/")
        self.api_url = override or f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.is_frozen = bool(getattr(sys, "frozen", False))
        self.app_dir = (
            Path(sys.executable).resolve().parent
            if self.is_frozen
            else Path(__file__).resolve().parent.parent.parent
        )
        self.current_exe = Path(sys.executable).resolve() if self.is_frozen else None
        self.backup_dir: Optional[Path] = None
        self.progress_callback: Optional[Callable[[DownloadProgress], None]] = None
        self._network_reachable: bool = True

    def _create_request(self, url: str) -> Request:
        req = Request(url)
        req.add_header("User-Agent", f"TaskManager/{self.current_version}")
        return req

    def _api_get(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            with urlopen(self._create_request(url), timeout=self.TIMEOUT_API) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            # Server answered (e.g. 404 "no releases yet") -> network is fine.
            logger.debug("API request failed: %s", exc)
            return None
        except (URLError, TimeoutError) as exc:
            logger.debug("Network unreachable: %s", exc)
            self._network_reachable = False
            return None
        except Exception as exc:
            logger.debug("Unexpected API error: %s", exc)
            self._network_reachable = False
            return None

    def _download_with_progress(
        self, 
        url: str, 
        dest_path: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> Tuple[bool, str]:
        """Download a file with progress tracking and validation.
        
        Returns:
            Tuple of (success, error_message)
        """
        import time
        
        try:
            req = self._create_request(url)
            req.add_header('Accept', 'application/octet-stream')
            
            with urlopen(req, timeout=self.TIMEOUT_DOWNLOAD) as resp:
                # Handle redirects by following them automatically
                final_url = resp.url if hasattr(resp, 'url') else url
                
                # Try to get Content-Length, may not be available for all URLs
                total_size = int(resp.getheader('Content-Length', 0))
                
                # For GitHub releases, the size might not be available initially
                # In this case, we'll download without size validation
                if total_size == 0 and 'github' in final_url.lower():
                    logger.debug("GitHub URL detected, size validation skipped")
                
                downloaded = 0
                start_time = time.time()
                progress = DownloadProgress(total_bytes=total_size)
                last_update_time = start_time
                bytes_since_last_update = 0
                
                with open(dest_path, 'wb') as dest_file:
                    while True:
                        chunk = resp.read(self.CHUNK_SIZE)
                        if not chunk:
                            break
                        
                        dest_file.write(chunk)
                        downloaded += len(chunk)
                        bytes_since_last_update += len(chunk)
                        
                        current_time = time.time()
                        elapsed = current_time - start_time
                        
                        # Update speed and ETA every 0.5 seconds
                        if current_time - last_update_time >= 0.5:
                            if elapsed > 0:
                                progress.speed_bps = downloaded / elapsed
                            
                            # Calculate ETA based on current speed
                            remaining_bytes = max(0, total_size - downloaded) if total_size > 0 else 0
                            if progress.speed_bps > 0 and total_size > 0:
                                progress.eta_seconds = remaining_bytes / progress.speed_bps
                            else:
                                progress.eta_seconds = 0
                            
                            progress.elapsed_time = elapsed
                            last_update_time = current_time
                            bytes_since_last_update = 0
                        
                        progress.bytes_downloaded = downloaded
                        
                        if total_size > 0:
                            progress.percent = (downloaded / total_size) * 100
                        
                        if progress_callback:
                            progress_callback(progress)
                
                # Final speed calculation
                total_elapsed = time.time() - start_time
                if total_elapsed > 0:
                    progress.speed_bps = downloaded / total_elapsed
                    progress.elapsed_time = total_elapsed
                    
                    # Final ETA calculation
                    remaining_bytes = max(0, total_size - downloaded) if total_size > 0 else 0
                    if progress.speed_bps > 0 and total_size > 0:
                        progress.eta_seconds = remaining_bytes / progress.speed_bps
                    else:
                        progress.eta_seconds = 0
                
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
                
                logger.info(
                    "Download completed: %s (%.1f KB, %.2f MB/s, %s)",
                    dest_path.name, 
                    downloaded / 1024,
                    progress.speed_mbps,
                    progress.formatted_eta if total_size > 0 else "N/A"
                )
                return True, ""
                
        except HTTPError as exc:
            return False, f"HTTP error {exc.code}: {exc.reason}"
        except URLError as exc:
            return False, f"Network error: {exc.reason}"
        except Exception as exc:
            return False, f"Download failed: {str(exc)}"

    @staticmethod
    def _parse_version(version_str: str) -> Tuple[Tuple[int, ...], str, str]:
        import re

        version_str = version_str.lstrip("v").strip()
        pattern = r"^(\d+(?:\.\d+)*)([a-zA-Z]+)?(\d*)$"
        match = re.match(pattern, version_str)
        if not match:
            parts = re.findall(r"\d+", version_str)
            padded = tuple(int(p) for p in parts[:8]) + (0,) * max(0, 8 - len(parts))
            return padded, "", ""

        base_version, pre_type, pre_num = match.groups()
        base_parts = [int(p) for p in base_version.split(".")]
        numeric = tuple(base_parts[:8]) + (0,) * max(0, 8 - len(base_parts))

        pre_type = (pre_type or "").lower().strip()
        pre_num = (pre_num or "0").strip()
        type_map = {
            "a": "alpha",
            "alpha": "alpha",
            "b": "beta",
            "beta": "beta",
            "rc": "rc",
            "releasecandidate": "rc",
            "release": "rc",
            "dev": "dev",
            "development": "dev",
            "post": "post",
        }
        pre_type = type_map.get(pre_type, pre_type)
        return numeric, pre_type, pre_num

    def _is_newer_version(self, latest: str, current: str) -> bool:
        try:
            l_nums, l_pre, l_pn = self._parse_version(latest)
            c_nums, c_pre, c_pn = self._parse_version(current)

            if l_nums > c_nums:
                return True
            if l_nums < c_nums:
                return False

            priority = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3, "": 4, "post": 5}
            l_pri = priority.get(l_pre, 4)
            c_pri = priority.get(c_pre, 4)

            if l_pre == c_pre:
                try:
                    return int(l_pn or 0) > int(c_pn or 0)
                except ValueError:
                    return False
            return l_pri > c_pri
        except Exception:
            return str(latest).strip() != str(current).strip() and str(latest) > str(current)

    def _asset_keywords(self) -> list:
        """Substrings that identify the release asset for this OS, best first."""
        if not self.is_frozen:
            return [".zip"]
        if sys.platform == "win32":
            return ["windows", ".exe"]
        if sys.platform == "darwin":
            return ["macos", "mac", "darwin", ".app", ".dmg"]
        return ["linux"]

    def _resolve_download_url(self, release_info: Dict[str, Any]) -> Optional[str]:
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

    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
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

    def _create_backup(self) -> Optional[Path]:
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
        """Calculate file checksum for integrity verification."""
        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(self.CHUNK_SIZE), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def _find_source_root(self, extracted_dir: Path) -> Path:
        for candidate in sorted(extracted_dir.iterdir(), key=lambda p: p.name.lower()):
            if candidate.is_dir():
                return candidate
        return extracted_dir

    def _find_exe_in_bundle(self, source_folder: Path, preferred_name: Optional[str] = None) -> Optional[Path]:
        preferred_name = (preferred_name or "").lower()
        candidates = []
        for item in source_folder.rglob("*.exe"):
            candidates.append(item)
        if not candidates:
            return None
        if preferred_name:
            for item in candidates:
                if item.name.lower() == preferred_name:
                    return item
        return candidates[0]

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
        clean = str(new_version).strip().lstrip("vV").strip()
        try:
            version_file.write_text(clean + "\n", encoding="utf-8")
            logger.info("Version updated to %s", clean)
        except Exception as exc:
            logger.warning("Could not update version.txt: %s", exc)

    def _relaunch_after_update(self) -> None:
        """Swap the staged executable into place and start it detached.

        Windows lets you *rename* a running .exe, so we move the current one
        aside (deleted on next launch), drop the new one in, then launch it
        with ShellExecute (`os.startfile`) which is fully detached from this
        dying process. No helper script, no job-object surprises.
        """
        if not self.current_exe:
            return
        target = self.current_exe
        staged = self.app_dir / f"{target.name}.updated"
        if not staged.exists():
            return

        old = target.with_name(target.name + ".old")
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
        try:
            os.replace(target, old)      # rename the running exe out of the way
            os.replace(staged, target)   # new exe into place
        except OSError as exc:
            logger.error("Could not swap in the update: %s", exc)
            return

        import subprocess as sp
        devnull = sp.DEVNULL
        try:
            if sys.platform == "win32":
                flags = (getattr(sp, "DETACHED_PROCESS", 0x08)
                         | getattr(sp, "CREATE_NEW_PROCESS_GROUP", 0x200)
                         | getattr(sp, "CREATE_BREAKAWAY_FROM_JOB", 0x1000000))
                try:
                    sp.Popen([str(target), "--no-update"], creationflags=flags,
                             close_fds=True, cwd=str(self.app_dir),
                             stdin=devnull, stdout=devnull, stderr=devnull)
                except OSError:
                    # job may forbid breakaway — retry without that flag
                    sp.Popen([str(target), "--no-update"],
                             creationflags=getattr(sp, "DETACHED_PROCESS", 0x08),
                             close_fds=True, cwd=str(self.app_dir),
                             stdin=devnull, stdout=devnull, stderr=devnull)
            else:
                target.chmod(0o755)
                sp.Popen([str(target), "--no-update"], start_new_session=True,
                         cwd=str(self.app_dir),
                         stdin=devnull, stdout=devnull, stderr=devnull)
        except OSError as exc:
            logger.error("Update installed but relaunch failed (%s); "
                         "restart the app manually.", exc)

    def _install_frozen_update(self, source_folder: Path, latest_version: str) -> bool:
        if not self.current_exe:
            return False

        exe_name = self.current_exe.name
        bundled_exe = self._find_exe_in_bundle(source_folder, exe_name)
        if bundled_exe:
            staged_exe = self.app_dir / f"{exe_name}.updated"
            shutil.copy2(bundled_exe, staged_exe)
        else:
            staged_exe = None

        version_file_in_bundle = source_folder / "version.txt"
        if version_file_in_bundle.exists():
            shutil.copy2(version_file_in_bundle, self.app_dir / "version.txt")
        else:
            self._update_version_file(latest_version)

        if staged_exe and staged_exe.exists():
            self._relaunch_after_update()
            return True
        return False

    def _install_frozen_executable(self, downloaded_exe: Path, latest_version: str) -> bool:
        if not self.current_exe or not downloaded_exe.exists():
            return False

        staged_exe = self.app_dir / f"{self.current_exe.name}.updated"
        shutil.copy2(downloaded_exe, staged_exe)
        self._update_version_file(latest_version)
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
                raise UpdateError(f"Invalid ZIP archive: {exc}", recoverable=False)

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
            logger.info("Already up to date")
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


def _version_file_candidates() -> list:
    """Every place version.txt might live, most-authoritative first.

    For a frozen app the copy next to the .exe wins: the updater writes it
    there after a successful update, while the bundled copy is frozen at build
    time (trusting it would cause an endless update loop).
    """
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "version.txt")
    here = Path(__file__).resolve().parent.parent.parent  # src/ -> repo root / _MEIPASS
    candidates.append(here / "version.txt")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "version.txt")
    return candidates


def get_current_version() -> str:
    for version_file in _version_file_candidates():
        try:
            if version_file.is_file():
                text = version_file.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except Exception:
            pass

    try:
        from ._version import get_version
        v = get_version()
        if v and v != "unknown":
            return v
    except Exception:
        pass

    if not getattr(sys, "frozen", False):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    return "unknown"


def check_updates(repo_owner: str, repo_name: str, auto: bool = False) -> bool:
    current_version = get_current_version()
    logger.info("Current version: %s", current_version)
    updater = AutoUpdater(repo_owner, repo_name, current_version)
    return updater.run_update_check(auto=auto)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Task Manager - Проверка обновлений")
    print("=" * 50)
    check_updates("LgbtBsod", "task_manager", auto=False)
