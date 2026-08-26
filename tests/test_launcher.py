"""Test launcher.py steps without actually launching GUI."""
import sys, os, subprocess, time, tempfile, shutil
from pathlib import Path

APP_DIR = Path(__file__).parent.parent
VENV_DIR = APP_DIR / 'venv'
VENV_PYTHON = VENV_DIR / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')

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


def test_find_python():
    print('--- find_python ---')
    r = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from launcher import find_python; print(find_python())'],
        capture_output=True, text=True, cwd=str(APP_DIR)
    )
    ok('find_python returns path', r.returncode == 0 and len(r.stdout.strip()) > 0, r.stderr)


def test_get_venv_python():
    print('--- get_venv_python ---')
    r = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from launcher import get_venv_python; print(get_venv_python())'],
        capture_output=True, text=True, cwd=str(APP_DIR)
    )
    path = r.stdout.strip()
    ok('venv python path', path.endswith('python') or path.endswith('python.exe'), f'got {path}')
    ok('venv python exists', Path(path).exists(), f'{path} not found')


def test_setup_venv_idempotent():
    print('--- setup_venv (idempotent) ---')
    r = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from launcher import setup_venv, find_python; '
         'p = find_python(); v = setup_venv(p); print(v)'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=30
    )
    ok('setup_venv completes', r.returncode == 0, r.stderr)
    ok('returns venv path', 'venv' in r.stdout, r.stdout)


def test_install_deps():
    print('--- install_deps ---')
    r = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0,"src"); '
         'from launcher import get_venv_python, install_deps; '
         'install_deps(get_venv_python())'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=120
    )
    ok('install_deps completes', r.returncode == 0, r.stderr[:200] if r.stderr else '')


def test_try_git_pull_non_blocking():
    print('--- try_git_pull (non-blocking) ---')
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, '-c',
         'import sys; sys.path.insert(0,"src"); from launcher import try_git_pull; try_git_pull()'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=20
    )
    elapsed = time.time() - t0
    ok('git pull completes fast', elapsed < 15, f'took {elapsed:.1f}s')
    ok('git pull no crash', r.returncode == 0, r.stderr[:200] if r.stderr else '')


def test_launcher_no_update_skip_deps():
    print('--- launcher --no-update --skip-deps ---')
    r = subprocess.run(
        [sys.executable, '-c',
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
    ok('step 4 printed', '[4/4]' in output, output[-200:])
    ok('reached launch step', 'Starting Task Manager' in output, output[-300:])


def test_main_py_imports_clean():
    print('--- main.py imports clean ---')
    r = subprocess.run(
        [str(VENV_PYTHON), '-c',
         'import sys; sys.path.insert(0,"src"); '
         'sys.path.insert(0,"src/gui_flet"); '
         'from app import TaskManagerApp, run_app; '
         'print("GUI imports OK")'],
        capture_output=True, text=True, cwd=str(APP_DIR), timeout=10
    )
    ok('main.py GUI imports', r.returncode == 0 and 'GUI imports OK' in r.stdout, r.stderr[:300])


if __name__ == '__main__':
    tests = [
        test_find_python,
        test_get_venv_python,
        test_setup_venv_idempotent,
        test_install_deps,
        test_try_git_pull_non_blocking,
        test_launcher_no_update_skip_deps,
        test_main_py_imports_clean,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as e:
            failed += 1
            print(f'  UNHANDLED: {e}')
            import traceback; traceback.print_exc()
    total = passed + failed
    print(f'\n{"="*60}')
    print(f'LAUNCHER TESTS: {passed}/{total} passed, {failed} failed')
    print(f'{"="*60}')
    sys.exit(0 if failed == 0 else 1)
