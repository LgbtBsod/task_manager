"""
Task Manager - Auto Updater Module

Responsibilities:
- Query GitHub releases for a newer version.
- Download a ZIP update bundle.
- Apply the update to the project root or the frozen EXE directory.
- Relaunch the app after update installation.

This module keeps the update logic isolated from the GUI and startup flow.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

SKIP_PATTERNS = {"venv", ".git", "__pycache__", "tasks.json", "data"}
SKIP_EXTENSIONS = {".pyc", ".pyo"}


@dataclass(frozen=True)
class UpdateJob:
    has_update: bool
    latest_version: Optional[str]
    download_url: Optional[str]


class AutoUpdater:
    """Responsible only for checking and applying app updates."""

    TIMEOUT_API = 8
    TIMEOUT_DOWNLOAD = 60

    def __init__(self, repo_owner: str, repo_name: str, current_version: str = "unknown"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.is_frozen = bool(getattr(sys, "frozen", False))
        self.app_dir = (
            Path(sys.executable).resolve().parent
            if self.is_frozen
            else Path(__file__).resolve().parent.parent.parent
        )
        self.current_exe = Path(sys.executable).resolve() if self.is_frozen else None

    def _create_request(self, url: str) -> Request:
        req = Request(url)
        req.add_header("User-Agent", f"TaskManager/{self.current_version}")
        return req

    def _api_get(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            with urlopen(self._create_request(url), timeout=self.TIMEOUT_API) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("API request failed: %s", exc)
            return None

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

    def _resolve_download_url(self, release_info: Dict[str, Any]) -> Optional[str]:
        assets = release_info.get("assets") or []
        preferred_suffix = ".exe" if self.is_frozen else ".zip"
        for asset in assets:
            name = str(asset.get("name") or "").lower()
            if name.endswith(preferred_suffix):
                return asset.get("browser_download_url")
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
        try:
            version_file.write_text(str(new_version).strip(), encoding="utf-8")
            logger.info("Version updated to %s", new_version)
        except Exception as exc:
            logger.warning("Could not update version.txt: %s", exc)

    def _relaunch_after_update(self) -> None:
        if not self.current_exe:
            return

        exe_name = self.current_exe.name
        staged_exe = self.app_dir / f"{exe_name}.updated"
        target = self.current_exe

        if staged_exe.exists():
            try:
                if target.exists():
                    target.unlink()
                shutil.move(str(staged_exe), str(target))
            except Exception:
                pass

        launcher = self.app_dir / "update_restart.cmd"
        launcher.write_text(
            "@echo off\n"
            "setlocal\n"
            "ping -n 4 127.0.0.1 >nul\n"
            f"if exist \"{staged_exe}\" (\n"
            f"  copy /Y \"{staged_exe}\" \"{target}\" >nul\n"
            "  if errorlevel 1 exit /b 1\n"
            "  del /f /q \"{staged_exe}\"\n"
            ")\n"
            f"start \"\" \"{target}\"\n"
            f"del /f /q \"{launcher}\"\n",
            encoding="utf-8",
        )
        subprocess.Popen(["cmd.exe", "/c", str(launcher)], shell=False, creationflags=0)

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
        if not zip_url:
            return False

        temp_dir = None
        try:
            temp_base = Path(tempfile.gettempdir()) / "task_manager_update"
            temp_dir = temp_base / f"update_{latest_version.replace('.', '_')}_{os.getpid()}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            zip_path = temp_dir / "update.zip"
            logger.info("Downloading update from %s", zip_url)
            with urlopen(self._create_request(zip_url), timeout=self.TIMEOUT_DOWNLOAD) as resp, open(zip_path, "wb") as dest:
                shutil.copyfileobj(resp, dest)

            if self.is_frozen and zip_url.lower().split("?", 1)[0].endswith(".exe"):
                result = self._install_frozen_executable(zip_path, latest_version)
                if result:
                    logger.info("Executable update staged successfully: %s", latest_version)
                return result

            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extracted_dir)

            source_folder = self._find_source_root(extracted_dir)
            if self.is_frozen:
                result = self._install_frozen_update(source_folder, latest_version)
            else:
                result = self._copy_update_files(source_folder) > 0
                self._update_version_file(latest_version)

            if result:
                logger.info("Update installed successfully: %s", latest_version)
            return result
        except Exception as exc:
            logger.error("Update download/apply failed: %s", exc)
            return False
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def run_update_check(self, auto: bool = False) -> bool:
        logger.info("Checking for updates (current: %s)", self.current_version)
        has_update, latest_version, download_url = self.check_for_updates()

        if not has_update:
            logger.info("Already up to date")
            return False

        if auto and download_url:
            print(f"[Обновление] Новая версия: {latest_version}. Автообновление...")
            ok = self.download_update(download_url, latest_version)
            if ok:
                print("[Обновление] Обновление установлено и приложение будет перезапущено.")
            else:
                print("[Обновление] Не удалось установить обновление.")
            return ok

        print(f"[Обновление] Доступна новая версия: {latest_version}")
        print(f"[Обновление] Текущая версия: {self.current_version}")
        print("[Обновление] Для обновления перезапустите приложение заново.")
        return False


def get_current_version() -> str:
    version_file = Path(__file__).resolve().parent.parent.parent / "version.txt"
    if version_file.exists():
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    try:
        from ._version import get_version
        return get_version()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
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
