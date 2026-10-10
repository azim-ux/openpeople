import json
from pathlib import Path
import tempfile
import sqlite3
import unittest

from test_app import HRFlows


class CoreHRFlows(HRFlows):
    def activate(self):
        self.setup_admin()
        self.server.product_profile = 'core-hr'

    def test_profile_blocks_disabled_routes_even_for_hr_and_replays(self):
        self.setup_admin()
        key = 'fictional-idempotency-key-123'
        body = {'title': 'Private broader-module goal', 'due_date': '2026-12-31'}
        self.assertEqual(self.request('POST', '/api/goals', body, extra={'Idempotency-Key': key})[0], 201)
        self.server.product_profile = 'core-hr'
        for method, path, data in [('POST', '/api/goals', body), ('GET', '/api/payroll', None), ('POST', '/api/pay_runs', {}), ('GET', '/api/statutory', None), ('POST', '/api/legal_entities', {}), ('POST', '/api/benefit_enrollments', {}), ('POST', '/api/courses', {}), ('PATCH', '/api/expenses/1', {}), ('GET', '/api/pay_groups', None)]:
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, data, extra={'Idempotency-Key': key})[0], 404)
        self.assertEqual(self.request('POST', '/api/goals', body, extra={'Idempotency-Key': key})[0], 404)

    def test_profile_projects_state_and_catalog_without_removing_stored_records(self):
        self.activate()
        state = self.request('GET', '/api/state')[1]
        self.assertEqual(state['product']['profile'], 'core-hr')
        self.assertNotIn('payruns', state['product']['pages'])
        for key in ('goals', 'expenses', 'candidates', 'benefit_plans', 'courses', 'pay_runs', 'payroll_access', 'payslips', 'legal_entities', 'filing_packets', 'pay_groups'):
            self.assertEqual(state[key], [], key)
        self.assertNotIn('expenses_policy', state['policies'])
        self.assertEqual(self.request('GET', '/api/countries')[1]['payroll_capabilities'], {})
        self.server.product_profile = 'full'
        self.assertTrue(self.request('GET', '/api/state')[1]['candidates'])

    def test_core_workflows_keep_permissions_and_stale_edit_protection(self):
        self.activate()
        worker = self.add_employee()
        row = next(e for e in self.request('GET', '/api/state')[1]['employees'] if e['id'] == worker)
        self.assertEqual(self.request('PATCH', f'/api/employees/{worker}', {'title': 'Senior analyst', 'expected_version': row['version']})[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/employees/{worker}', {'title': 'Stale edit', 'expected_version': row['version']})[0], 409)
        self.login('person@example.org', 'EmployeePass123!')
        self.assertEqual(self.request('POST', '/api/employees', {})[0], 403)
        self.assertNotIn('annual_salary', self.request('GET', '/api/state')[1]['employees'][0])
        self.assertEqual(self.request('GET', '/api/operations')[0], 403)

    def test_reports_and_role_and_policy_inputs_cannot_bypass_scope(self):
        self.activate()
        worker = self.add_employee()
        for entity in ('expenses', 'benefit_enrollments'):
            self.assertEqual(self.request('GET', '/api/reports?entity=' + entity)[0], 404)
        self.assertEqual(self.request('GET', '/api/reports?entity=employees')[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/employees/{worker}', {'role': 'payroll'})[0], 400)
        self.assertEqual(self.request('POST', '/api/policies', {'expenses_policy': 'hr_only'})[0], 400)

    def test_profile_is_visible_before_login_and_cannot_be_changed_over_http(self):
        self.server.product_profile = 'core-hr'
        self.assertEqual(self.request('GET', '/api/session')[1]['product']['profile'], 'core-hr')
        self.assertEqual(self.request('POST', '/api/setup', {'name': 'Fictional HR', 'email': 'hr@example.org', 'password': 'FictionalPassword123!', 'include_samples': True})[0], 400)
        self.assertEqual(self.request('POST', '/api/profile', {'profile': 'full'})[0], 401)


class CoreAcceptanceTests(unittest.TestCase):
    def test_reference_and_recovery_verify_records_anchor_and_removed_credentials(self):
        from core_acceptance import capture_reference, recover_and_check
        from server import HRStore
        from provisioning import initialize_administrator
        from identity import totp
        from backup import create_backup
        from contextlib import closing
        import base64
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = HRStore(root / 'source/workspace.db')
            secret = base64.b32encode(b'01234567890123456789').decode()
            initialize_administrator(store, 'Fictional HR', 'admin@openpeople.invalid', 'FictionalPassword123!', secret, totp(secret), 'IN')
            reference = capture_reference(store.db_path)
            before = Path(store.db_path).read_bytes()
            archive = create_backup(store.db_path, root / 'downloads', 'Fictional recovery phrase 123!')
            Path(store.db_path).parent.rename(root / 'unavailable-source')
            result = recover_and_check(archive, root / 'recovered', 'Fictional recovery phrase 123!', reference, 60)
            self.assertTrue(result['passed'], result)
            self.assertFalse(result['off_device_recovery_verified'])
            self.assertTrue(result['checks']['independent_reference_matches'])
            self.assertTrue(result['checks']['reusable_credentials_removed'])
            self.assertEqual((root / 'unavailable-source/workspace.db').read_bytes(), before)
            self.assertNotIn(secret, json.dumps(result))
            with closing(sqlite3.connect(root / 'recovered/workspace.db')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM employees').fetchone()[0], 1)
            bad = json.loads(json.dumps(reference)); bad['data_digest'] = '0' * 64
            self.assertFalse(recover_and_check(archive, root / 'mismatched', 'Fictional recovery phrase 123!', bad, 60)['passed'])
            with self.assertRaises(ValueError):recover_and_check(archive, root / 'recovered', 'Fictional recovery phrase 123!', reference, 60)
            with self.assertRaises(ValueError):recover_and_check(archive, root / 'bad-password', 'Incorrect phrase 123!', reference, 60)
            self.assertFalse((root / 'bad-password').exists())

    def test_private_evidence_refuses_overwrite_and_recovery_rejects_bad_reference(self):
        from core_acceptance import write_evidence, recover_and_check
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'evidence.json'
            write_evidence(target, {'passed': False})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):write_evidence(target, {'passed': True})
            self.assertFalse(json.loads(target.read_text())['passed'])
            for reference in ({}, {'format': 'made-up'}, {'format': 'openpeople.core-reference.v1', 'data_digest': 'bad'}):
                with self.assertRaises(ValueError):recover_and_check(Path(folder) / 'missing.opbackup', Path(folder) / 'untouched', 'Private phrase 123!', reference, 60)
                self.assertFalse((Path(folder) / 'untouched').exists())

    def test_profile_and_recovery_inputs_fail_before_writing_a_workspace(self):
        from server import HRStore
        from core_acceptance import recover_and_check
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):HRStore(root / 'absent/workspace.db', product_profile='made-up')
            self.assertFalse((root / 'absent').exists())
            reference = {'format':'openpeople.core-reference.v1','schema':9,'data_digest':'0'*64,
                         'audit_anchor':{'format':'openpeople.audit-anchor.v1','chains':{
                             key:{'count':0,'last_id':0,'digest':'0'*64} for key in ('audit','security_events')}}}
            for objective in (False, 0, float('nan'), float('inf'), 86401):
                with self.assertRaises(ValueError):recover_and_check(root / 'absent', root / 'restored', 'Private phrase 123!', reference, objective)
                self.assertFalse((root / 'restored').exists())

    def test_recovery_detects_a_mismatched_workspace_key_and_cli_refuses_noninteractive_secrets(self):
        from core_acceptance import capture_reference, recover_and_check, write_evidence
        from server import HRStore
        from provisioning import initialize_administrator
        from identity import totp
        from backup import create_backup
        from cryptography.fernet import Fernet
        from unittest.mock import patch
        import base64
        import contextlib
        import io
        from scripts.accept_core_hr import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);store = HRStore(root / 'source/workspace.db')
            secret = base64.b32encode(b'01234567890123456789').decode()
            initialize_administrator(store,'Fictional HR','admin@openpeople.invalid','FictionalPassword123!',secret,totp(secret),'IN')
            reference = capture_reference(store.db_path)
            reference_file = root / 'reference.json';write_evidence(reference_file, reference)
            phrase = 'Fictional recovery phrase 123!'
            archive = create_backup(store.db_path, root / 'download', phrase)
            args = ['accept_core_hr.py','recovery','--archive',str(archive),'--reference',str(reference_file),'--destination',str(root / 'cli-restored'),'--output',str(root / 'cli-result.json')]
            with patch('sys.argv',args),patch('sys.stdin.isatty',return_value=False),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main()
            self.assertFalse((root / 'cli-restored').exists())
            output = io.StringIO()
            with patch('sys.argv',args),patch('sys.stdin.isatty',return_value=True),patch('sys.stderr.isatty',return_value=True),patch('getpass.getpass',return_value=phrase),contextlib.redirect_stdout(output):
                self.assertEqual(main(),0)
            self.assertNotIn(phrase,output.getvalue());self.assertNotIn(secret,output.getvalue())
            self.assertFalse(json.loads((root / 'cli-result.json').read_text())['production_approved'])
            Path(store.db_path).with_suffix('.key').write_bytes(Fernet.generate_key())
            mismatched = create_backup(store.db_path,root / 'download',phrase)
            result = recover_and_check(mismatched,root / 'wrong-key',phrase,reference,60)
            self.assertTrue(result['checks']['independent_reference_matches'])
            self.assertFalse(result['checks']['authenticator_secrets_decryptable'])
            self.assertFalse(result['passed'])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([*(CoreHRFlows(name) for name in CoreHRFlows.__dict__ if name.startswith('test_')), loader.loadTestsFromTestCase(CoreAcceptanceTests)])
