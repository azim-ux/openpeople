"""Verify the public artifact excludes local evidence and matches tested code."""
import hashlib
import json
import re
import stat
from pathlib import Path
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']


def main():
    archive=ROOT/'release'/f'openpeople-{VERSION}-github.zip'
    prefix=f'openpeople-{VERSION}-github/'
    with zipfile.ZipFile(archive) as source:
        assert source.testzip() is None
        for entry in source.infolist():
            mode = entry.external_attr >> 16
            assert entry.create_system == 3 and stat.S_ISREG(mode), entry.filename
            expected = 0o755 if entry.filename == prefix + 'start.command' else 0o644
            assert stat.S_IMODE(mode) == expected, (entry.filename, oct(mode))
        manifest=json.loads(source.read(prefix+'SOURCE_MANIFEST.json'))
        for name,digest in manifest['files'].items():
            path=Path(name)
            assert not path.is_absolute() and '..' not in path.parts
            assert not set(path.parts).intersection({'data','services-private','.venv','.git','__pycache__','audit','validation','release','coverage'})
            assert not name.endswith(('.db','.key','.setup-token','.opbackup','.private','.log','.pem'))
            data=source.read(prefix+name)
            assert hashlib.sha256(data).hexdigest()==digest
            assert not re.search(rb'/Users/[A-Za-z0-9_-]+/',data),name
            if path.suffix in ('.py','.js','.mjs','.yml','.yaml','.toml','.lock') or path.parts[0]=='public':
                assert data==(ROOT/name).read_bytes(),name
        assert {'LICENSE','.gitignore','.github/workflows/verify.yml','.github/dependabot.yml','scripts/setup_workspace.py','provisioning.py','docs/SELF_HOSTING.md','start.command','start.bat'} <= set(manifest['files'])
        assert {'installers/installer.py','installers/desktop.py','installers/runtimes.json','scripts/package_installers.py','.github/workflows/installers.yml','docs/INSTALLERS.md'} <= set(manifest['files'])
        assert set(source.namelist())=={prefix+name for name in manifest['files']}|{prefix+'SOURCE_MANIFEST.json'}
    print(json.dumps({'passed':True,'files':len(manifest['files']),'private_workspaces_and_logs_excluded':True,'runtime_matches_local_source':True,'personal_home_path_excluded':True,'safe_regular_file_modes_and_executable_launcher':True,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))


if __name__=='__main__':main()
