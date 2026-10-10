import hashlib
from pathlib import Path
import shutil
import sqlite3
import unittest

from identity import totp
from scripts.deployment_check import check_endpoint, check_offline_workspace
from test_app import HRFlows


class DeploymentCheckFlows(HRFlows):
    def test_offline_check_is_read_only_and_detects_missing_mfa_policy(self):
        self.setup_admin()
        folder = Path(self.temp.name) / 'stopped-offline-fixture'
        folder.mkdir(mode=0o700)
        snapshot = folder / 'workspace.db'
        def offline_snapshot():
            source = self.server.connect()
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            snapshot.chmod(0o600)
            shutil.copyfile(Path(self.server.db_path).with_suffix('.key'), snapshot.with_suffix('.key'))
            snapshot.with_suffix('.key').chmod(0o600)
        offline_snapshot()
        def fingerprints():
            return {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode, path.stat().st_mtime_ns) for path in folder.iterdir() if path.is_file()}
        before = fingerprints()
        result = check_offline_workspace(snapshot)
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['workspace_requires_mfa'])
        self.assertEqual(before, fingerprints())
        secret = self.request('POST', '/api/mfa/begin', {})[1]['secret']
        self.assertEqual(self.request('POST', '/api/mfa/confirm', {'otp': totp(secret)})[0], 200)
        self.assertEqual(self.request('POST', '/api/policies', {'require_mfa': True})[0], 200)
        offline_snapshot()
        before = fingerprints()
        self.assertTrue(check_offline_workspace(snapshot)['passed'])
        self.assertEqual(before, fingerprints())
        self.assertFalse(check_offline_workspace(snapshot)['cloud_upload_verified'])

    def test_offline_check_refuses_active_wal_and_unsafe_permissions(self):
        self.setup_admin()
        db = self.server.connect()
        try:
            db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('offline_test_fixture','1')")
            db.commit()
            with self.assertRaisesRegex(ValueError, 'WAL'):
                check_offline_workspace(self.server.db_path)
        finally:
            db.close()
        path = Path(self.server.db_path)
        path.chmod(0o644)
        try:
            self.assertFalse(check_offline_workspace(path)['checks']['database_private_permissions'])
        finally:
            path.chmod(0o600)

    def test_remote_check_rejects_insecure_and_credential_urls(self):
        for origin in ('http://127.0.0.1', 'https://username:password@example.org', 'https://example.org/api', 'https://example.org?token=secret', 'https://example.org/#fragment'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                check_endpoint(origin)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(DeploymentCheckFlows(name) for name in DeploymentCheckFlows.__dict__ if name.startswith('test_'))
