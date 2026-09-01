"""Модуль обновления и сборки приложения."""
import os
import sys
import subprocess
import time
import hashlib
import json
from pathlib import Path
from typing import Optional, Tuple

class AppUpdater:
    """Класс для управления обновлениями приложения."""
    
    def __init__(self, repo_url: str = "https://github.com/user/repo.git"):
        self.repo_url = repo_url
        self.app_dir = Path(sys.argv[0]).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
        self.version_file = self.app_dir / "version.json"
        self.temp_dir = self.app_dir / "temp_update"
        self.log_file = self.app_dir / "update.log"
        
    def log(self, message: str):
        """Логирование сообщений."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        print(log_entry.strip())
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")
    
    def get_current_version(self) -> str:
        """Получение текущей версии приложения."""
        try:
            if self.version_file.exists():
                with open(self.version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version", "0.0.0")
        except Exception as e:
            self.log(f"Error reading version file: {e}")
        return "0.0.0"
    
    def save_version(self, version: str):
        """Сохранение версии приложения."""
        try:
            with open(self.version_file, "w", encoding="utf-8") as f:
                json.dump({"version": version, "updated": time.time()}, f)
        except Exception as e:
            self.log(f"Error saving version file: {e}")
    
    def check_for_updates(self) -> Tuple[bool, str]:
        """
        Проверка наличия обновлений.
        Returns: (есть_обновление, новая_версия)
        """
        try:
            # В реальной реализации здесь был бы запрос к API GitHub/GitLab
            # Для демонстрации возвращаем False
            current = self.get_current_version()
            self.log(f"Current version: {current}")
            return False, current
        except Exception as e:
            self.log(f"Error checking updates: {e}")
            return False, self.get_current_version()
    
    def download_update(self, version: str) -> bool:
        """Загрузка обновления."""
        try:
            self.log(f"Downloading update to version {version}...")
            
            # Создание временной директории
            if self.temp_dir.exists():
                self._cleanup_temp()
            self.temp_dir.mkdir(exist_ok=True)
            
            # В реальной реализации здесь была бы загрузка файлов
            # git clone или download zip
            
            self.log("Update downloaded successfully")
            return True
        except PermissionError as e:
            self.log(f"Permission error during download: {e}")
            return False
        except Exception as e:
            self.log(f"Error downloading update: {e}")
            return False
    
    def apply_update(self) -> bool:
        """Применение обновления."""
        try:
            if not self.temp_dir.exists():
                self.log("No update files found")
                return False
            
            self.log("Applying update...")
            
            # Копирование файлов из temp в основную директорию
            # Исключаем сам исполняемый файл если он запущен
            
            for item in self.temp_dir.iterdir():
                dest = self.app_dir / item.name
                
                # Пропускаем исполняемый файл приложения
                if item.name == Path(sys.executable).name:
                    continue
                
                try:
                    if item.is_dir():
                        if dest.exists():
                            self._merge_dirs(item, dest)
                        else:
                            self._copy_dir(item, dest)
                    else:
                        # Попытка заменить файл с обработкой ошибок
                        self._safe_copy_file(item, dest)
                except PermissionError as e:
                    self.log(f"Permission error copying {item.name}: {e}")
                    # Файл будет обновлен при следующем запуске
                except Exception as e:
                    self.log(f"Error copying {item.name}: {e}")
            
            self.log("Update applied successfully")
            self._cleanup_temp()
            return True
            
        except Exception as e:
            self.log(f"Error applying update: {e}")
            return False
    
    def _safe_copy_file(self, src: Path, dest: Path):
        """Безопасное копирование файла с обработкой ошибок."""
        try:
            if dest.exists():
                # Создаем резервную копию
                backup = dest.with_suffix(dest.suffix + ".bak")
                try:
                    dest.rename(backup)
                except:
                    pass
            
            # Копируем новый файл
            import shutil
            shutil.copy2(src, dest)
            
            # Удаляем резервную копию если всё успешно
            if backup.exists():
                try:
                    backup.unlink()
                except:
                    pass
                    
        except PermissionError:
            # Если не можем перезаписать, пробуем переименовать старый
            if dest.exists():
                old_name = dest.with_name(f"{dest.name}.old")
                try:
                    dest.rename(old_name)
                    import shutil
                    shutil.copy2(src, dest)
                except Exception as e:
                    self.log(f"Could not replace {dest.name}: {e}")
                    raise
        except Exception as e:
            self.log(f"Error copying file {src}: {e}")
            raise
    
    def _copy_dir(self, src: Path, dest: Path):
        """Копирование директории."""
        import shutil
        try:
            shutil.copytree(src, dest)
        except FileExistsError:
            self._merge_dirs(src, dest)
    
    def _merge_dirs(self, src: Path, dest: Path):
        """Слияние директорий."""
        for item in src.iterdir():
            dest_item = dest / item.name
            if item.is_dir():
                if dest_item.exists():
                    self._merge_dirs(item, dest_item)
                else:
                    item.rename(dest_item)
            else:
                self._safe_copy_file(item, dest_item)
    
    def _cleanup_temp(self):
        """Очистка временной директории."""
        try:
            if self.temp_dir.exists():
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            self.log(f"Error cleaning temp directory: {e}")
    
    def restart_app(self):
        """Перезапуск приложения после обновления."""
        try:
            self.log("Restarting application...")
            
            if getattr(sys, 'frozen', False):
                # Запуск EXE
                exe_path = sys.executable
                subprocess.Popen([exe_path] + sys.argv[1:])
            else:
                # Запуск через Python
                script_path = __file__
                subprocess.Popen([sys.executable, script_path] + sys.argv[1:])
            
            sys.exit(0)
        except Exception as e:
            self.log(f"Error restarting app: {e}")
            raise


class AppBuilder:
    """Класс для сборки приложения в EXE."""
    
    def __init__(self):
        self.app_dir = Path(__file__).parent.parent
        self.main_script = self.app_dir / "main.py"
        self.output_dir = self.app_dir / "dist"
        
    def build_exe(self, one_file: bool = True) -> bool:
        """
        Сборка приложения в EXE.
        
        Args:
            one_file: Если True, создается один EXE файл, иначе папка с файлами
            
        Returns:
            True если сборка успешна
        """
        try:
            print("Starting EXE build process...")
            
            # Проверка наличия PyInstaller
            try:
                import PyInstaller
            except ImportError:
                print("Installing PyInstaller...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            
            # Формирование команды
            cmd = [
                sys.executable, "-m", "PyInstaller",
                "--name", "TaskManager",
                "--windowed",  # Без консоли
                "--onefile" if one_file else "--onedir",
                "--add-data", f"{self.app_dir / 'assets'}{os.pathsep}assets" if (self.app_dir / "assets").exists() else "",
                "--hidden-import", "flet",
                "--hidden-import", "flet_core",
                "--hidden-import", "flet_runtime",
                "--hidden-import", "requests",
                "--hidden-import", "urllib3",
                "--clean",
                str(self.main_script)
            ]
            
            # Удаление пустых аргументов
            cmd = [arg for arg in cmd if arg]
            
            print(f"Running: {' '.join(cmd)}")
            
            # Запуск сборки
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("Build completed successfully!")
                
                # Копирование дополнительных файлов
                self._copy_additional_files()
                
                return True
            else:
                print(f"Build failed:\n{result.stderr}")
                return False
                
        except Exception as e:
            print(f"Build error: {e}")
            return False
    
    def _copy_additional_files(self):
        """Копирование дополнительных файлов в dist."""
        try:
            dist_dir = self.output_dir
            
            # Копирование BAT файлов если они есть
            for bat_file in ["build.bat", "start_flet.bat", "run.bat"]:
                src = self.app_dir / bat_file
                if src.exists():
                    import shutil
                    shutil.copy2(src, dist_dir / bat_file)
            
            # Копирование requirements.txt
            req_file = self.app_dir / "requirements.txt"
            if req_file.exists():
                import shutil
                shutil.copy2(req_file, dist_dir / "requirements.txt")
            
            print("Additional files copied successfully")
        except Exception as e:
            print(f"Warning: Could not copy additional files: {e}")


def run_tests():
    """Запуск тестов приложения."""
    try:
        print("Running tests...")
        test_script = Path(__file__).parent.parent / "tests.py"
        
        if not test_script.exists():
            print("Tests file not found")
            return False
        
        result = subprocess.run([sys.executable, str(test_script)], capture_output=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Test error: {e}")
        return False


if __name__ == "__main__":
    # Демонстрация использования
    print("App Updater & Builder Module")
    print("=" * 40)
    
    # Проверка обновлений
    updater = AppUpdater()
    has_update, version = updater.check_for_updates()
    print(f"Current version: {version}")
    print(f"Update available: {has_update}")
    
    # Сборка (если передан аргумент)
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        builder = AppBuilder()
        builder.build_exe()
