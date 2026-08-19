"""
Task Manager - Auto Updater Module
Checks for updates from GitHub and downloads new version without Git installed.
"""
import os
import sys
import json
import zipfile
import tempfile
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.request import urlopen, urlretrieve, Request
from urllib.error import URLError, HTTPError


class AutoUpdater:
    """Automatic updater for Task Manager application."""
    
    def __init__(self, repo_owner: str, repo_name: str, current_version: str = "unknown"):
        """
        Initialize the updater.
        
        Args:
            repo_owner: GitHub repository owner (e.g., "username")
            repo_name: GitHub repository name (e.g., "task_manager")
            current_version: Current version string (can be commit hash or tag)
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.app_dir = Path(__file__).parent.parent.parent  # Go to project root
        
    def _create_request(self, url: str) -> Request:
        """Create a request with User-Agent header to avoid GitHub API rate limiting."""
        req = Request(url)
        req.add_header('User-Agent', f'TaskManager/{self.current_version}')
        return req
    
    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        """
        Fetch latest release information from GitHub API.
        
        Returns:
            Dictionary with release info or None if failed
        """
        try:
            url = f"{self.api_url}/releases/latest"
            req = self._create_request(url)
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except (URLError, HTTPError, json.JSONDecodeError) as e:
            print(f"[Обновление] Не удалось получить информацию о релизе: {e}")
            return None
    
    def get_latest_commit(self) -> Optional[Dict[str, Any]]:
        """
        Fetch latest commit information from GitHub API.
        
        Returns:
            Dictionary with commit info or None if failed
        """
        try:
            url = f"{self.api_url}/commits/main"
            req = self._create_request(url)
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except (URLError, HTTPError, json.JSONDecodeError) as e:
            print(f"[Обновление] Не удалось получить информацию о коммите: {e}")
            return None
    
    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if updates are available.
        
        Returns:
            Tuple of (has_update, latest_version, download_url)
        """
        import re
        
        # Try to get latest release first
        release_info = self.get_latest_release()
        if release_info:
            latest_version = release_info.get('tag_name', 'unknown')
            zip_url = None
            for asset in release_info.get('assets', []):
                if asset.get('name', '').endswith('.zip'):
                    zip_url = asset.get('browser_download_url')
                    break
            
            # If no zip asset, use source zip
            if not zip_url:
                zip_url = release_info.get('zipball_url')
            
            if zip_url:
                # Compare versions properly using semantic versioning
                if self._is_newer_version(latest_version, self.current_version):
                    print(f"[Обновление] Найдена новая версия: {latest_version}")
                    return True, latest_version, zip_url
                else:
                    return False, latest_version, None
        
        # Fallback to checking commits
        commit_info = self.get_latest_commit()
        if commit_info:
            latest_sha = commit_info.get('sha', '')[:7]
            zip_url = f"{self.api_url}/zipball/main"
            
            # Only suggest commit-based update if current version is not a semantic version
            if self.current_version != "unknown" and latest_sha != self.current_version[:7]:
                # If current version looks like a semantic version (e.g., 1.1.0), don't update to commit
                if re.match(r'^v?\d+\.\d+', self.current_version):
                    return False, latest_version, None
                else:
                    return True, latest_sha, zip_url
        
        return False, None, None
    
    def _parse_version(self, version_str: str) -> Tuple[Tuple[int, ...], str, str]:
        """
        Parse version string into components for comparison.
        Handles formats like: 1.1.0, v1.1.0, 1.1.0a, 1.1.0b, 1.1.0rc, 1.1.0.0
        Returns: (numeric_tuple, prerelease_type, prerelease_number)
        """
        import re
        
        # Remove 'v' prefix if present
        version_str = version_str.lstrip('v').strip()
        
        # Pattern to match version with optional prerelease suffix
        # Examples: 1.1.0, 1.1.0a, 1.1.0alpha, 1.1.0b2, 1.1.0rc1, 1.1.0.0
        pattern = r'^(\d+(?:\.\d+)*)\.?(\d*)\s*([a-zA-Z]+)?\s*(\d*)$'
        match = re.match(pattern, version_str)
        
        if not match:
            # Fallback: just extract numbers
            parts = re.findall(r'\d+', version_str)
            numeric_tuple = tuple(int(p) for p in parts[:4]) + (0,) * (4 - len(parts))
            return numeric_tuple, '', ''
        
        base_version, patch, prerelease_type, prerelease_num = match.groups()
        
        # Build numeric tuple from base version and optional patch
        base_parts = [int(p) for p in base_version.split('.')]
        if patch:
            base_parts.append(int(patch))
        
        # Pad to 4 elements
        numeric_tuple = tuple(base_parts[:4]) + (0,) * (4 - len(base_parts))
        
        # Normalize prerelease type
        prerelease_type = (prerelease_type or '').lower().strip()
        prerelease_num = (prerelease_num or '0').strip()
        
        # Map common aliases
        type_map = {
            'a': 'alpha', 'alpha': 'alpha',
            'b': 'beta', 'beta': 'beta',
            'rc': 'rc', 'releasecandidate': 'rc', 'release': 'rc',
            'dev': 'dev', 'development': 'dev',
            'post': 'post',
        }
        prerelease_type = type_map.get(prerelease_type, prerelease_type)
        
        return numeric_tuple, prerelease_type, prerelease_num
    
    def _is_newer_version(self, latest: str, current: str) -> bool:
        """
        Check if latest version is newer than current version.
        Supports semantic versioning with prerelease suffixes (alpha, beta, rc).
        
        Version order: dev < alpha < beta < rc < (no suffix/stable) < post
        Within same prerelease type, higher number is newer.
        Same base version with no suffix is newer than any prerelease.
        
        Args:
            latest: Latest version from GitHub (e.g., "v1.1.0", "1.1.0b2")
            current: Current local version (e.g., "1.1.0a", "1.1.0")
            
        Returns:
            True if latest is newer, False otherwise
        """
        try:
            latest_nums, latest_pre_type, latest_pre_num = self._parse_version(latest)
            current_nums, current_pre_type, current_pre_num = self._parse_version(current)
            
            # First compare numeric parts
            if latest_nums > current_nums:
                return True
            if latest_nums < current_nums:
                return False
            
            # Numeric parts are equal, check prerelease status
            # Priority order: dev < alpha < beta < rc < '' (stable) < post
            priority = {'dev': 0, 'alpha': 1, 'a': 1, 'beta': 2, 'b': 2, 'rc': 3, '': 4, 'post': 5}
            
            latest_priority = priority.get(latest_pre_type, 4)  # Default to stable if unknown
            current_priority = priority.get(current_pre_type, 4)
            
            # If both have same prerelease type, compare prerelease numbers
            if latest_pre_type == current_pre_type:
                try:
                    latest_num = int(latest_pre_num) if latest_pre_num else 0
                    current_num = int(current_pre_num) if current_pre_num else 0
                    return latest_num > current_num
                except ValueError:
                    return False
            
            # Stable release (no suffix) is newer than any prerelease
            # post is newer than stable
            return latest_priority > current_priority
            
        except Exception as e:
            print(f"[Обновление] Ошибка сравнения версий: {e}")
            # If parsing fails, fall back to simple string comparison
            return latest != current and latest > current
    
    def download_and_extract(self, zip_url: str, latest_version: str) -> bool:
        """
        Download and extract the update to a temporary folder, then restart.
        
        Args:
            zip_url: URL to download the zip file from
            latest_version: Version string of the latest release
            
        Returns:
            True if successful, False otherwise
        """
        import subprocess
        
        try:
            print("[Обновление] Скачивание обновлений...")
            
            # Create temporary directory for extraction
            temp_base = Path(tempfile.gettempdir()) / "task_manager_update"
            temp_dir = temp_base / f"update_{latest_version.replace('.', '_')}_{os.getpid()}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[Обновление] Временная папка: {temp_dir}")
            
            # Download archive to temp folder
            zip_path = temp_dir / "update.zip"
            req = self._create_request(zip_url)
            with urlopen(req, timeout=30) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            print("[Обновление] Распаковка обновлений во временную папку...")
            
            # Extract to temporary directory
            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)
            
            # Find the extracted folder (GitHub adds a prefix like username-repo-hash/)
            extracted_folders = [f for f in extracted_dir.iterdir() if f.is_dir()]
            if not extracted_folders:
                print("[Обновление] Ошибка: не найдено распакованных файлов")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False
            
            source_folder = extracted_folders[0]
            print(f"[Обновление] Источник: {source_folder}")
            
            # Prepare restart script path
            app_dir = self.app_dir
            start_bat = app_dir / "start.bat"
            update_bat = app_dir / "update.bat"
            
            print("[Обновление] Подготовка перезапуска...")
            
            # Save update info for batch script
            update_info = {
                'source_folder': str(source_folder),
                'app_dir': str(app_dir),
                'version': latest_version,
                'temp_dir': str(temp_dir)
            }
            update_info_file = temp_dir / "update_info.json"
            with open(update_info_file, 'w', encoding='utf-8') as f:
                json.dump(update_info, f, ensure_ascii=False, indent=2)
            
            # Stop current application gracefully
            print("[Обновление] Остановка приложения...")
            
            # If running from start.bat, we'll let the batch script handle the copy
            if update_bat.exists():
                print("[Обновление] Запуск внешнего скрипта обновления...")
                
                # Close current GUI if exists
                try:
                    import tkinter as tk
                    root = tk.Tk()
                    root.withdraw()
                    root.destroy()
                except Exception:
                    pass
                
                # Start update.bat with parameters
                subprocess.Popen([
                    'cmd.exe', '/c',
                    str(update_bat),
                    zip_url,
                    latest_version
                ], cwd=str(app_dir))
                
                # Exit current process
                sys.exit(0)
            else:
                # Fallback: copy files directly then restart
                print("[Обновление] Копирование файлов из временной папки...")
                
                files_copied = 0
                errors = []
                for item in source_folder.rglob('*'):
                    if item.is_file():
                        # Skip hidden files and directories
                        if any(part.startswith('.') for part in item.relative_to(source_folder).parts):
                            continue
                        
                        relative_path = item.relative_to(source_folder)
                        dest_path = app_dir / relative_path
                        
                        # Skip currently running script files that might be locked
                        if dest_path.exists() and self._is_file_locked(dest_path):
                            errors.append(f"Пропущен заблокированный файл: {relative_path}")
                            continue
                        
                        # Create parent directories if needed
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file
                        try:
                            shutil.copy2(item, dest_path)
                            files_copied += 1
                        except PermissionError as e:
                            errors.append(f"Не удалось скопировать {relative_path}: {e}")
                
                if errors:
                    print("[Обновление] Предупреждения:")
                    for err in errors[:5]:
                        print(f"  - {err}")
                    if len(errors) > 5:
                        print(f"  ... и ещё {len(errors) - 5} ошибок")
                
                print(f"[Обновление] Обновлено файлов: {files_copied}")
                
                # Update version file after successful extraction
                self._update_version_file(latest_version)
                
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                
                print("[Обновление] Обновление успешно установлено!")
                
                # Restart application
                print("[Обновление] Перезапуск приложения...")
                if start_bat.exists():
                    subprocess.Popen(['cmd.exe', '/c', str(start_bat)], cwd=str(app_dir))
                else:
                    subprocess.Popen([sys.executable, 'main.py'], cwd=str(app_dir))
                
                sys.exit(0)
            
            return True
            
        except Exception as e:
            print(f"[Обновление] Ошибка при установке обновлений: {e}")
            # Cleanup on error
            if 'temp_dir' in locals() and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    
    def _is_file_locked(self, filepath: Path) -> bool:
        """Check if a file is locked by another process."""
        try:
            with open(filepath, 'r+b') as f:
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        except (IOError, OSError, ImportError):
            return True
    
    def _update_version_file(self, new_version: str) -> None:
        """Update the version.txt file with the new version."""
        # Update version.txt in project root
        version_file = self.app_dir / "version.txt"
        
        try:
            with open(version_file, 'w', encoding='utf-8') as f:
                f.write(new_version.strip())
            print(f"[Обновление] Версия обновлена: {new_version}")
        except Exception as e:
            print(f"[Обновление] Не удалось обновить файл версии: {e}")
    
    def prompt_update(self, latest_version: str) -> bool:
        """
        Prompt user to confirm update.
        
        Args:
            latest_version: Version string of the latest release
            
        Returns:
            True if user wants to update, False otherwise
        """
        print("\n" + "="*50)
        print(f"Доступна новая версия: {latest_version}")
        print(f"Текущая версия: {self.current_version}")
        print("="*50)
        
        try:
            response = input("Скачать и установить обновление? (y/n): ").strip().lower()
            return response in ('y', 'yes', 'д', 'да')
        except (EOFError, KeyboardInterrupt):
            print("\n[Обновление] Отменено пользователем")
            return False
    
    def run_update_check(self, auto: bool = False) -> bool:
        """
        Run the update check process.
        
        Args:
            auto: If True, skip user prompt and auto-update if available
            
        Returns:
            True if update was performed, False otherwise
        """
        print("[Обновление] Проверка доступности обновлений...")
        
        has_update, latest_version, download_url = self.check_for_updates()
        
        if not has_update:
            print("[Обновление] Установлена актуальная версия")
            return False
        
        if auto or self.prompt_update(latest_version):
            if download_url:
                return self.download_and_extract(download_url, latest_version)
            else:
                print("[Обновление] Не найдено ссылки для скачивания")
                return False
        
        return False


def get_current_version() -> str:
    """Get current version from version.txt file."""
    # Try to get from version.txt in project root
    version_file = Path(__file__).parent.parent.parent / 'version.txt'
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    
    # Fallback to _version.py module
    try:
        from ._version import get_version
        return get_version()
    except Exception:
        pass
    
    # Try to get from git if available (fallback)
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return "unknown"


def check_updates(repo_owner: str, repo_name: str, auto: bool = False) -> bool:
    """
    Convenience function to check and install updates.
    
    Args:
        repo_owner: GitHub repository owner
        repo_name: GitHub repository name
        auto: If True, skip user prompt
        
    Returns:
        True if update was performed
    """
    current_version = get_current_version()
    print(f"[Обновление] Текущая версия: {current_version}")
    updater = AutoUpdater(repo_owner, repo_name, current_version)
    return updater.run_update_check(auto=auto)


if __name__ == "__main__":
    # Production settings for Task Manager
    REPO_OWNER = "LgbtBsod"
    REPO_NAME = "task_manager"
    
    print("Task Manager - Автообновление")
    print("=" * 50)
    
    updated = check_updates(REPO_OWNER, REPO_NAME, auto=False)
    
    if updated:
        print("\n[Обновление] Приложение будет перезапущено для применения обновлений...")
        # Optionally restart the application here
        # os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        print("\nПроект актуален")
