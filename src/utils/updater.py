"""
Task Manager - Auto Updater Module
Checks for updates from GitHub.  Non-blocking by default.

Key design decisions:
- check_updates() never calls sys.exit or input()
- All network calls have short timeouts
- Downloading an update is a separate explicit step, never automatic
- Works cross-platform (no .bat dependency)
"""
import os
import sys
import json
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import subprocess
import logging

logger = logging.getLogger(__name__)

# Files to skip when copying update files
SKIP_PATTERNS = {"venv", ".git", "__pycache__", "tasks.json"}
SKIP_EXTENSIONS = {".pyc", ".pyo"}


class AutoUpdater:
    """Automatic updater for Task Manager application."""

    TIMEOUT_API = 8       # seconds for GitHub API calls
    TIMEOUT_DOWNLOAD = 60  # seconds for zip download

    def __init__(self, repo_owner: str, repo_name: str, current_version: str = "unknown"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.app_dir = Path(__file__).parent.parent.parent  # project root

    # ── Network helpers ───────────────────────────────────────────────────

    def _create_request(self, url: str) -> Request:
        req = Request(url)
        req.add_header('User-Agent', f'TaskManager/{self.current_version}')
        return req

    def _api_get(self, url: str) -> Optional[Dict[str, Any]]:
        """GET JSON from GitHub API with timeout.  Returns None on any error."""
        try:
            req = self._create_request(url)
            with urlopen(req, timeout=self.TIMEOUT_API) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.debug("API request failed: %s", e)
            return None

    # ── Version parsing ───────────────────────────────────────────────────

    @staticmethod
    def _parse_version(version_str: str) -> Tuple[Tuple[int, ...], str, str]:
        """
        Parse version string.  Handles: 1.1.0, v1.1.0, 1.1.0a, 1.1.0b2, 1.1.0rc1
        Returns: (numeric_tuple, prerelease_type, prerelease_number)
        """
        import re
        version_str = version_str.lstrip('v').strip()
        # Primary pattern: match dotted numbers, optional prerelease suffix
        pattern = r'^(\d+(?:\.\d+)*)([a-zA-Z]+)?(\d*)$'
        match = re.match(pattern, version_str)

        if not match:
            parts = re.findall(r'\d+', version_str)
            padded = tuple(int(p) for p in parts[:8]) + (0,) * max(0, 8 - len(parts))
            return padded, '', ''

        base_version, pre_type, pre_num = match.groups()
        base_parts = [int(p) for p in base_version.split('.')]
        numeric_tuple = tuple(base_parts[:8]) + (0,) * max(0, 8 - len(base_parts))

        pre_type = (pre_type or '').lower().strip()
        pre_num = (pre_num or '0').strip()
        type_map = {
            'a': 'alpha', 'alpha': 'alpha',
            'b': 'beta', 'beta': 'beta',
            'rc': 'rc', 'releasecandidate': 'rc', 'release': 'rc',
            'dev': 'dev', 'development': 'dev',
            'post': 'post',
        }
        pre_type = type_map.get(pre_type, pre_type)
        return numeric_tuple, pre_type, pre_num

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Check if *latest* is strictly newer than *current*."""
        try:
            l_nums, l_pre, l_pn = self._parse_version(latest)
            c_nums, c_pre, c_pn = self._parse_version(current)

            if l_nums > c_nums:
                return True
            if l_nums < c_nums:
                return False

            priority = {'dev': 0, 'alpha': 1, 'a': 1, 'beta': 2, 'b': 2,
                        'rc': 3, '': 4, 'post': 5}
            l_pri = priority.get(l_pre, 4)
            c_pri = priority.get(c_pre, 4)

            if l_pre == c_pre:
                try:
                    return int(l_pn or 0) > int(c_pn or 0)
                except ValueError:
                    return False
            return l_pri > c_pri
        except Exception:
            return latest != current and latest > current

    # ── Check for updates (read-only, never blocks) ────────────────────────

    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Non-blocking check.  Returns (has_update, latest_version, download_url).
        Never raises, never calls input/sys.exit.
        """
        import re

        release_info = self._api_get(f"{self.api_url}/releases/latest")
        if release_info:
            latest_version = release_info.get('tag_name', 'unknown')
            zip_url = None
            for asset in release_info.get('assets', []):
                if (asset.get('name', '') or '').endswith('.zip'):
                    zip_url = asset.get('browser_download_url')
                    break
            if not zip_url:
                zip_url = release_info.get('zipball_url')

            if zip_url and self._is_newer_version(latest_version, self.current_version):
                logger.info("New version available: %s", latest_version)
                return True, latest_version, zip_url
            return False, latest_version, None

        # Fallback: check latest commit
        commit_info = self._api_get(f"{self.api_url}/commits/main")
        if commit_info:
            latest_sha = commit_info.get('sha', '')[:7]
            zip_url = f"{self.api_url}/zipball/main"
            if (self.current_version != "unknown"
                    and latest_sha != self.current_version[:7]
                    and not re.match(r'^v?\d+\.\d+', self.current_version)):
                return True, latest_sha, zip_url

        return False, None, None

    # ── Download & apply update ───────────────────────────────────────────

    def download_update(self, zip_url: str, latest_version: str) -> bool:
        """
        Download zip to a temp dir and apply file-by-file.
        Cross-platform — no .bat dependency.
        Returns True on success, False on failure (never raises to caller).
        """
        temp_dir = None
        try:
            temp_base = Path(tempfile.gettempdir()) / "task_manager_update"
            temp_dir = temp_base / f"update_{latest_version.replace('.', '_')}_{os.getpid()}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            zip_path = temp_dir / "update.zip"
            logger.info("Downloading update from %s", zip_url)

            req = self._create_request(zip_url)
            with urlopen(req, timeout=self.TIMEOUT_DOWNLOAD) as resp, open(zip_path, 'wb') as f:
                shutil.copyfileobj(resp, f)

            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extracted_dir)

            # GitHub zips have a single root folder like owner-repo-hash/
            folders = [p for p in extracted_dir.iterdir() if p.is_dir()]
            if not folders:
                logger.error("No extracted folder found")
                return False
            source_folder = folders[0]

            # Copy files
            files_copied = self._copy_update_files(source_folder)
            logger.info("Updated %d files", files_copied)

            # Update version file
            self._update_version_file(latest_version)

            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True

        except Exception as e:
            logger.error("Update download/apply failed: %s", e)
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    def _copy_update_files(self, source_folder: Path) -> int:
        """Copy files from extracted update, skipping venv/.git/__pycache__/tasks.json."""
        app_dir = self.app_dir
        files_copied = 0

        for item in source_folder.rglob('*'):
            if not item.is_file():
                continue
            rel = item.relative_to(source_folder)
            parts = rel.parts

            # Skip hidden dirs/files, venv, __pycache__, etc.
            if any(p.startswith('.') for p in parts):
                continue
            if any(p in SKIP_PATTERNS for p in parts):
                continue
            if item.suffix in SKIP_EXTENSIONS:
                continue

            dest = app_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, dest)
                files_copied += 1
            except PermissionError:
                logger.warning("Skipping locked file: %s", rel)

        return files_copied

    def _update_version_file(self, new_version: str) -> None:
        version_file = self.app_dir / "version.txt"
        try:
            version_file.write_text(new_version.strip(), encoding='utf-8')
            logger.info("Version updated to %s", new_version)
        except Exception as e:
            logger.warning("Could not update version.txt: %s", e)

    # ── Public entry point ─────────────────────────────────────────────────

    def run_update_check(self, auto: bool = False) -> bool:
        """
        Check and optionally apply updates.

        Args:
            auto: if True, download+apply without prompting (for CI/background).
                  if False, just print a notice (never calls input()).

        Returns:
            True if an update was applied, False otherwise.
        """
        logger.info("Checking for updates (current: %s)", self.current_version)
        has_update, latest_version, download_url = self.check_for_updates()

        if not has_update:
            logger.info("Already up to date")
            return False

        if auto and download_url:
            print(f"[Обновление] Новая версия: {latest_version}. Автообновление...")
            ok = self.download_update(download_url, latest_version)
            if ok:
                print("[Обновление] Обновление установлено. Перезапустите приложение.")
            else:
                print("[Обновление] Не удалось установить обновление.")
            return ok

        # Non-auto: just inform, do NOT block with input()
        print(f"[Обновление] Доступна новая версия: {latest_version}")
        print(f"[Обновление] Текущая версия: {self.current_version}")
        print("[Обновление] Для обновления перезапустите с флагом --update")
        return False


def get_current_version() -> str:
    """Get current version from version.txt, _version.py, or git."""
    version_file = Path(__file__).parent.parent.parent / 'version.txt'
    if version_file.exists():
        try:
            return version_file.read_text(encoding='utf-8').strip()
        except Exception:
            pass

    try:
        from ._version import get_version
        return get_version()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "unknown"


def check_updates(repo_owner: str, repo_name: str, auto: bool = False) -> bool:
    """
    Convenience function — non-blocking, never calls input() or sys.exit.
    """
    current_version = get_current_version()
    logger.info("Current version: %s", current_version)
    updater = AutoUpdater(repo_owner, repo_name, current_version)
    return updater.run_update_check(auto=auto)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    REPO_OWNER = "LgbtBsod"
    REPO_NAME = "task_manager"
    print("Task Manager - Проверка обновлений")
    print("=" * 50)
    check_updates(REPO_OWNER, REPO_NAME, auto=False)
