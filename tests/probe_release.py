"""Verify a locally built source archive using this interpreter's installed deps.

Extracts to a disposable folder, checks manifests/private-file exclusions, and
starts an isolated loopback workspace. Does not open the default employee DB.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
ARCHIVE = ROOT / ('release/openpeople-' + VERSION + '-source.zip')

SMOKE = '''import json,tempfile,threading
from pathlib import Path
import requests
from server import HRStore
from serving import create_hardened_server
with tempfile.TemporaryDirectory(prefix="isolated-workspace-") as workspace:
 store=HRStore(Path(workspace)/"workspace.db",port=0)
 server=create_hardened_server(store,port=0)
 store.allowed_hosts={"127.0.0.1:"+str(server.effective_port)}
 thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  origin="http://127.0.0.1:"+str(server.effective_port)
  client=requests.Session();client.trust_env=False
  session=client.get(origin+"/api/session",timeout=5)
  assert session.status_code==200 and session.json()["setup_required"]
  catalog=client.get(origin+"/api/countries",timeout=5).json()
  assert len(catalog["countries"])==251
  assert client.get(origin+"/",timeout=5).status_code==200
  created=client.post(origin+"/api/setup",json={"name":"Fictional Japan HR","email":"packaged@example.org","password":"FictionalPackagePassword123!","country":"JP","include_samples":False},headers={"X-Setup-Token":store.bootstrap_token},timeout=5)
  assert created.status_code==201,created.text
  state=client.get(origin+"/api/state",timeout=5)
  assert state.status_code==200
  employees=state.json()["employees"]
  assert len(employees)==1
  assert (employees[0]["country"],employees[0]["currency"],employees[0]["timezone"])==("JP","JPY","Asia/Tokyo")
  print(json.dumps({"packaged_root_status":200,"country_options":251,"fresh_setup_status":201,"japan_profile":"JP/JPY/Asia-Tokyo","fictional_employees":1}))
 finally:
  server.task_dispatcher.shutdown();server.close();thread.join(timeout=3)
'''


def main():
    with tempfile.TemporaryDirectory(prefix='openpeople-packaged-smoke-') as temporary:
        folder = Path(temporary)
        with zipfile.ZipFile(ARCHIVE) as zipped:
            assert zipped.testzip() is None
            for name in zipped.namelist():
                parts = Path(name).parts
                assert not Path(name).is_absolute() and '..' not in parts
                assert not set(parts).intersection({'data','.venv','__pycache__','.git'})
                assert not name.endswith(('.key','.setup-token','.opbackup'))
            zipped.extractall(folder)
        source = folder / ('openpeople-' + VERSION + '-source')
        manifest = json.loads((source / 'SOURCE_MANIFEST.json').read_text())
        for name,digest in manifest['files'].items():
            assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
        result = subprocess.run([sys.executable,'-c',SMOKE],cwd=source,capture_output=True,text=True,timeout=30)
        assert result.returncode == 0,result.stderr + result.stdout
        observations = json.loads(result.stdout)
        observations.update({'manifest_files_verified':len(manifest['files']),'private_data_excluded':True,'archive_integrity':'passed'})
        print(json.dumps(observations,indent=2))


if __name__ == '__main__':
    main()
