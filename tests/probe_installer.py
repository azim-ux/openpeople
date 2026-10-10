"""Exercise the native offline installer in disposable storage with fictional data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'installers'))
from installer import host_target

VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']


def main():
    if sys.platform == 'darwin' and not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-'):
        raise SystemExit('Use scripts/test_isolated.py --installer-only; no unrestricted macOS fallback.')
    target = host_target()
    archive_path = ROOT / 'release' / f'openpeople-{VERSION}-{target}-installer.zip'
    checks = {}
    with tempfile.TemporaryDirectory(prefix='native-installer-', dir=os.environ.get('TMPDIR') or None) as folder:
        temporary = Path(folder)
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            for entry in archive.infolist():
                assert not Path(entry.filename).is_absolute() and '..' not in Path(entry.filename).parts
                assert stat.S_ISREG(entry.external_attr >> 16)
            archive.extractall(temporary)
            if os.name == 'posix':
                for entry in archive.infolist(): os.chmod(temporary / entry.filename, stat.S_IMODE(entry.external_attr >> 16))
        kit = temporary / f'OpenPeople-{VERSION}-{target}'
        runtime = kit / ('payload/runtime/python.exe' if os.name == 'nt' else 'payload/runtime/bin/python3')
        root = temporary / "Fictional user's computer/OpenPeople"
        sentinel = temporary / 'personal-sentinel.txt'; sentinel.write_text('fictional protected personal file')
        environment = os.environ.copy(); environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
        if os.name == 'nt': command = ['cmd.exe', '/d', '/c', str(kit / 'Install.cmd'), '--yes', '--root', str(root)]
        else: command = ['/bin/sh', str(kit / ('Install.command' if sys.platform == 'darwin' else 'install.sh')), '--yes', '--root', str(root)]
        installed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment, timeout=35)
        assert installed.returncode == 0, installed.stderr
        state = json.loads((root / 'installation.json').read_text())
        program = root / state['program']
        python = program / ('runtime/python.exe' if os.name == 'nt' else 'runtime/bin/python3')
        desktop = program / 'desktop.py'; dbpath = root / 'data/openpeople.db'
        checks['offline_install_with_bundled_python_and_dependencies'] = True
        init = r'''import base64,sys
from pathlib import Path
p=Path(sys.argv[1]);sys.path[:0]=[str(p/'app'),str(p/'vendor')]
from server import HRStore
from provisioning import initialize_administrator
from identity import totp
from backup import configure_backup,run_configured_backup
s=HRStore(Path(sys.argv[2]),product_profile='core-hr')
secret=base64.b32encode(b'01234567890123456789').decode()
initialize_administrator(s,'Fictional installed HR','admin@openpeople.invalid','Fictional installer password 123!',secret,totp(secret),'IN')
configure_backup(s.db_path,Path(sys.argv[3]),'Fictional installer recovery phrase 123!',60,30)
run_configured_backup(s.db_path)
print('fictional owner and encrypted backup ready')
'''
        initialized = subprocess.run([str(python), '-I', '-B', '-c', init, str(program), str(dbpath), str(temporary / 'backups')], capture_output=True, text=True, env=environment, timeout=20)
        assert initialized.returncode == 0, initialized.stderr
        checks['native_cryptography_sqlite_mfa_and_encrypted_backup'] = True
        with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        origin = 'http://127.0.0.1:' + str(port)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        processes = []
        log = (temporary / 'app.log').open('w')
        try:
            app = subprocess.Popen([str(python), '-I', '-B', str(desktop), '--db', str(dbpath), '--port', str(port), '--no-browser'], stdout=log, stderr=log, env=environment)
            processes.append(app)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                assert app.poll() is None, (temporary / 'app.log').read_text()
                try:
                    with opener.open(origin + '/api/session', timeout=1) as response: session = json.load(response)
                    break
                except OSError: time.sleep(.1)
            else: raise AssertionError('Installed app never became ready')
            assert session['product']['profile'] == 'core-hr' and not session['setup_required']
            checks['installed_native_core_hr_launcher'] = True
            blocked = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment, timeout=20)
            assert blocked.returncode != 0 and 'Stop the running' in blocked.stderr
            checks['running_workspace_blocks_installer'] = True
            body = json.dumps({'email': 'admin@openpeople.invalid', 'password': 'Fictional installer password 123!'}).encode()
            request = urllib.request.Request(origin + '/api/login', data=body, headers={'Content-Type': 'application/json', 'Origin': origin})
            try:
                opener.open(request, timeout=4)
                raise AssertionError('MFA was bypassed')
            except urllib.error.HTTPError as error: assert error.code == 401
            checks['installed_login_requires_mfa'] = True
            app.terminate(); app.wait(timeout=15)
        finally:
            for process in processes:
                if process.poll() is None: process.terminate(); process.wait(timeout=15)
            log.close()
        baseline = hashlib.sha256(dbpath.read_bytes()).hexdigest()
        reinstall = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment, timeout=35)
        assert reinstall.returncode == 0, reinstall.stderr
        assert hashlib.sha256(dbpath.read_bytes()).hexdigest() == baseline
        checks['reinstall_preserves_employee_workspace'] = True
        maintenance = subprocess.run([str(python), '-I', '-B', str(desktop), '--db', str(dbpath), '--tool', 'backup', 'status'], capture_output=True, text=True, env=environment, timeout=20)
        assert maintenance.returncode == 0, maintenance.stderr
        assert json.loads(maintenance.stdout)['configured']
        checks['bundled_private_database_maintenance'] = True
        uninstall = subprocess.run([str(runtime), '-I', '-B', str(kit / 'installer.py'), 'uninstall', '--yes', '--root', str(root)], capture_output=True, text=True, env=environment, timeout=35)
        assert uninstall.returncode == 0, uninstall.stderr
        assert hashlib.sha256(dbpath.read_bytes()).hexdigest() == baseline
        assert sentinel.read_text() == 'fictional protected personal file'
        checks['uninstall_keeps_data_and_unrelated_files'] = True
        if os.name == 'posix': assert dbpath.stat().st_mode & 0o077 == 0 and dbpath.parent.stat().st_mode & 0o077 == 0
        checks['private_workspace_permissions'] = True
    print(json.dumps({'passed': True, 'target': target, 'checks': checks, 'installer_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(), 'temporary_folders_removed': not temporary.exists(), 'native_execution_verified': True, 'physical_off_device_recovery_verified': False}, indent=2))


if __name__ == '__main__': main()
