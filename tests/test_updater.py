import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.updater import AutoUpdater, get_current_version, check_updates

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


def test_version_parsing():
    print('--- Version parsing ---')
    u = AutoUpdater('owner', 'repo', '1.0.0')
    ok('1.1 > 1.0', u._is_newer_version('1.1', '1.0'))
    ok('2.0 > 1.9', u._is_newer_version('2.0', '1.9'))
    ok('1.1.1 > 1.1.0', u._is_newer_version('1.1.1', '1.1.0'))
    ok('NOT 1.0 > 1.1', not u._is_newer_version('1.0', '1.1'))
    ok('NOT 1.0 > 1.0', not u._is_newer_version('1.0', '1.0'))
    ok('v2.0 > v1.0 (v prefix)', u._is_newer_version('v2.0', 'v1.0'))
    ok('1.1.0b > 1.1.0a (beta>alpha)', u._is_newer_version('1.1.0b', '1.1.0a'))
    ok('1.1.0 > 1.1.0b (stable>beta)', u._is_newer_version('1.1.0', '1.1.0b'))
    ok('1.1.0rc1 > 1.1.0b2 (rc>beta)', u._is_newer_version('1.1.0rc1', '1.1.0b2'))
    ok('1.1.0b2 > 1.1.0b1 (beta2>beta1)', u._is_newer_version('1.1.0b2', '1.1.0b1'))
    ok('0.0.0.0.1 parsing', u._parse_version('0.0.0.0.1')[0][:5] == (0, 0, 0, 0, 1), str(u._parse_version('0.0.0.0.1')))


def test_get_current_version():
    print('--- get_current_version ---')
    v = get_current_version()
    ok('version is string', isinstance(v, str))
    ok('version not empty', len(v) > 0)
    ok('version matches file', v == '0.0.0.0.1', f'got "{v}"')


def test_check_updates_non_blocking():
    print('--- check_updates non-blocking ---')
    import time
    t0 = time.time()
    result = check_updates('LgbtBsod', 'task_manager', auto=False)
    elapsed = time.time() - t0
    ok('completes in <15s', elapsed < 15, f'took {elapsed:.1f}s')
    ok('returns bool', isinstance(result, bool))
    ok('no crash', True)


def test_check_updates_fake_repo():
    print('--- check_updates fake repo ---')
    import time
    t0 = time.time()
    result = check_updates('nonexistent_fake_repo_xyz', 'nope_task_manager_xyz', auto=False)
    elapsed = time.time() - t0
    ok('fake repo completes in <15s', elapsed < 15, f'took {elapsed:.1f}s')
    ok('fake repo returns False', result is False)


def test_updater_attributes():
    print('--- Updater init ---')
    u = AutoUpdater('TestOwner', 'TestRepo', '1.0.0')
    ok('api_url correct', u.api_url == 'https://api.github.com/repos/TestOwner/TestRepo')
    ok('TIMEOUT_API set', u.TIMEOUT_API == 8)
    ok('TIMEOUT_DOWNLOAD set', u.TIMEOUT_DOWNLOAD == 60)


def test_check_for_updates_returns_tuple():
    print('--- check_for_updates return type ---')
    u = AutoUpdater('nonexistent_xyz_123', 'fake_xyz_456', '0.0.1')
    result = u.check_for_updates()
    ok('returns 3-tuple', isinstance(result, tuple) and len(result) == 3)
    has_update, version, url = result
    ok('has_update is bool', isinstance(has_update, bool))
    ok('url is None for fake repo', url is None)


def test_download_update_nonexistent_url():
    print('--- download_update bad URL ---')
    u = AutoUpdater('owner', 'repo', '1.0.0')
    result = u.download_update('https://example.com/nonexistent_file_404.zip', '9.9.9')
    ok('bad URL returns False', result is False)


def test_run_update_check_auto():
    print('--- run_update_check auto mode ---')
    u = AutoUpdater('nonexistent_xyz_123', 'fake_xyz_456', '0.0.1')
    result = u.run_update_check(auto=True)
    ok('auto update returns bool', isinstance(result, bool))


if __name__ == '__main__':
    tests = [
        test_version_parsing,
        test_get_current_version,
        test_check_updates_non_blocking,
        test_check_updates_fake_repo,
        test_updater_attributes,
        test_check_for_updates_returns_tuple,
        test_download_update_nonexistent_url,
        test_run_update_check_auto,
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
    print(f'UPDATER TESTS: {passed}/{total} passed, {failed} failed')
    print(f'{"="*60}')
    sys.exit(0 if failed == 0 else 1)
