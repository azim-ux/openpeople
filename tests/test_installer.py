"""Install/update/uninstall safety without modifying the real user profile."""
import hashlib
import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'installers/installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.kit = self.base / 'kit'
        (self.kit / 'payload/runtime/bin').mkdir(parents=True)
        (self.kit / ('payload/runtime/python.exe' if os.name == 'nt' else 'payload/runtime/bin/python3')).write_text('fake runtime')
        (self.kit / 'payload/desktop.py').write_text('fake launcher')
        (self.kit / 'payload/installer.py').write_text('fake installer')
        self.root = self.base / 'home with spaces/OpenPeople'
        self.make_manifest()

    def make_manifest(self, version='0.8.1'):
        files = {p.relative_to(self.kit / 'payload').as_posix(): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'executable': p.name == 'python3'} for p in (self.kit / 'payload').rglob('*') if p.is_file()}
        (self.kit / 'bundle.json').write_text(json.dumps({'format': 1, 'version': version, 'target': installer.host_target(), 'files': files}))

    def install(self):
        return installer.install(self.kit, self.root)

    def test_fresh_install_and_reinstall_preserve_data_and_external_files(self):
        result = self.install()
        self.assertTrue((self.root / result['program'] / 'desktop.py').is_file())
        sentinel = self.base / 'personal.txt'; sentinel.write_text('untouched')
        db = self.root / 'data/openpeople.db'; db.write_bytes(b'fictional employee data')
        self.install()
        self.assertEqual(db.read_bytes(), b'fictional employee data')
        self.assertEqual(sentinel.read_text(), 'untouched')

    def test_upgrade_keeps_old_program_and_data(self):
        first = self.install()
        db = self.root / 'data/openpeople.db'; db.write_bytes(b'fictional data')
        self.make_manifest('0.8.2')
        second = self.install()
        self.assertNotEqual(first['program'], second['program'])
        self.assertTrue((self.root / first['program']).exists())
        self.assertEqual(db.read_bytes(), b'fictional data')

    def test_tampered_bundle_fails_before_installation(self):
        (self.kit / 'payload/desktop.py').write_text('tampered')
        with self.assertRaises(ValueError): self.install()
        self.assertFalse(self.root.exists())

    def test_traversal_and_extra_payload_are_rejected(self):
        path = self.kit / 'bundle.json'; manifest = json.loads(path.read_text())
        manifest['files']['../outside'] = next(iter(manifest['files'].values())); path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): self.install()
        self.make_manifest(); (self.kit / 'payload/unlisted.py').write_text('extra')
        with self.assertRaises(ValueError): self.install()

    def test_wrong_platform_is_rejected(self):
        path = self.kit / 'bundle.json'; manifest = json.loads(path.read_text()); manifest['target'] = 'unsupported'; path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): self.install()

    def test_symlink_payload_and_destination_are_rejected(self):
        victim = self.base / 'victim'; victim.write_text('personal')
        (self.kit / 'payload/desktop.py').unlink(); (self.kit / 'payload/desktop.py').symlink_to(victim)
        with self.assertRaises(ValueError): self.install()
        (self.kit / 'payload/desktop.py').unlink(); (self.kit / 'payload/desktop.py').write_text('fake launcher'); self.make_manifest()
        self.root.parent.mkdir(parents=True); self.root.symlink_to(self.base)
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(victim.read_text(), 'personal')

    def test_unrelated_existing_directory_is_not_adopted(self):
        self.root.mkdir(parents=True); (self.root / 'personal.txt').write_text('keep')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual((self.root / 'personal.txt').read_text(), 'keep')

    def test_running_workspace_prevents_upgrade_and_uninstall(self):
        self.install()
        with installer.workspace_lock(self.root):
            with self.assertRaises(ValueError): self.install()
            with self.assertRaises(ValueError): installer.uninstall(self.root)

    def test_partial_install_failure_keeps_previous_release(self):
        first = self.install(); self.make_manifest('0.8.2')
        with patch.object(installer.shutil, 'copytree', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(json.loads((self.root / 'installation.json').read_text())['program'], first['program'])
        self.assertFalse(list((self.root / 'versions').glob('.staging-*')))

    def test_launcher_publication_failure_rolls_back_previous_launchers(self):
        first = self.install(); self.make_manifest('0.8.2')
        previous = {name: (self.root / name).read_bytes() for name in first['managed']}
        original = installer.atomic_file; failed = False
        def write(path, contents, mode=0o600):
            nonlocal failed
            if Path(path).name.startswith('Uninstall.') and not failed:
                failed = True; raise OSError('simulated publication failure')
            return original(path, contents, mode)
        with patch.object(installer, 'atomic_file', side_effect=write):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(json.loads((self.root / 'installation.json').read_text())['program'], first['program'])
        for name, contents in previous.items(): self.assertEqual((self.root / name).read_bytes(), contents)
        self.assertFalse((self.root / ('versions/0.8.2-' + installer.host_target())).exists())

    def test_uninstall_preserves_workspace_and_unknown_files(self):
        result = self.install()
        db = self.root / 'data/openpeople.db'; db.write_bytes(b'fictional data')
        extra = self.root / 'personal.txt'; extra.write_text('keep')
        installer.uninstall(self.root)
        self.assertEqual((self.root / result['program']).exists(), os.name == 'nt')
        self.assertEqual(db.read_bytes(), b'fictional data')
        self.assertEqual(extra.read_text(), 'keep')

    def test_reinstall_after_uninstall_keeps_workspace(self):
        self.install()
        db = self.root / 'data/openpeople.db'; db.write_bytes(b'fictional retained workspace')
        installer.uninstall(self.root)
        self.install()
        self.assertEqual(db.read_bytes(), b'fictional retained workspace')

    def test_modified_launcher_is_not_overwritten(self):
        self.install()
        launcher = self.root / ('Launch.cmd' if installer.host_target().startswith('windows') else 'Launch.command')
        launcher.write_text('my personal replacement')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(launcher.read_text(), 'my personal replacement')

    def test_uninstall_rejects_tampered_registry_paths(self):
        self.install()
        path = self.root / 'installation.json'; state = json.loads(path.read_text()); state['program'] = '../outside'; path.write_text(json.dumps(state))
        with self.assertRaises(ValueError): installer.uninstall(self.root)

    def test_linked_program_parent_cannot_redirect_uninstall(self):
        result = self.install()
        outside = self.base / 'unrelated-copy'
        installer.shutil.copytree(self.root / 'versions', outside)
        (self.root / 'versions').rename(self.base / 'held-versions')
        (self.root / 'versions').symlink_to(outside, target_is_directory=True)
        protected = outside / Path(result['program']).name / 'desktop.py'
        before = protected.read_bytes()
        with self.assertRaises(ValueError): installer.uninstall(self.root)
        self.assertEqual(protected.read_bytes(), before)

    def test_windows_acl_verification_requires_explicit_success(self):
        with patch.object(installer.os, 'name', 'nt'), patch.dict(os.environ, {'PSModulePath': 'incompatible PowerShell modules'}), patch.object(installer.subprocess, 'run') as apply_acl, patch.object(installer.subprocess, 'check_output', side_effect=['S-1-5-21-123\n', 'OPENPEOPLE_ACL_PRIVATE\n']) as powershell:
            installer.windows_private_acl(self.root)
        apply_acl.assert_called_once()
        for call in powershell.call_args_list:
            self.assertFalse(any(k.lower() == 'psmodulepath' for k in call.kwargs['env']))
        script = base64.b64decode(powershell.call_args.args[0][-1]).decode('utf-16-le')
        self.assertIn("$ErrorActionPreference='Stop'", script)
        self.assertIn("Write-Output 'OPENPEOPLE_ACL_PRIVATE'", script)

    def test_windows_acl_verification_fails_closed_on_missing_output(self):
        with patch.object(installer.os, 'name', 'nt'), patch.object(installer.subprocess, 'run'), patch.object(installer.subprocess, 'check_output', side_effect=['S-1-5-21-123', '']):
            with self.assertRaises(ValueError): installer.windows_private_acl(self.root)

    def test_windows_acl_verification_propagates_powershell_errors(self):
        with patch.object(installer.os, 'name', 'nt'), patch.object(installer.subprocess, 'run'), patch.object(installer.subprocess, 'check_output', side_effect=['S-1-5-21-123', subprocess.CalledProcessError(1, 'powershell')]):
            with self.assertRaises(subprocess.CalledProcessError): installer.windows_private_acl(self.root)


if __name__ == '__main__': unittest.main()
