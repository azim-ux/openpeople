"""Regression checks for payroll maker/checker and provider isolation boundaries."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_app import HRFlows
from server import HRStore
from serving import create_hardened_server
from workspace import migrate


class PayrollBoundaries(HRFlows):
    def colleague(self, email, role='payroll'):
        status, result = self.request('POST', '/api/employees', {'name': email.split('@')[0], 'email': email, 'title': 'Reviewer', 'department': 'Finance', 'location': 'Remote', 'annual_salary': 600000, 'start_date': '2026-10-01', 'role': role, 'password': 'ReviewerPassword123!'})
        self.assertEqual(status, 201)
        return result['id']

    def test_self_edit_and_every_editor_are_excluded_from_final_approval(self):
        self.setup_admin()
        owner = self.add_employee()
        reviewer = self.colleague('reviewer@example.org')
        self.colleague('independent@example.org')
        run = self.request('POST', '/api/pay_runs', {'month': '2026-10'})[1]['id']
        rows = self.request('GET', f'/api/pay_runs/{run}')[1]['rows']
        own = next(row for row in rows if row['employee_id'] == reviewer)
        other = next(row for row in rows if row['employee_id'] == owner)
        self.login('reviewer@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{own["id"]}', {'deductions_paise': 0, 'deduction_note': ''})[0], 403)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{other["id"]}', {'deductions_paise': 100000, 'deduction_note': 'Reviewed deduction'})[0], 200)
        self.assertFalse(self.request('GET', f'/api/pay_runs/{run}')[1]['can_finalize'])
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 403)
        self.login()
        # A later edit by the creator must not erase the earlier editor.
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{other["id"]}', {'deductions_paise': 200000, 'deduction_note': 'Second correction'})[0], 200)
        self.login('reviewer@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 403)
        self.login('independent@example.org', 'ReviewerPassword123!')
        self.assertTrue(self.request('GET', f'/api/pay_runs/{run}')[1]['can_finalize'])
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{other["id"]}', {'deductions_paise': 0, 'deduction_note': ''})[0], 409)

    def test_stale_edit_and_finalization_require_the_reviewed_version(self):
        self.setup_admin()
        owner = self.add_employee()
        self.colleague('reviewer@example.org')
        run = self.request('POST', '/api/pay_runs', {'month': '2026-10'})[1]['id']
        snapshot = self.request('GET', f'/api/pay_runs/{run}')[1]
        row = next(row for row in snapshot['rows'] if row['employee_id'] == owner)
        payload = {'deductions_paise': 100000, 'deduction_note': 'Reviewed deduction'}
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', payload, version=False)[0], 428)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {**payload, 'expected_version': snapshot['run']['version']})[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {**payload, 'deductions_paise': 0, 'expected_version': snapshot['run']['version']})[0], 409)
        self.login('reviewer@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'}, version=False)[0], 428)
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized', 'expected_version': snapshot['run']['version']})[0], 409)
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 200)
        result = self.request('GET', f'/api/pay_runs/{run}')[1]
        self.assertEqual(next(r for r in result['rows'] if r['id'] == row['id'])['deductions_paise'], 100000)

    def test_schema_upgrade_keeps_legacy_draft_editor_history(self):
        self.setup_admin()
        owner = self.add_employee()
        editor = self.colleague('editor@example.org')
        run = self.request('POST', '/api/pay_runs', {'month': '2026-10'})[1]['id']
        row = next(r for r in self.request('GET', f'/api/pay_runs/{run}')[1]['rows'] if r['employee_id'] == owner)
        db = self.server.connect()
        try:
            with db:
                # Fictional schema-3 fixture: an edit predating the editor table.
                db.execute('DROP TABLE pay_run_editors')
                db.execute('PRAGMA user_version=3')
                db.execute("INSERT INTO audit(actor_id,action,entity,entity_id,created_at,details) VALUES(?,'Updated','pay_results',?,'2026-10-09T00:00:00Z','{}')", (editor, row['id']))
                migrate(db)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 9)
            self.assertIsNotNone(db.execute('SELECT 1 FROM pay_run_editors WHERE run_id=? AND employee_id=?', (run, editor)).fetchone())
        finally:
            db.close()
        self.login('editor@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 403)


class ProviderIsolation(unittest.TestCase):
    def test_slow_provider_keeps_reads_and_writes_available_and_releases_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = HRStore(Path(temporary) / 'private/workspace.db', port=0)
            server = create_hardened_server(store, port=0)
            port = int(server.effective_port)
            store.server_port = port
            store.allowed_hosts = {f'127.0.0.1:{port}'}
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            def call(path, method='GET', data=None, cookie='', csrf=''):
                client = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    client.request(method, path, json.dumps(data) if data is not None else None, {'Content-Type': 'application/json', 'Connection': 'close', 'Cookie': cookie, 'X-CSRF-Token': csrf, 'X-Setup-Token': store.bootstrap_token})
                    response = client.getresponse()
                    return response.status, json.loads(response.read()), response.getheader('Set-Cookie', '').split(';')[0]
                finally:
                    client.close()
            waiting, release = threading.Event(), threading.Event()
            counter_lock = threading.Lock()
            count = 0
            metadata = {'issuer': 'https://idp.example', 'authorization_endpoint': 'https://idp.example/auth', 'token_endpoint': 'https://idp.example/token', 'jwks_uri': 'https://idp.example/keys'}
            def delayed_provider(*args, **kwargs):
                nonlocal count
                with counter_lock:
                    count += 1
                    if count == 2:
                        waiting.set()
                if not release.wait(5):
                    raise TimeoutError('Bounded fictional provider fixture')
                return type('Response', (), {'raise_for_status': lambda self: None, 'json': lambda self: metadata})()
            try:
                setup = call('/api/setup', 'POST', {'name': 'HR', 'email': 'hr@example.org', 'password': 'FictionalPassword123!', 'include_samples': False})
                self.assertEqual(setup[0], 201)
                cookie, csrf = setup[2], setup[1]['csrf']
                with patch.dict(os.environ, {'OPENPEOPLE_OIDC_ISSUER': metadata['issuer'], 'OPENPEOPLE_OIDC_CLIENT_ID': 'fictional'}), patch('identity.requests.get', side_effect=delayed_provider), ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(call, '/api/sso/start') for _ in range(2)]
                    try:
                        self.assertTrue(waiting.wait(2))
                        self.assertEqual(call('/api/sso/start')[0], 503)
                        self.assertEqual(call('/api/sso/callback?state=invalid')[0], 503)
                        self.assertEqual(call('/api/state', cookie=cookie)[0], 200)
                        self.assertEqual(call('/api/goals', 'POST', {'title': 'Work continues during provider delay', 'due_date': '2026-12-31'}, cookie, csrf)[0], 201)
                    finally:
                        release.set()
                    self.assertEqual([future.result(timeout=3)[0] for future in futures], [200, 200])
                    self.assertEqual(call('/api/sso/callback?state=invalid')[0], 401)
                    self.assertEqual(call('/api/sso/start')[0], 200)
            finally:
                release.set()
                server.task_dispatcher.shutdown()
                server.close()
                thread.join(timeout=3)

    def test_small_worker_pool_reserves_at_least_one_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = HRStore(Path(temporary) / 'private/workspace.db', port=0)
            with self.assertRaises(ValueError):
                create_hardened_server(store, port=0, threads=1)
            server = create_hardened_server(store, port=0, threads=2)
            try:
                self.assertTrue(store.sso_slots.acquire(blocking=False))
                self.assertFalse(store.sso_slots.acquire(blocking=False))
                store.sso_slots.release()
            finally:
                server.task_dispatcher.shutdown()
                server.close()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([*(PayrollBoundaries(name) for name in PayrollBoundaries.__dict__ if name.startswith('test_')), *loader.loadTestsFromTestCase(ProviderIsolation)])
