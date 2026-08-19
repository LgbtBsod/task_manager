"""
Task Manager - Modern Kanban Board
Main Entry Point
"""
import sys
import os
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def restart_application():
    """Restart the application with the same arguments."""
    python = sys.executable
    script = __file__
    os.execv(python, [python, script] + sys.argv[1:])


if __name__ == "__main__":
    # Check for updates before starting the app
    # Replace with your actual GitHub repo details
    REPO_OWNER = "your-username"  # TODO: Замените на ваш username GitHub
    REPO_NAME = "task_manager"     # TODO: Замените на имя вашего репозитория
    
    updated = False
    try:
        from src.utils import check_updates
        print("=" * 50)
        print("Task Manager - Проверка обновлений")
        print("=" * 50)
        updated = check_updates(REPO_OWNER, REPO_NAME, auto=False)
        print()
    except Exception as e:
        print(f"[Обновление] Ошибка проверки обновлений: {e}")
        print()
    
    # Restart if update was performed to load new code
    if updated:
        print("[Обновление] Перезапуск приложения для применения обновлений...")
        restart_application()
    
    from src.gui.main_window import run_app
    run_app()
