"""Build a source-only release with an explicit allowlist and SHA-256 manifest."""
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

root=Path(__file__).resolve().parents[1]
version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
top_level=['server.py','workspace.py','identity.py','backup.py','serving.py','manage.py','localization.py','payroll.py','countries.json','UNICODE-LICENSE.txt','pyproject.toml','uv.lock','requirements.txt','README.md','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','LICENSE','.gitignore','start.command','start.bat']
top_level.extend(['cloud_backup.py','statutory.py','statutory_uk.py','enterprise.py','access.py','audit_integrity.py','government_submission.py','service_config.py'])
top_level.extend(['pay_periods.py','operations.py'])
top_level.append('service_runner.py')
top_level.append('provisioning.py')
top_level.append('.gitattributes')
top_level.extend(['core_hr.py','core_acceptance.py'])
paths=[root/name for name in top_level]
extensions={'.py','.md','.json','.mjs','.js','.css','.html','.svg','.log','.yml','.yaml'}
for directory in ('public','tests','docs','scripts','deploy','.github','installers'):
    paths.extend(path for path in (root/directory).rglob('*') if path.is_file() and not path.is_symlink() and (path.suffix in extensions or path.name=='Caddyfile') and '__pycache__' not in path.parts)
# A package cannot contain its own final hash. Keep this build's post-package
# proof beside the archive instead of embedding stale proof from an earlier ZIP.
post_package=root/'docs'/'validation'/f'v{version}-isolation'
paths=[path for path in paths if not (path.parent==post_package and path.name.startswith('final-package-'))]
paths=sorted(set(paths))
if any(not path.resolve().is_relative_to(root) or path.is_symlink() for path in paths):
    raise ValueError('Release files must be ordinary files inside the project.')
manifest={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
release=root/'release';release.mkdir(exist_ok=True)
output=release/f'openpeople-{version}-source.zip'
prefix=f'openpeople-{version}-source/'
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
        archive.write(path,prefix+str(path.relative_to(root)))
    archive.writestr(prefix+'SOURCE_MANIFEST.json',json.dumps({'version':version,'files':manifest},indent=2)+'\n')
with zipfile.ZipFile(output) as archive:
    if archive.testzip() is not None:
        raise ValueError('Release archive failed its integrity check.')
    for name,digest in manifest.items():
        if hashlib.sha256(archive.read(prefix+name)).hexdigest()!=digest:
            raise ValueError('Release source digest mismatch.')
print(json.dumps({'archive':str(output),'files':len(manifest),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))
