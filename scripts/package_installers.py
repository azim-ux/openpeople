"""Build offline cross-platform installer ZIPs with verified portable runtimes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'installers'))
from installer import host_target, safe_path

VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
RUNTIMES = json.loads((ROOT / 'installers/runtimes.json').read_text())


def fetch_runtime(target, cache):
    facts = RUNTIMES['targets'][target]
    if not facts['url'].startswith('https://github.com/astral-sh/python-build-standalone/releases/download/') or not re.fullmatch(r'[0-9a-f]{64}', facts['sha256']):
        raise ValueError('Invalid pinned runtime source.')
    path = cache / (target + '-' + facts['sha256'] + '.tar.gz')
    if not path.exists():
        request = urllib.request.Request(facts['url'], headers={'User-Agent': 'OpenPeople-installer-build'})
        temporary = path.with_suffix('.part')
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('xb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != facts['sha256']: raise ValueError('Downloaded runtime digest differs from the upstream pinned digest.')
            temporary.replace(path)
        finally: temporary.unlink(missing_ok=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != facts['sha256']: raise ValueError('Cached runtime digest is incorrect.')
    return path


def extract_runtime(archive, destination):
    destination.mkdir(mode=0o700)
    with tarfile.open(archive, 'r:gz') as source:
        for member in source.getmembers():
            if not (member.name == 'python' or member.name.startswith('python/')): raise ValueError('Unexpected runtime archive root.')
            safe_path(member.name.rstrip('/'))
        # Linux terminfo aliases can collide on a case-insensitive Mac build disk.
        # The browser/server needs no bundled terminal database; use host terminfo.
        members = [member for member in source.getmembers() if member.name != 'python/share/terminfo' and not member.name.startswith('python/share/terminfo/')]
        source.extractall(destination, members=members, filter='data')
    runtime = destination / 'python'
    for path in runtime.rglob('*'):
        if not path.resolve().is_relative_to(runtime.resolve()): raise ValueError('Runtime link leaves its directory.')
    return runtime


def hashed_requirements():
    packages = {p['name'].replace('_', '-').lower(): p for p in tomllib.loads((ROOT / 'uv.lock').read_text())['package']}
    lines = []
    for line in (ROOT / 'requirements.txt').read_text().splitlines():
        match = re.match(r'^([\w-]+)==([\d.]+)', line)
        if not match: continue
        name, version = match.groups()
        package = packages[name.replace('_', '-').lower()]
        if package['version'] != version: raise ValueError('Requirements and lock file differ.')
        hashes = sorted({w['hash'] for w in package.get('wheels', [])})
        if not hashes: raise ValueError('Every bundled dependency must have a pinned wheel hash.')
        lines.append(name + '==' + version + ''.join(' --hash=' + digest for digest in hashes))
    if len(lines) != 11: raise ValueError('Review a changed dependency list before building installers.')
    return '\n'.join(lines) + '\n'


def app_source(destination):
    archive = ROOT / 'release' / f'openpeople-{VERSION}-github.zip'
    prefix = f'openpeople-{VERSION}-github/'
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read(prefix + 'SOURCE_MANIFEST.json'))
        for name, digest in manifest['files'].items():
            safe_path(name)
            contents = source.read(prefix + name)
            if hashlib.sha256(contents).hexdigest() != digest: raise ValueError('Public source manifest failed.')
            if name.startswith(('tests/', '.github/', 'installers/')): continue
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def build(target, cache, pip_python):
    release = ROOT / 'release'
    with tempfile.TemporaryDirectory(prefix='installer-build-', dir=release) as folder:
        work = Path(folder)
        kit = work / f'OpenPeople-{VERSION}-{target}'
        payload = kit / 'payload'
        payload.mkdir(parents=True)
        runtime = extract_runtime(fetch_runtime(target, cache), work / 'unpacked')
        shutil.copytree(runtime, payload / 'runtime', symlinks=False)
        source_digest = app_source(payload / 'app')
        requirements = work / 'hashed-requirements.txt'
        requirements.write_text(hashed_requirements())
        command = [str(pip_python), '-I', '-m', 'pip', '--isolated', '--cache-dir', str(cache / 'pip'), 'install', '--index-url', 'https://pypi.org/simple', '--require-hashes', '--only-binary=:all:', '--no-deps', '--no-compile', '--disable-pip-version-check', '--no-warn-script-location', '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313', '--abi', 'abi3', '--abi', 'none', '--target', str(payload / 'vendor'), '-r', str(requirements)]
        for tag in RUNTIMES['targets'][target]['platforms']: command.extend(['--platform', tag])
        subprocess.run(command, check=True, timeout=180)
        # Console-script wrappers are unnecessary and can embed build-machine paths.
        for directory in ('bin', 'Scripts'):
            if (payload / 'vendor' / directory).exists(): shutil.rmtree(payload / 'vendor' / directory)
        for path in list(payload.rglob('__pycache__')):
            if path.is_dir(): shutil.rmtree(path)
        shutil.copy2(ROOT / 'installers/installer.py', kit / 'installer.py')
        for name in ('installer.py', 'desktop.py'): shutil.copy2(ROOT / 'installers' / name, payload / name)
        if target.startswith('windows'):
            (kit / 'Install.cmd').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\n"payload\\runtime\\python.exe" -I -B installer.py %*\r\nset "openpeople_result=%errorlevel%"\r\npause\r\nexit /b %openpeople_result%\r\n')
        else:
            entry = 'Install.command' if target.startswith('macos') else 'install.sh'
            (kit / entry).write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec ./payload/runtime/bin/python3 -I -B installer.py "$@"\n')
            (kit / entry).chmod(0o755)
        (kit / 'README.txt').write_text('OpenPeople ' + VERSION + '\nOffline per-user installer: Python and application dependencies are included.\nExtract the entire ZIP, then run Install.cmd (Windows), Install.command (Mac) or ./install.sh (Linux).\nNo administrator password or employee data is included. Programs and private data are stored separately.\nDo not publish an installed workspace. Verify the download SHA-256 from the release.\nUnsigned: obey your platform\'s normal publisher-approval process; do not disable operating-system security.\nRead payload/app/docs/INSTALLERS.md for installation, startup, backups and testing scope.\n')
        files = {}
        for path in sorted(payload.rglob('*')):
            if not path.is_file(): continue
            name = path.relative_to(payload).as_posix()
            files[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': bool(path.stat().st_mode & 0o111)}
        manifest = {'format': 1, 'version': VERSION, 'target': target, 'source_sha256': source_digest, 'python': RUNTIMES['python_version'], 'runtime_url': RUNTIMES['targets'][target]['url'], 'runtime_sha256': RUNTIMES['targets'][target]['sha256'], 'files': files}
        (kit / 'bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
        output = release / f'openpeople-{VERSION}-{target}-installer.zip'
        pending = work / output.name
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(kit.rglob('*')):
                if not path.is_file(): continue
                entry = zipfile.ZipInfo(path.relative_to(work).as_posix())
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | (0o755 if path.stat().st_mode & 0o111 else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
        with zipfile.ZipFile(pending) as archive:
            if archive.testzip() is not None: raise ValueError('Built installer ZIP integrity failed.')
        pending.replace(output)
        return {'target': target, 'file': output.name, 'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'source_sha256': source_digest, 'runtime_sha256': manifest['runtime_sha256'], 'payload_files': len(files), 'native_execution_verified': False}


def main():
    parser = argparse.ArgumentParser(description='Build offline installers. Downloads only pinned, digest-verified runtimes and wheels.')
    parser.add_argument('--target', choices=sorted(RUNTIMES['targets']), action='append')
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    cache = ROOT / 'release/installer-cache'
    cache.mkdir(parents=True, exist_ok=True)
    targets = args.target or list(RUNTIMES['targets'])
    if args.download_only:
        for target in targets: print(str(fetch_runtime(target, cache)), flush=True)
        return
    with tempfile.TemporaryDirectory(prefix='installer-pip-', dir=ROOT / 'release') as folder:
        if importlib.util.find_spec('pip'): pip_python = Path(sys.executable)
        else:
            runtime = extract_runtime(fetch_runtime(host_target(), cache), Path(folder) / 'unpacked')
            pip_python = runtime / ('python.exe' if os.name == 'nt' else 'bin/python3')
        reports = [build(target, cache, pip_python) for target in targets]
    (ROOT / 'release' / f'openpeople-{VERSION}-installers.json').write_text(json.dumps({'version': VERSION, 'installers': reports, 'signed_or_notarized': False, 'hosted_ci_executed': False}, indent=2) + '\n')
    (ROOT / 'release' / f'openpeople-{VERSION}-SHA256SUMS.txt').write_text(''.join(r['sha256'] + '  ' + r['file'] + '\n' for r in reports))
    print(json.dumps(reports, indent=2))


if __name__ == '__main__': main()
