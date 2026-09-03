"""
Tests for download functionality in the updater module.
"""
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.updater import AutoUpdater, DownloadProgress, UpdateError

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


def test_download_progress_model():
    """Test DownloadProgress dataclass."""
    print('--- DownloadProgress model ---')
    
    progress = DownloadProgress()
    ok('default bytes_downloaded is 0', progress.bytes_downloaded == 0)
    ok('default total_bytes is 0', progress.total_bytes == 0)
    ok('default percent is 0.0', progress.percent == 0.0)
    ok('is_complete False when total is 0', not progress.is_complete)
    
    progress = DownloadProgress(bytes_downloaded=50, total_bytes=100)
    ok('bytes_downloaded set correctly', progress.bytes_downloaded == 50)
    ok('total_bytes set correctly', progress.total_bytes == 100)
    # Note: percent is not auto-calculated in constructor, only updated during download
    # is_complete checks bytes >= total, which is False for 50/100
    ok('is_complete property works', not progress.is_complete)
    
    progress2 = DownloadProgress(bytes_downloaded=100, total_bytes=100)
    ok('is_complete True when downloaded equals total', progress2.is_complete)
    
    progress = DownloadProgress(bytes_downloaded=50, total_bytes=200)
    ok('is_complete False when downloaded < total', not progress.is_complete)


def test_download_with_progress_mock():
    """Test _download_with_progress method with mocked network."""
    print('--- _download_with_progress mock ---')
    
    updater = AutoUpdater('owner', 'repo', '1.0.0')
    
    # Mock response object
    mock_response = Mock()
    mock_response.getheader.return_value = '1024'  # 1KB file
    mock_response.read.side_effect = [b'x' * 512, b'y' * 512, b'']  # Two chunks then EOF
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)
    
    progress_callback = Mock()
    
    with patch('utils.updater.urlopen', return_value=mock_response):
        success, error_msg = updater._download_with_progress(
            'http://test.com/update.zip',
            Path('/tmp/test_update.zip'),
            progress_callback
        )
    
    ok('download succeeds with valid mock', success)
    ok('error_msg empty on success', error_msg == '')
    ok('progress callback called', progress_callback.called)


def test_download_size_validation():
    """Test file size validation during download."""
    print('--- Download size validation ---')
    
    updater = AutoUpdater('owner', 'repo', '1.0.0')
    
    # Test too small file
    mock_response_small = Mock()
    mock_response_small.getheader.return_value = '100'  # Too small
    mock_response_small.read.return_value = b''
    mock_response_small.__enter__ = Mock(return_value=mock_response_small)
    mock_response_small.__exit__ = Mock(return_value=False)
    
    with patch('utils.updater.urlopen', return_value=mock_response_small):
        success, error_msg = updater._download_with_progress(
            'http://test.com/tiny.zip',
            Path('/tmp/tiny.zip')
        )
    
    ok('rejects too small file', not success)
    ok('error mentions size', 'small' in error_msg.lower())
    
    # Test too large file
    mock_response_large = Mock()
    mock_response_large.getheader.return_value = str(600 * 1024 * 1024)  # 600MB
    mock_response_large.read.return_value = b''
    mock_response_large.__enter__ = Mock(return_value=mock_response_large)
    mock_response_large.__exit__ = Mock(return_value=False)
    
    with patch('utils.updater.urlopen', return_value=mock_response_large):
        success, error_msg = updater._download_with_progress(
            'http://test.com/huge.zip',
            Path('/tmp/huge.zip')
        )
    
    ok('rejects too large file', not success)
    ok('error mentions large', 'large' in error_msg.lower())


def test_download_http_error():
    """Test handling of HTTP errors."""
    print('--- HTTP error handling ---')
    
    from urllib.error import HTTPError
    
    updater = AutoUpdater('owner', 'repo', '1.0.0')
    
    mock_error = HTTPError('http://test.com', 404, 'Not Found', {}, None)
    
    with patch('utils.updater.urlopen', side_effect=mock_error):
        success, error_msg = updater._download_with_progress(
            'http://test.com/missing.zip',
            Path('/tmp/missing.zip')
        )
    
    ok('handles 404 error', not success)
    ok('error mentions HTTP', '404' in error_msg or 'HTTP' in error_msg)


def test_download_network_error():
    """Test handling of network errors."""
    print('--- Network error handling ---')
    
    from urllib.error import URLError
    
    updater = AutoUpdater('owner', 'repo', '1.0.0')
    
    mock_error = URLError('Network unreachable')
    
    with patch('utils.updater.urlopen', side_effect=mock_error):
        success, error_msg = updater._download_with_progress(
            'http://test.com/unreachable.zip',
            Path('/tmp/unreachable.zip')
        )
    
    ok('handles network error', not success)
    ok('error mentions network', 'network' in error_msg.lower() or 'unreachable' in error_msg.lower())


def test_backup_creation():
    """Test backup creation before update."""
    print('--- Backup creation ---')
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        app_dir = Path(tmpdir)
        
        # Create some files to backup
        (app_dir / 'version.txt').write_text('1.0.0')
        (app_dir / 'tasks.json').write_text('{}')
        
        updater = AutoUpdater('owner', 'repo', '1.0.0')
        updater.app_dir = app_dir
        
        backup_path = updater._create_backup()
        
        ok('backup created', backup_path is not None)
        ok('backup directory exists', backup_path.exists())
        ok('version.txt backed up', (backup_path / 'version.txt').exists())
        ok('tasks.json backed up', (backup_path / 'tasks.json').exists())


def test_backup_restore():
    """Test restoration from backup."""
    print('--- Backup restoration ---')
    
    import tempfile
    import shutil
    with tempfile.TemporaryDirectory() as tmpdir:
        app_dir = Path(tmpdir)
        
        # Create initial files
        (app_dir / 'version.txt').write_text('1.0.0')
        original_content = '{"tasks": []}'
        (app_dir / 'tasks.json').write_text(original_content)
        
        updater = AutoUpdater('owner', 'repo', '1.0.0')
        updater.app_dir = app_dir
        
        # Create backup
        backup_path = updater._create_backup()
        
        # Modify files
        (app_dir / 'version.txt').write_text('2.0.0')
        (app_dir / 'tasks.json').write_text('{"tasks": ["modified"]}')
        
        # Restore
        result = updater._restore_from_backup()
        
        ok('restore succeeds', result)
        ok('version.txt restored', (app_dir / 'version.txt').read_text() == '1.0.0')
        ok('tasks.json restored', (app_dir / 'tasks.json').read_text() == original_content)


def test_checksum_calculation():
    """Test checksum calculation."""
    print('--- Checksum calculation ---')
    
    import tempfile
    updater = AutoUpdater('owner', 'repo', '1.0.0')
    
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'test content for checksum')
        temp_path = Path(f.name)
    
    try:
        checksum = updater._calculate_checksum(temp_path)
        
        ok('checksum is string', isinstance(checksum, str))
        ok('checksum has correct length (SHA256 hex)', len(checksum) == 64)
        ok('checksum is hexadecimal', all(c in '0123456789abcdef' for c in checksum))
        
        # Same content should produce same checksum
        checksum2 = updater._calculate_checksum(temp_path)
        ok('checksum is deterministic', checksum == checksum2)
    finally:
        temp_path.unlink()


def test_update_error_exception():
    """Test UpdateError exception class."""
    print('--- UpdateError exception ---')
    
    err = UpdateError('Test error message')
    ok('error message stored', str(err) == 'Test error message')
    ok('default recoverable is True', err.recoverable)
    
    err2 = UpdateError('Critical error', recoverable=False)
    ok('recoverable can be False', not err2.recoverable)


if __name__ == '__main__':
    tests = [
        test_download_progress_model,
        test_download_with_progress_mock,
        test_download_size_validation,
        test_download_http_error,
        test_download_network_error,
        test_backup_creation,
        test_backup_restore,
        test_checksum_calculation,
        test_update_error_exception,
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
    print(f'DOWNLOAD TESTS: {passed}/{total} passed, {failed} failed')
    print(f'{"="*60}')
    sys.exit(0 if failed == 0 else 1)
