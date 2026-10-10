"""Export only reviewed public source; never export a live workspace or logs."""
import hashlib
import json
from pathlib import Path
import stat
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']


def public_path(name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:return False
    if name=='SOURCE_MANIFEST.json':return False
    if path.suffix in ('.log','.private','.pem','.key','.db','.opbackup'):return False
    if len(path.parts)==1:
        return path.suffix in ('.py','.md','.toml','.lock','.txt','.json','.command','.bat') or name in ('LICENSE','.gitignore')
    if path.parts[0]=='docs':return len(path.parts)==2 and path.suffix=='.md'
    return path.parts[0] in ('public','tests','scripts','deploy','.github','installers') and path.suffix in ('.py','.mjs','.js','.css','.html','.svg','.md','.yml','.yaml','.json') or path.parts[0]=='deploy' and path.name=='Caddyfile'


def main():
    prefix=f'openpeople-{VERSION}-source/'
    target_prefix=f'openpeople-{VERSION}-github/'
    output=ROOT/'release'/f'openpeople-{VERSION}-github.zip'
    files={}
    with zipfile.ZipFile(ROOT/'release'/f'openpeople-{VERSION}-source.zip') as source:
        for entry in source.infolist():
            if not entry.filename.startswith(prefix):raise ValueError('Unexpected source archive prefix.')
            name=entry.filename[len(prefix):]
            if public_path(name):
                data=source.read(entry)
                # Historical prose may refer to the maintainer's local folder.
                # Runtime/test sources are kept byte-for-byte identical.
                if name.endswith('.md'):
                    data=data.replace(str(ROOT).encode(),b'<project-folder>')
                files[name]=data
    manifest={'version':VERSION,'scope':'Public source only; no deployment credentials or private test logs','files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            write_public_file(archive,target_prefix+name,data,executable=name=='start.command')
        write_public_file(archive,target_prefix+'SOURCE_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'archive':str(output),'files':len(files),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))


def write_public_file(archive,name,data,executable=False):
    # Normalize ordinary source files; do not copy symlink or special-file bits.
    entry=zipfile.ZipInfo(name)
    entry.create_system=3
    entry.external_attr=(stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    entry.compress_type=zipfile.ZIP_DEFLATED
    archive.writestr(entry,data)


if __name__=='__main__':main()
