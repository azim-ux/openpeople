"""Check every built installer without executing foreign-platform code."""
import hashlib
import json
from pathlib import Path
import re
import stat
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']


def main():
    pins = dict(re.findall(r'^([\w-]+)==([\d.]+)', (ROOT / 'requirements.txt').read_text(), re.MULTILINE))
    targets = json.loads((ROOT / 'installers/runtimes.json').read_text())['targets']
    source = ROOT / 'release' / f'openpeople-{VERSION}-github.zip'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        source_files = json.loads(archive.read(f'openpeople-{VERSION}-github/SOURCE_MANIFEST.json'))['files']
    results = []
    for target, runtime in targets.items():
        path = ROOT / 'release' / f'openpeople-{VERSION}-{target}-installer.zip'
        prefix = f'OpenPeople-{VERSION}-{target}/'
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read(prefix + 'bundle.json'))
            assert manifest['version'] == VERSION and manifest['target'] == target
            assert manifest['source_sha256'] == source_hash and manifest['runtime_sha256'] == runtime['sha256']
            entries = archive.namelist()
            for entry in archive.infolist():
                assert entry.filename.startswith(prefix) and '..' not in Path(entry.filename).parts
                assert stat.S_ISREG(entry.external_attr >> 16)
                assert not entry.filename.endswith(('.db', '.key', '.setup-token', '.opbackup', '.private', '.log'))
            assert {n[len(prefix + 'payload/'):] for n in entries if n.startswith(prefix + 'payload/')} == set(manifest['files'])
            dependencies = {}
            for name, facts in manifest['files'].items():
                data = archive.read(prefix + 'payload/' + name)
                assert hashlib.sha256(data).hexdigest() == facts['sha256'], name
                assert bool(archive.getinfo(prefix + 'payload/' + name).external_attr >> 16 & 0o111) == facts['executable'], name
                if name.startswith('app/'):
                    assert name[4:] in source_files and source_files[name[4:]] == facts['sha256'], name
                    assert not name.startswith(('app/data/', 'app/tests/', 'app/acceptance-private/', 'app/services-private/'))
                if name.startswith('vendor/') and name.endswith('.dist-info/METADATA'):
                    text = data.decode()
                    package = re.search(r'^Name: (.+)$', text, re.MULTILINE).group(1).strip().replace('_', '-').lower()
                    dependencies[package] = re.search(r'^Version: (.+)$', text, re.MULTILINE).group(1).strip()
            assert dependencies == pins, dependencies
            assert archive.read(prefix + 'installer.py') == archive.read(prefix + 'payload/installer.py') == (ROOT / 'installers/installer.py').read_bytes()
            assert archive.read(prefix + 'payload/desktop.py') == (ROOT / 'installers/desktop.py').read_bytes()
            assert any(name.startswith('runtime/') and name.endswith('LICENSE.txt') for name in manifest['files'])
        results.append({'target': target, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'manifest_files': len(manifest['files']), 'pinned_dependencies': len(dependencies), 'private_workspaces_excluded': True, 'native_execution_verified': False})
    print(json.dumps({'passed': True, 'installers': results, 'foreign_binaries_executed': False}, indent=2))


if __name__ == '__main__': main()
