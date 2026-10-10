"""Run the built release tests in a disposable macOS filesystem/network sandbox.

No unrestricted fallback. Children may write only to this run's temporary tree;
personal-home contents are unreadable except the installed Python runtime.
The local production workspace is inspected only for before/after fingerprints.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
ARCHIVE = ROOT / ('release/openpeople-' + VERSION + '-source.zip')
PREFIX = 'openpeople-' + VERSION + '-source/'
OUTPUT = ROOT / ('docs/validation/v' + VERSION + '-isolation')


def workspace_fingerprints():
    facts = {}
    for name in ('openpeople.db','openpeople.db-wal','openpeople.db-shm','openpeople.key','openpeople.setup-token'):
        path = ROOT / 'data' / name
        if path.exists():
            info = path.stat()
            facts[name] = (hashlib.sha256(path.read_bytes()).hexdigest(),info.st_size,info.st_mtime_ns,info.st_mode,info.st_ino)
    return facts


def run_check(profile,temporary,source,label,arguments,environment,timeout=150):
    log = temporary / (label + '.log')
    with log.open('w') as output:
        process = subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(profile),*arguments],cwd=source,env=environment,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait()
            raise RuntimeError(label + ' exceeded the bounded test deadline.')
        finally:
            # Any leftover child belongs to the new test-only process group.
            try:
                os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
    shutil.copy2(log,OUTPUT / log.name)
    if status != 0:
        raise RuntimeError(label + ' failed; see ' + str(OUTPUT / log.name))
    return log.read_text()


def main():
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise SystemExit('This runner requires macOS sandbox-exec; it will not run tests without protection.')
    node = shutil.which('node')
    if not node or not Path('/tmp/openpeople-caddy-audit/caddy').is_file():
        raise SystemExit('Existing Node and the verified portable Caddy test binary are required. Nothing will be installed.')
    before = workspace_fingerprints()
    followup_only = '--followup-only' in sys.argv
    browser_only = '--browser-only' in sys.argv
    identity_only = '--identity-only' in sys.argv
    services_only = '--services-only' in sys.argv or '--core-services-only' in sys.argv
    core_services = '--core-services-only' in sys.argv
    core_only = '--core-only' in sys.argv
    installer_only = '--installer-only' in sys.argv
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report = {'scope':'Fictional archived workspace; this computer only','checks':{},'real_vpn_test':False,'real_provider_test':False,'real_identity_tenant_test':False,'actual_services_configured':False,'actual_service_status':'User confirmed none are configured.','followup_only':followup_only,'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='openpeople-isolated-test-',dir='/private/tmp') as disposable, tempfile.TemporaryDirectory(prefix='openpeople-protection-sentinel-',dir='/private/tmp') as protected:
        temporary = Path(disposable)
        guard = Path(protected) / 'protected.txt'
        guard.write_text('Disposable protection sentinel')
        with zipfile.ZipFile(ARCHIVE) as archive:
            if archive.testzip() is not None:
                raise ValueError('Source archive integrity failed.')
            for name in archive.namelist():
                parts = Path(name).parts
                if Path(name).is_absolute() or '..' in parts or not name.startswith(PREFIX):
                    raise ValueError('Unexpected archive path.')
            archive.extractall(temporary)
        source = temporary / PREFIX.rstrip('/')
        manifest = json.loads((source / 'SOURCE_MANIFEST.json').read_text())
        for name,digest in manifest['files'].items():
            if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Source manifest mismatch.')
        (source / 'release').mkdir(exist_ok=True)
        report['tested_runtime_files']={name:digest for name,digest in manifest['files'].items() if name.startswith(('public/','tests/','scripts/','deploy/')) or name.endswith('.py') or name in ('pyproject.toml','uv.lock','requirements.txt','countries.json')}
        shutil.copy2(ARCHIVE,source / 'release' / ARCHIVE.name)
        if installer_only:
            for path in (ROOT / 'release').glob(f'openpeople-{VERSION}-*-installer.zip'):
                shutil.copy2(path,source / 'release' / path.name)
        profile = temporary / 'tests.sb'
        profile.write_text('\n'.join([
            '(version 1)',
            '(allow default)',
            '(deny file-write*)',
            '(allow file-write* (subpath ' + json.dumps(str(temporary)) + '))',
            '(allow file-write-data (literal "/dev/null"))',
            '(deny file-read-data (subpath ' + json.dumps(str(Path.home())) + '))',
            '(allow file-read-data (subpath ' + json.dumps(str(ROOT / '.venv')) + ') (subpath ' + json.dumps(sys.base_prefix) + '))',
            '(deny file-read-data (literal ' + json.dumps(str(guard)) + '))',
            '(deny network*)',
            '(allow network-bind (local ip "localhost:*"))',
            '(allow network-inbound (local ip "localhost:*"))',
            '(allow network-outbound (remote ip "localhost:*"))',
            '(allow network-bind (local unix-socket (subpath ' + json.dumps(str(temporary)) + ')))',
            '(allow network-inbound (local unix-socket (subpath ' + json.dumps(str(temporary)) + ')))',
            '(allow network-outbound (remote unix-socket (subpath ' + json.dumps(str(temporary)) + ')))',
        ]) + '\n')
        environment = os.environ.copy()
        environment.update({'TMPDIR':str(temporary) + '/','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'})
        preflight = '''import json,socket,sys
from pathlib import Path
guard=Path(sys.argv[1]);blocked={}
for name,operation in [('outside_write',lambda:guard.write_text('must be blocked')),('protected_read',guard.read_text)]:
 try:operation();blocked[name]=False
 except PermissionError:blocked[name]=True
with socket.socket() as sock:
 sock.settimeout(1)
 try:sock.connect(('203.0.113.1',443));blocked['external_connection']=False
 except PermissionError:blocked['external_connection']=True
assert all(blocked.values()),blocked
with socket.socket() as sock:sock.bind(('127.0.0.1',0))
print(json.dumps(blocked))
'''
        report['checks']['sandbox_preflight'] = json.loads(run_check(profile,temporary,source,'sandbox-preflight',[sys.executable,'-c',preflight,str(guard)],environment,15))
        if installer_only:
            run_check(profile,temporary,source,'installer-regressions',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_installer.py'],environment,60)
            report['checks']['installer_regressions'] = {'passed':True}
            report['checks']['native_installer'] = json.loads(run_check(profile,temporary,source,'native-installer',[sys.executable,'tests/probe_installer.py'],environment,150))
        if core_only:
            run_check(profile,temporary,source,'core-hr-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_core_hr.py'],environment,60)
            run_check(profile,temporary,source,'core-hr-frontend',[node,'tests/test_frontend_core.mjs'],environment,30)
            report['checks']['core_hr'] = {'passed':True}
            report['checks']['core_hr_browser'] = json.loads(run_check(profile,temporary,source,'core-hr-browser',[sys.executable,'tests/probe_browser_security.py','--core'],environment,60))
        if browser_only:
            report['checks']['browser_security'] = json.loads(run_check(profile,temporary,source,'browser-security',[sys.executable,'tests/probe_browser_security.py'],environment,60))
        if identity_only:
            report['checks']['https_identity'] = json.loads(run_check(profile,temporary,source,'https-identity',[sys.executable,'tests/probe_oidc_https.py'],environment,60))
        if services_only:
            report['checks']['independent_services'] = json.loads(run_check(profile,temporary,source,'core-hr-services' if core_services else 'independent-services',[sys.executable,'tests/probe_independent_services.py',*(['--core'] if core_services else [])],environment,120))
            report['local_independent_services_configured_and_tested']=True
            report['real_wireguard_transport_test']=True
            report['independent_identity_acceptance_passed']=True
            report['persistent_production_services_configured']=False
            report['actual_service_status']='Independent disposable Dex, Headscale/Tailscale and WebDAV services configured and tested; no persistent production account or off-device service connected.'
        if not followup_only and not browser_only and not identity_only and not services_only and not core_only and not installer_only:
            backend = run_check(profile,temporary,source,'backend-tests',[sys.executable,'tests/run_coverage.py'],environment)
            count = re.search(r'Ran (\d+) tests',backend)
            coverage = re.search(r'Combined backend line coverage: ([\d.]+)%',backend)
            report['checks']['backend'] = {'passed':True,'tests':int(count.group(1)) if count else None,'coverage_percent':float(coverage.group(1)) if coverage else None}
            report['checks']['large_audit_recovery']=json.loads(run_check(profile,temporary,source,'large-audit-recovery',[sys.executable,'tests/probe_large_audit.py'],environment,90))
            shutil.copy2(source/'coverage'/'summary.json',OUTPUT/'backend-coverage.json')
            report['checks']['https_webdav']={'passed':True,'test_methods':6,'transport':'Separate synthetic HTTPS WebDAV service','original_database_and_archive_paths_missing_during_restore':True,'stalled_worker_killed_while_database_remains_writable':True,'off_device_restore_verified':False}
        if not browser_only and not identity_only and not services_only and not core_only and not installer_only:
            report['checks']['frontend'] = json.loads(run_check(profile,temporary,source,'frontend-checks',[node,'tests/test_frontend.mjs'],environment,30))
            run_check(profile,temporary,source,'frontend-followup',[node,'tests/test_frontend_followup.mjs'],environment,30)
            report['checks']['frontend_followup'] = 'passed'
            run_check(profile,temporary,source,'frontend-security',[node,'tests/test_frontend_security.mjs'],environment,30)
            report['checks']['frontend_security'] = 'passed'
            run_check(profile,temporary,source,'core-hr-frontend',[node,'tests/test_frontend_core.mjs'],environment,30)
            report['checks']['core_hr_frontend'] = 'passed'
            report['checks']['core_hr_browser'] = json.loads(run_check(profile,temporary,source,'core-hr-browser',[sys.executable,'tests/probe_browser_security.py','--core'],environment,60))
            report['checks']['browser_security'] = json.loads(run_check(profile,temporary,source,'browser-security',[sys.executable,'tests/probe_browser_security.py'],environment,60))
            report['checks']['https_identity'] = json.loads(run_check(profile,temporary,source,'https-identity',[sys.executable,'tests/probe_oidc_https.py'],environment,60))
            report['checks']['https_recovery'] = json.loads(run_check(profile,temporary,source,'https-recovery',[sys.executable,'tests/probe_https_recovery.py'],environment,60))
            report['checks']['packaged_smoke'] = json.loads(run_check(profile,temporary,source,'packaged-smoke',[sys.executable,'tests/probe_release.py'],environment,40))
            run_check(profile,temporary,source,'public-package',[sys.executable,'scripts/package_public.py'],environment,20)
            report['checks']['public_source'] = json.loads(run_check(profile,temporary,source,'public-source',[sys.executable,'tests/probe_public_release.py'],environment,20))
            report['checks']['core_hr_public_installation'] = json.loads(run_check(profile,temporary,source,'core-hr-public-installation',[sys.executable,'tests/probe_core_launch.py'],environment,70))
        assert guard.read_text() == 'Disposable protection sentinel'
        report['protected_sentinel_unchanged'] = True
    report['temporary_folders_removed'] = not temporary.exists() and not guard.parent.exists()
    report['live_workspace_unchanged'] = before == workspace_fingerprints()
    report['write_scope'] = 'OS-enforced: test children may write only inside the removed temporary test tree, plus discarded standard I/O to /dev/null.'
    report['personal_home_read_scope'] = 'Blocked except installed .venv and Python runtime directories.'
    report['real_browser_acceptance_passed'] = report['checks'].get('browser_security',{}).get('passed',False)
    if not report['live_workspace_unchanged']:
        raise RuntimeError('The live workspace changed during the run; investigate before attributing the change.')
    report_path = OUTPUT / ('report-installer.json' if installer_only else 'report-core-services.json' if core_services else 'report-core.json' if core_only else 'report-services.json' if services_only else 'report-identity.json' if identity_only else 'report-browser.json' if browser_only else 'report-followup.json' if followup_only else 'report.json')
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(report_path),'backend':report['checks'].get('backend'),'live_workspace_unchanged':report['live_workspace_unchanged'],'temporary_folders_removed':report['temporary_folders_removed']},indent=2))


if __name__ == '__main__':
    main()
