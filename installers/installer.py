"""Offline, per-user installation. Never installs services or deletes HR data."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

TARGETS = {'macos-arm64', 'windows-x64', 'linux-x64'}
OWNER = 'org.openpeople'


def is_link(path):
    return path.is_symlink() or path.is_junction()


def host_target():
    machine = platform.machine().lower()
    architecture = 'arm64' if machine in ('arm64', 'aarch64') else 'x64' if machine in ('amd64', 'x86_64') else 'unsupported'
    os_name = {'darwin': 'macos', 'win32': 'windows', 'linux': 'linux'}.get(sys.platform, 'unsupported')
    return os_name + '-' + architecture


def default_root():
    if sys.platform == 'win32':
        if not os.environ.get('LOCALAPPDATA'): raise ValueError('Local AppData is unavailable; choose a dedicated --root.')
        return Path(os.environ['LOCALAPPDATA']) / 'OpenPeople'
    if sys.platform == 'darwin': return Path.home() / 'Library/Application Support/OpenPeople'
    return Path.home() / '.local/share/OpenPeople'


def safe_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or path.as_posix() != name:
        raise ValueError('Invalid installer file path.')
    return path


def checked_root(root):
    root = Path(root).absolute()
    if any(c in str(root) for c in '\r\n\x00') or (os.name == 'nt' and any(c in str(root) for c in '"%!^&|<>')):
        raise ValueError('Choose a normal dedicated installation path.')
    for path in (root, *root.parents):
        if is_link(path): raise ValueError('Installation paths cannot contain symbolic links or junctions.')
    if root == Path(root.anchor) or root == Path.home(): raise ValueError('Choose a dedicated OpenPeople folder.')
    return root


def private_directory(path):
    if is_link(path) or (path.exists() and not path.is_dir()): raise ValueError('An installation directory was replaced.')
    # Windows children inherit the explicitly protected installation ACL.
    # Python's Windows mode 0700 adds an explicit Administrators group grant.
    path.mkdir(parents=True, mode=0o700 if os.name == 'posix' else 0o777, exist_ok=True)
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        raise ValueError('The OpenPeople directory must be private to its owner.')


def windows_private_acl(root):
    if os.name != 'nt': return
    # PowerShell 7's inherited module path can break Windows PowerShell 5.1.
    environment = {key: value for key, value in os.environ.items() if key.lower() != 'psmodulepath'}
    sid = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference='Stop'; [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"], text=True, timeout=15, env=environment).strip()
    if not re.fullmatch(r'S-1-(?:5|12)-[0-9-]+', sid): raise ValueError('Could not identify the installing Windows account.')
    subprocess.run(['icacls.exe', str(root), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True, stdout=subprocess.DEVNULL, timeout=15)
    subprocess.run(['icacls.exe', str(root), '/remove:g', '*S-1-5-32-544', '*S-1-3-4'], check=True, stdout=subprocess.DEVNULL, timeout=15)
    # Refuse pre-existing explicit grants to other accounts as well.
    script = "$ErrorActionPreference='Stop'; $allowed=@('" + sid + "','S-1-5-18'); $acl=Get-Acl -LiteralPath '" + str(root).replace("'", "''") + "'; if ($null -eq $acl) { throw 'ACL unavailable' }; $unexpected=@($acl.Access | Where-Object { $_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -notin $allowed }); if ($unexpected.Count -ne 0) { throw ('Unexpected Windows directory grants: ' + (($unexpected | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }) -join ', ')) }; Write-Output 'OPENPEOPLE_ACL_PRIVATE'"
    encoded = base64.b64encode(script.encode('utf-16-le')).decode()
    result = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], text=True, timeout=15, env=environment).strip()
    if result != 'OPENPEOPLE_ACL_PRIVATE': raise ValueError('Windows directory privacy could not be verified.')


@contextmanager
def workspace_lock(root):
    data = Path(root) / 'data'
    private_directory(data)
    windows_private_acl(data)
    path = data / 'host.lock'
    if is_link(path): raise ValueError('The workspace lock was replaced.')
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'r+b') as handle:
        try:
            # Windows byte-range locks prohibit even reading the locked byte.
            if os.fstat(handle.fileno()).st_size == 0: handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Stop the running OpenPeople application before installing, updating or uninstalling.') from error
        try: yield
        finally:
            handle.seek(0)
            if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def verified_bundle(kit):
    manifest = json.loads((kit / 'bundle.json').read_text())
    if manifest.get('format') != 1 or manifest.get('target') != host_target() or manifest['target'] not in TARGETS:
        raise ValueError('This installer is for a different operating system or processor.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', manifest.get('version', '')): raise ValueError('Invalid installer version.')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files: raise ValueError('Empty installer payload.')
    payload = kit / 'payload'
    if is_link(payload): raise ValueError('Installer payload directory was replaced.')
    actual = set()
    for path in payload.rglob('*'):
        if is_link(path) or not (path.is_file() or path.is_dir()): raise ValueError('Installer payload contains a link or special file.')
        if path.is_file(): actual.add(path.relative_to(payload).as_posix())
    if actual != set(files): raise ValueError('Installer payload has missing or unlisted files.')
    for name, facts in files.items():
        safe_path(name)
        if not isinstance(facts, dict) or not re.fullmatch(r'[0-9a-f]{64}', facts.get('sha256', '')) or type(facts.get('executable')) is not bool:
            raise ValueError('Invalid installer manifest.')
        if hashlib.sha256((payload / name).read_bytes()).hexdigest() != facts['sha256']:
            raise ValueError('Installer integrity failed; download an intact release.')
    required = {'desktop.py', 'installer.py', 'runtime/python.exe' if host_target().startswith('windows') else 'runtime/bin/python3'}
    if not required <= actual: raise ValueError('Installer runtime or launcher is missing.')
    return manifest


def read_state(root):
    path = root / 'installation.json'
    if is_link(path): raise ValueError('The installation record was replaced.')
    if not path.exists(): return None
    state = json.loads(path.read_text())
    if state.get('owner') != OWNER or state.get('format') != 1 or state.get('target') != host_target():
        raise ValueError('This folder is not this platform\'s OpenPeople installation.')
    programs = state.get('programs')
    if not isinstance(programs, list) or not programs or state.get('program') not in programs:
        raise ValueError('Invalid installed program inventory.')
    for name in programs:
        safe_path(name)
        if not re.fullmatch(r'versions/\d+\.\d+\.\d+-' + re.escape(host_target()), name): raise ValueError('Invalid installed program path.')
        program = root / name
        if any(is_link(p) for p in (program, *program.parents)) or not program.is_dir(): raise ValueError('An installed program was replaced.')
        for entry in program.rglob('*'):
            if is_link(entry): raise ValueError('Installed program contains a symbolic link or junction.')
        marker = program / '.openpeople-program.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('owner') != OWNER:
            raise ValueError('An installed program has no ownership marker.')
    managed = state.get('managed')
    if not isinstance(managed, dict): raise ValueError('Invalid installed launcher inventory.')
    for name, digest in managed.items():
        safe_path(name)
        if name not in managed_names() or not re.fullmatch(r'[0-9a-f]{64}', digest): raise ValueError('Invalid installed launcher path.')
        path = root / name
        if any(is_link(p) for p in (path, *path.parents)) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('An installed launcher was changed; it will not be overwritten or removed.')
    return state


def managed_names():
    return {'Launch.cmd', 'Uninstall.cmd', 'Launch.command', 'Uninstall.command', 'OpenPeople.desktop', 'OpenPeople.app/Contents/Info.plist', 'OpenPeople.app/Contents/MacOS/OpenPeople'}


def launchers(root, program):
    python = root / program / ('runtime/python.exe' if os.name == 'nt' else 'runtime/bin/python3')
    desktop = root / program / 'desktop.py'
    tool = root / program / 'installer.py'
    if os.name == 'nt':
        launch = '@echo off\r\n"' + str(python) + '" -I -B "' + str(desktop) + '" --db "' + str(root / 'data/openpeople.db') + '" %*\r\nif errorlevel 1 pause\r\n'
        remove = '@echo off\r\n"' + str(python) + '" -I -B "' + str(tool) + '" uninstall --root "' + str(root) + '"\r\npause\r\n'
        return {'Launch.cmd': launch.encode(), 'Uninstall.cmd': remove.encode()}
    command = shlex.join([str(python), '-I', '-B', str(desktop), '--db', str(root / 'data/openpeople.db')])
    remove = shlex.join([str(python), '-I', '-B', str(tool), 'uninstall', '--root', str(root)])
    files = {'Launch.command': ('#!/bin/sh\nexec ' + command + ' "$@"\n').encode(), 'Uninstall.command': ('#!/bin/sh\nexec ' + remove + '\n').encode()}
    if sys.platform == 'darwin':
        import plistlib
        files['OpenPeople.app/Contents/Info.plist'] = plistlib.dumps({'CFBundleIdentifier': OWNER, 'CFBundleName': 'OpenPeople', 'CFBundleExecutable': 'OpenPeople', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1'})
        # Pass the launch path as an argument; AppleScript quotes it for Terminal.
        body = '#!/bin/sh\nexec /usr/bin/osascript - ' + shlex.quote(str(root / 'Launch.command')) + " <<'OPENPEOPLE_APP'\non run argv\n tell application \"Terminal\"\n  activate\n  do script quoted form of item 1 of argv\n end tell\nend run\nOPENPEOPLE_APP\n"
        files['OpenPeople.app/Contents/MacOS/OpenPeople'] = body.encode()
    else:
        escaped = str(root / 'Launch.command').replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        files['OpenPeople.desktop'] = ('[Desktop Entry]\nType=Application\nName=OpenPeople\nComment=Self-hosted Core HR\nExec="' + escaped + '"\nTerminal=true\nCategories=Office;\n').encode()
    return files


def atomic_file(path, contents, mode=0o600):
    private_directory(path.parent)
    if is_link(path): raise ValueError('An installation file was replaced.')
    descriptor, temporary = tempfile.mkstemp(prefix='.openpeople-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle: handle.write(contents); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def install(kit, root):
    kit = Path(kit)
    manifest = verified_bundle(kit)  # Reject tampering before touching the host.
    root = checked_root(root)
    previous = read_state(root) if root.exists() else None
    receipt = root / '.openpeople-owner.json'
    retained = receipt.is_file() and not is_link(receipt) and json.loads(receipt.read_text()) == {'owner': OWNER, 'format': 1}
    if root.exists() and previous is None and any(root.iterdir()) and not retained: raise ValueError('Choose an empty folder; unrelated files will not be adopted.')
    private_directory(root)
    windows_private_acl(root)
    if not retained: atomic_file(receipt, json.dumps({'owner': OWNER, 'format': 1}).encode())
    with workspace_lock(root):
        previous = read_state(root)
        private_directory(root / 'versions')
        program = 'versions/' + manifest['version'] + '-' + manifest['target']
        final = root / program
        files = launchers(root, program)
        owned = previous.get('managed', {}) if previous else {}
        for name in files:
            path = root / name
            if path.exists() and name not in owned: raise ValueError('An unrelated launcher already exists.')
            if any(is_link(p) for p in (path, *path.parents)): raise ValueError('A launcher directory was replaced.')
        if final.exists():
            if not previous or program not in previous['programs']: raise ValueError('The program destination already exists.')
            # Reinstall the exact same release without replacing a running runtime.
            for name, facts in manifest['files'].items():
                if not (final / name).is_file() or hashlib.sha256((final / name).read_bytes()).hexdigest() != facts['sha256']:
                    raise ValueError('Installed program differs; use a new release or uninstall its program files first.')
        else:
            stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=root / 'versions'))
            try:
                windows_private_acl(stage)
                shutil.copytree(kit / 'payload', stage, dirs_exist_ok=True)
                os.chmod(stage, 0o700)
                for path in stage.rglob('*'):
                    if path.is_dir(): os.chmod(path, 0o700)
                    else: os.chmod(path, 0o700 if manifest['files'][path.relative_to(stage).as_posix()]['executable'] else 0o600)
                atomic_file(stage / '.openpeople-program.json', json.dumps({'owner': OWNER, 'version': manifest['version'], 'target': manifest['target']}).encode())
                stage.rename(final)
            finally:
                if stage.exists(): shutil.rmtree(stage)
        old_contents = {name: (root / name).read_bytes() for name in files if name in owned}
        try:
            for name, contents in files.items():
                atomic_file(root / name, contents, 0o700 if name.endswith(('.command', '.desktop')) or name.endswith('/MacOS/OpenPeople') else 0o600)
            state = {'format': 1, 'owner': OWNER, 'target': manifest['target'], 'version': manifest['version'], 'program': program, 'programs': sorted(set((previous or {}).get('programs', []) + [program])), 'managed': {name: hashlib.sha256(contents).hexdigest() for name, contents in files.items()}}
            atomic_file(root / 'installation.json', (json.dumps(state, indent=2) + '\n').encode())
        except Exception:
            for name in files:
                if name in old_contents: atomic_file(root / name, old_contents[name], 0o700 if name.endswith(('.command', '.desktop')) or name.endswith('/MacOS/OpenPeople') else 0o600)
                else: (root / name).unlink(missing_ok=True)
            # Only the newly published version belongs to this failed transaction.
            if not previous or program not in previous['programs']: shutil.rmtree(final)
            raise
    return state


def uninstall(root):
    root = checked_root(root)
    state = read_state(root)
    if not state: raise ValueError('No managed OpenPeople installation was found.')
    with workspace_lock(root):
        state = read_state(root)
        # A Windows process cannot reliably remove its own loaded runtime.
        # Keep its inventory so a reinstall can verify/reuse it safely.
        for name in state['programs']:
            if os.name != 'nt': shutil.rmtree(root / name)
        for name in state['managed']: (root / name).unlink()
        if os.name == 'nt':
            state.update(managed={}, uninstalled=True)
            atomic_file(root / 'installation.json', (json.dumps(state, indent=2) + '\n').encode())
        else: (root / 'installation.json').unlink()
    return {'data_preserved': True, 'windows_program_cleanup_pending': os.name == 'nt'}


def main():
    parser = argparse.ArgumentParser(description='Install OpenPeople offline for this user. Employee data is preserved.')
    parser.add_argument('action', nargs='?', choices=('install', 'uninstall'), default='install')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--yes', action='store_true', help='Accept install/uninstall without an interactive confirmation.')
    args = parser.parse_args()
    root = args.root or default_root()
    print('OpenPeople ' + args.action + '\nLocation: ' + str(root))
    if args.action == 'install': print('Programs and private employee data are separate. Stop OpenPeople and verify a backup before updating.')
    else: print('Employee data and recovery material will be kept. Windows may retain program folders for manual cleanup.')
    if not args.yes and input('Continue? [y/N] ').strip().lower() not in ('y', 'yes'): return
    try:
        if args.action == 'install':
            install(Path(__file__).resolve().parent, root)
            print('Installed. Open ' + str(root / ('Launch.cmd' if os.name == 'nt' else 'Launch.command')))
            print('First-run account setup is completed privately in your browser. No default password is included.')
        else: uninstall(root); print('Uninstalled program launchers. Your data remains in ' + str(root / 'data'))
    except (ValueError, OSError, subprocess.SubprocessError) as error: parser.exit(1, str(error) + '\n')


if __name__ == '__main__': main()
