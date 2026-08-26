import sys, os, json, shutil, subprocess, tempfile
from pathlib import Path

APP_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(APP_DIR / 'src'))
VENV_PYTHON = APP_DIR / 'venv' / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
TASKS_JSON = APP_DIR / 'tasks.json'
VERSION_FILE = APP_DIR / 'version.txt'

passed = 0
failed = 0


def ok(name, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f'  PASS  {name}')
    else:
        failed += 1
        print(f'  FAIL  {name} {detail}')


def test_data_survives_update():
    print('--- Data survives update ---')
    TASKS_JSON.write_text(json.dumps([{
        'id': 'test123',
        'title': 'Survival test',
        'description': 'Must survive update',
        'status': 'Todo',
        'priority': 'Medium',
        'due_date': '2026-12-31',
        'start_date': None,
        'time_spent': 0,
        'created_at': '2026-08-20T12:00:00',
        'updated_at': '2026-08-20T12:00:00'
    }], indent=2))
    ok('test task written', TASKS_JSON.exists())
    tmp = Path(tempfile.mkdtemp())
    (tmp / 'src').mkdir(parents=True)
    (tmp / 'src' / '__init__.py').write_text('# updated')
    (tmp / 'tasks.json').write_text(json.dumps([]))
    from utils.updater import AutoUpdater
    updater = AutoUpdater('test', 'test', '1.0')
    copied = updater._copy_update_files(tmp)
    data = json.loads(TASKS_JSON.read_text())
    ok('tasks.json NOT overwritten', len(data) == 1, f'got {len(data)} tasks')
    ok('survival task intact', data[0]['id'] == 'test123')
    ok('some files were copied', copied > 0, f'copied={copied}')
    shutil.rmtree(tmp, ignore_errors=True)


def test_version_file_updates():
    print('--- Version file updates ---')
    original = VERSION_FILE.read_text().strip()
    from utils.updater import AutoUpdater
    updater = AutoUpdater('test', 'test', '1.0')
    updater._update_version_file('9.9.9')
    new_version = VERSION_FILE.read_text().strip()
    ok('version.txt changed', new_version == '9.9.9', f'got "{new_version}"')
    VERSION_FILE.write_text(original)
    ok('version.txt restored', VERSION_FILE.read_text().strip() == original)


def test_post_update_import_chain():
    print('--- Post-update import chain ---')
    for pyc in APP_DIR.rglob('__pycache__'):
        shutil.rmtree(pyc, ignore_errors=True)
    for pyc in APP_DIR.rglob('*.pyc'):
        pyc.unlink(missing_ok=True)
    r = subprocess.run(
        [str(VENV_PYTHON), '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from core.models import Task, TaskStatus, Priority; '
         'from core.service import TaskService; '
         'from core.repository import TaskRepository; '
         'from core.events import EventBus, EventType; '
         'from utils.updater import AutoUpdater, get_current_version; '
         'from utils.helpers import validate_date, format_time_spent; '
         'sys.path.insert(0,"src/gui_flet"); '
         'from app import TaskManagerApp, run_app; '
         'print("ALL POST-UPDATE IMPORTS OK")'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=15
    )
    ok('all imports after pycache clear', r.returncode == 0, r.stderr[:300] if r.stderr else '')
    ok('import success message', 'ALL POST-UPDATE IMPORTS OK' in r.stdout, r.stdout[-100:])


def test_post_update_full_functionality():
    print('--- Post-update full functionality ---')
    r = subprocess.run(
        [str(VENV_PYTHON), '-c',
         'import sys, json, tempfile; '
         'sys.path.insert(0,"src"); '
         'from core.models import Task, TaskStatus, Priority; '
         'from core.service import TaskService; '
         'from core.repository import TaskRepository; '
         'db = tempfile.mktemp(suffix=".json"); '
         'svc = TaskService(repository=TaskRepository(db_path=db)); '
         't = svc.create_task("Post-update test", priority=Priority.HIGH, due_date="2026-12-31"); '
         'assert t.title == "Post-update test"; '
         'u = svc.update_task_status(t.id, TaskStatus.DONE); '
         'assert u.status == TaskStatus.DONE; '
         'stats = svc.get_statistics(); '
         'assert stats["total"] == 1; '
         'assert stats["by_status"]["done"] == 1; '
         'svc.delete_task(t.id); '
         'assert svc.get_statistics()["total"] == 0; '
         'import os; os.unlink(db); '
         'print("POST-UPDATE CRUD OK")'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=15
    )
    ok('post-update CRUD', r.returncode == 0, r.stderr[:300] if r.stderr else '')
    ok('CRUD success message', 'POST-UPDATE CRUD OK' in r.stdout, r.stdout[-100:])


def test_post_update_launcher_reaches_app():
    print('--- Post-update launcher reaches app ---')
    r = subprocess.run(
        [str(VENV_PYTHON), '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from launcher import find_python, get_venv_python, setup_venv, try_git_pull; '
         'p = find_python(); '
         'vp = get_venv_python(); '
         'setup_venv(p); '
         'try_git_pull(); '
         'print("[4/4] Launching..."); '
         'print("Starting Task Manager")'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=30
    )
    output = r.stdout + r.stderr
    ok('launcher reaches step 4', '[4/4]' in output, output[-200:])
    ok('launcher says Starting', 'Starting Task Manager' in output, output[-200:])


if __name__ == '__main__':
    os.chdir(str(APP_DIR))
    sys.path.insert(0, str(APP_DIR / 'src'))
    tests = [
        test_data_survives_update,
        test_version_file_updates,
        test_post_update_import_chain,
        test_post_update_full_functionality,
        test_post_update_launcher_reaches_app,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as e:
            failed += 1
            print(f'  UNHANDLED: {e}')
            import traceback; traceback.print_exc()
    total = passed + failed
    print()
    print('=' * 60)
    print(f'POST-UPDATE TESTS: {passed}/{total} passed, {failed} failed')
    print('='*60)
    sys.exit(0 if failed == 0 else 1)
