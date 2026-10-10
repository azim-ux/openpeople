"""Native installer acceptance with mandatory macOS filesystem/network isolation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

from test_isolated import ROOT, VERSION, ARCHIVE, PREFIX, OUTPUT, run_check, workspace_fingerprints


def main():
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise SystemExit('This runner requires macOS sandbox-exec; no unprotected fallback.')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = workspace_fingerprints()
    with tempfile.TemporaryDirectory(prefix='openpeople-isolated-test-', dir='/private/tmp') as folder, tempfile.TemporaryDirectory(prefix='openpeople-protection-sentinel-', dir='/private/tmp') as protected:
        temporary = Path(folder); guard = Path(protected) / 'sentinel.txt'; guard.write_text('protected')
        with zipfile.ZipFile(ARCHIVE) as archive:
            assert archive.testzip() is None
            for name in archive.namelist(): assert name.startswith(PREFIX) and '..' not in Path(name).parts
            archive.extractall(temporary)
        source = temporary / PREFIX.rstrip('/')
        manifest = json.loads((source / 'SOURCE_MANIFEST.json').read_text())['files']
        for name, digest in manifest.items(): assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
        (source / 'release').mkdir(exist_ok=True)
        for archive in (ROOT / 'release').glob(f'openpeople-{VERSION}-*-installer.zip'): shutil.copy2(archive, source / 'release' / archive.name)
        profile = temporary / 'installer.sb'
        profile.write_text('\n'.join([
            '(version 1)', '(allow default)', '(deny file-write*)',
            '(allow file-write* (subpath ' + json.dumps(str(temporary)) + '))',
            '(allow file-write-data (literal "/dev/null"))',
            '(deny file-read-data (subpath ' + json.dumps(str(Path.home())) + '))',
            '(allow file-read-data (subpath ' + json.dumps(str(ROOT / '.venv')) + ') (subpath ' + json.dumps(sys.base_prefix) + '))',
            '(deny file-read-data (literal ' + json.dumps(str(guard)) + '))',
            '(deny network*)', '(allow network-bind (local ip "localhost:*"))',
            '(allow network-inbound (local ip "localhost:*"))', '(allow network-outbound (remote ip "localhost:*"))',
        ]) + '\n')
        env = os.environ.copy(); env.update(TMPDIR=str(temporary) + '/', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
        preflight = '''from pathlib import Path
import socket,sys,json
p=Path(sys.argv[1]);checks={}
for name,action in [('outside_write',lambda:p.write_text('blocked')),('protected_read',p.read_text)]:
 try:action();checks[name]=False
 except PermissionError:checks[name]=True
with socket.socket() as s:
 s.settimeout(1)
 try:s.connect(('203.0.113.1',443));checks['external_network']=False
 except PermissionError:checks['external_network']=True
assert all(checks.values()),checks
print(json.dumps(checks))
'''
        sandbox = json.loads(run_check(profile, temporary, source, 'installer-sandbox', [sys.executable, '-c', preflight, str(guard)], env, 15))
        run_check(profile, temporary, source, 'installer-regressions', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_installer.py', '-v'], env, 60)
        native = json.loads(run_check(profile, temporary, source, 'native-installer', [sys.executable, 'tests/probe_installer.py'], env, 150))
        assert guard.read_text() == 'protected'
    report = {'version': VERSION, 'source_sha256': hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), 'sandbox': sandbox, 'installer_regressions_passed': True, 'native_installer': native, 'live_workspace_unchanged': before == workspace_fingerprints(), 'temporary_folders_removed': not temporary.exists() and not guard.parent.exists(), 'hosted_ci_executed': False}
    assert report['live_workspace_unchanged'] and report['temporary_folders_removed']
    (OUTPUT / 'report-installer.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
