"""Install the public ZIP and launch its actual production CLI behind local TLS.

Only run inside the mandatory disposable OS sandbox. No external custody claim.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
CADDY = Path('/tmp/openpeople-caddy-audit/caddy')

DRILL = r'''
import base64,json,socket,subprocess,sys,time,shutil
from contextlib import closing
from pathlib import Path
import requests
from server import HRStore
from provisioning import initialize_administrator
from identity import totp
from backup import configure_backup,run_configured_backup,create_backup
from core_acceptance import capture_reference,recover_and_check,endpoint_check
from operations import production_boot_check
root=Path(sys.argv[1]);caddy=Path(sys.argv[2]);checks={};processes=[];logs=[]
password='Fictional package launch password 123!';phrase='Fictional package recovery phrase 123!'
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
backend_port=port();tls_port=port();origin='https://127.0.0.1:'+str(tls_port)
dbpath=root/'host-a/workspace.db';store=HRStore(dbpath,public_origin=origin,product_profile='core-hr')
secret=base64.b32encode(b'01234567890123456789').decode()
initialize_administrator(store,'Fictional package owner','admin@openpeople.invalid',password,secret,totp(secret),'JP')
configure_backup(dbpath,root/'backup-folder',phrase,60,30);run_configured_backup(dbpath)
assert production_boot_check(store)['passed']
checks['production_boot_gates_passed']=True
evidence=root/'evidence';evidence.mkdir(mode=0o700)
installed=subprocess.run([sys.executable,'scripts/accept_core_hr.py','installation','--db',str(dbpath),'--output',str(evidence/'installation.json')],capture_output=True,text=True,timeout=10)
assert installed.returncode==0,installed.stderr
checks['packaged_installation_cli_passed']=True
body=Path('deploy/Caddyfile').read_text().replace('https://10.7.0.1',origin).replace('bind 10.7.0.1','bind 127.0.0.1').replace('127.0.0.1:8000','127.0.0.1:'+str(backend_port))
body=body.replace('    admin off','    admin off\n    skip_install_trust\n    persist_config off\n    storage file_system {\n        root '+str(root/'tls-storage')+'\n    }')
config=root/'Caddyfile';config.write_text(body);ca=root/'tls-storage/pki/authorities/local/root.crt'
def start(name,command):
 log=(root/(name+'.log')).open('w');logs.append(log)
 child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log);processes.append(child);return child
def stop(child):
 if child.poll() is None:child.terminate()
 child.wait(timeout=12)
client=requests.Session();client.trust_env=False;peer=requests.Session();peer.trust_env=False
try:
 app=start('app',[sys.executable,'-u','server.py','--db',str(dbpath),'--port',str(backend_port),'--public-origin',origin,'--production'])
 proxy=start('proxy',[str(caddy),'run','--config',str(config)])
 def call(who,path,method='GET',data=None,csrf=None):
  return who.request(method,origin+path,json=data,headers={'Origin':origin,**({'X-CSRF-Token':csrf} if csrf else {})},verify=str(ca),timeout=8)
 deadline=time.monotonic()+12
 while time.monotonic()<deadline:
  try:
   if ca.exists() and call(client,'/api/session').status_code==200:break
  except requests.RequestException:pass
  time.sleep(.1)
 else:raise AssertionError('Packaged production CLI did not become ready')
 assert call(client,'/api/session').json()['product']['profile']=='core-hr'
 assert endpoint_check(origin,str(ca))['passed']
 endpoint=subprocess.run([sys.executable,'scripts/accept_core_hr.py','endpoint','--origin',origin,'--ca',str(ca),'--output',str(evidence/'endpoint.json')],capture_output=True,text=True,timeout=15)
 assert endpoint.returncode==0,endpoint.stderr
 checks['actual_packaged_production_cli_and_verified_tls']=True
 checks['endpoint_evidence_cli_passed']=True
 logged=call(client,'/api/login','POST',{'email':'admin@openpeople.invalid','password':password,'otp':totp(secret,time.time()+30)})
 assert logged.status_code==200,logged.text
 token=logged.json()['csrf'];old_cookie=client.cookies.get('openpeople_session')
 created=call(client,'/api/employees','POST',{'name':'Fictional peer','email':'peer@openpeople.invalid','title':'Manager','department':'Core team','location':'Remote','annual_salary':1200000,'start_date':'2026-10-01','role':'manager','password':password},token)
 assert created.status_code==201,created.text
 peer_id=created.json()['id'];logged=call(peer,'/api/login','POST',{'email':'peer@openpeople.invalid','password':password})
 assert logged.status_code==200 and logged.json()['mfa_setup_required'];peer_token=logged.json()['csrf']
 assert call(peer,'/api/state').status_code==403
 peer_secret=call(peer,'/api/mfa/begin','POST',{},peer_token).json()['secret']
 assert call(peer,'/api/mfa/confirm','POST',{'otp':totp(peer_secret)},peer_token).status_code==200
 before=next(r for r in call(peer,'/api/state').json()['employees'] if r['id']==peer_id)
 assert call(client,'/api/employees/'+str(peer_id),'PATCH',{'title':'Verified peer manager','expected_version':before['version']},token).status_code==200
 after=next(r for r in call(peer,'/api/state').json()['employees'] if r['id']==peer_id)
 assert after['title']=='Verified peer manager' and after['version']>before['version']
 assert call(client,'/api/employees/'+str(peer_id),'PATCH',{'title':'Stale overwrite','expected_version':before['version']},token).status_code==409
 assert call(client,'/api/payroll').status_code==404
 assert call(client,'/api/policies','POST',{'require_mfa':False},token).status_code==400
 checks['two_clients_mfa_collaboration_and_stale_edit_denial']=True
 checks['core_scope_and_production_mfa_enforced']=True
 stop(app);stop(proxy)
 reference=capture_reference(dbpath);archive=create_backup(dbpath,root/'download',phrase)
 dbpath.parent.rename(root/'unavailable-original-host');assert not dbpath.exists()
 recovery=recover_and_check(archive,root/'host-b',phrase,reference,60);assert recovery['passed'],recovery
 assert not recovery['off_device_recovery_verified']
 restored=HRStore(recovery['restored_database'],public_origin=origin,product_profile='core-hr')
 assert not production_boot_check(restored)['passed'] # Replacement host needs a new backup configuration.
 checks['downloaded_copy_restore_without_original_paths']=True
 checks['record_fingerprint_audit_and_removed_credentials_verified']=True
 checks['replacement_host_requires_new_backup_configuration']=True
 print(json.dumps({'passed':True,'checks':checks,'product_profile':'core-hr','physical_off_device_recovery_verified':False,'actual_remote_network_verified':False,'enterprise_production_approved':False}))
finally:
 for child in reversed(processes):
  if child.poll() is None:
   try:stop(child)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
 for log in logs:log.close()
'''


def main():
    if not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-') or os.environ.get('PYTHONDONTWRITEBYTECODE') != '1':
        raise SystemExit('Use the enforced isolation runner.')
    archive = ROOT / 'release' / f'openpeople-{VERSION}-github.zip'
    prefix = f'openpeople-{VERSION}-github/'
    with tempfile.TemporaryDirectory(prefix='openpeople-core-install-') as folder:
        root = Path(folder)
        with zipfile.ZipFile(archive) as source:
            assert source.testzip() is None
            for name in source.namelist():
                assert name.startswith(prefix) and '..' not in Path(name).parts and not Path(name).is_absolute()
            source.extractall(root)
        installed = root / prefix.rstrip('/')
        manifest = json.loads((installed / 'SOURCE_MANIFEST.json').read_text())
        for name, digest in manifest['files'].items():
            assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == digest
        result = subprocess.run([sys.executable, '-c', DRILL, str(root), str(CADDY)], cwd=installed,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr + result.stdout
        report = json.loads(result.stdout)
        report['public_archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        report['fresh_source_installation'] = True
        print(json.dumps(report, indent=2))


if __name__ == '__main__':main()
