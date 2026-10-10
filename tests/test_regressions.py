"""Regression checks for the eight reproduced audit findings."""
import hashlib
import socket
import time
from unittest.mock import patch
import unittest

from test_app import HRFlows


class Regressions(HRFlows):
    def test_invalid_security_headers_return_client_error(self):
        body={'name':'Owner','email':'owner@example.org','password':'OwnerPassword123!','include_samples':False}
        self.assertEqual(self.request('POST','/api/setup',body,extra={'X-Setup-Token':'ÿ'})[0],403)
        self.setup_admin()
        self.assertEqual(self.request('POST','/api/goals',{'title':'Safe','due_date':'2026-12-31'},extra={'X-CSRF-Token':'ÿ'})[0],403)

    def test_stalled_body_does_not_hold_write_lock(self):
        self.setup_admin()
        self.server.request_timeout = 0.5
        stalled = socket.create_connection(('127.0.0.1', self.server.server_port))
        try:
            stalled.sendall(f'POST /api/login HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\nContent-Length: 1000\r\nContent-Type: application/json\r\n\r\n{{'.encode())
            time.sleep(0.08)
            started = time.monotonic()
            self.assertEqual(self.request('POST', '/api/goals', {'title': 'Not blocked', 'due_date': '2026-12-31'})[0], 201)
            self.assertLess(time.monotonic() - started, 2)
            stalled.settimeout(2)
            self.assertIn(b'408', stalled.recv(2048))
        finally:
            stalled.close()

    def test_host_and_bootstrap_proof(self):
        self.assertEqual(self.request('GET', '/api/session', extra={'Host': 'untrusted.example'})[0], 403)
        setup = {'name': 'Owner', 'email': 'owner@example.org', 'password': 'OwnerPassword123!', 'include_samples': False}
        self.assertEqual(self.request('POST', '/api/setup', setup, extra={'X-Setup-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', '/api/setup', setup, extra={'X-Setup-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/api/setup', setup)[0], 201)
        self.assertEqual(self.request('POST', '/api/setup', setup)[0], 409)

    def test_reactivation_requires_fresh_login(self):
        self.setup_admin()
        employee = self.add_employee()
        self.login('person@example.org', 'EmployeePass123!')
        old_cookie = self.cookie
        self.login()
        self.assertEqual(self.request('PATCH', f'/api/employees/{employee}', {'status': 'Inactive'})[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/employees/{employee}', {'status': 'Active'})[0], 200)
        self.cookie = old_cookie
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.login('person@example.org', 'EmployeePass123!')

    def test_idempotency_replay_and_payload_conflict(self):
        self.setup_admin()
        expense = {'description': 'One expense', 'amount': 10, 'category': 'Travel', 'expense_date': '2026-10-09'}
        headers = {'Idempotency-Key': 'test-submission-unique-0001'}
        first = self.request('POST', '/api/expenses', expense, extra=headers)
        second = self.request('POST', '/api/expenses', expense, extra=headers)
        self.assertEqual(first, second)
        self.assertEqual(len(self.request('GET', '/api/state')[1]['expenses']), 2)  # one seeded, one new
        self.assertEqual(self.request('POST', '/api/expenses', {**expense, 'amount': 11}, extra=headers)[0], 409)

    def test_one_password_verification_for_known_and_unknown_accounts(self):
        self.setup_admin()
        for email in ['admin@example.org', 'missing@example.org']:
            with patch('server.hashlib.pbkdf2_hmac', wraps=hashlib.pbkdf2_hmac) as derive:
                self.assertEqual(self.request('POST', '/api/login', {'email': email, 'password': 'WrongPassword123!'})[0], 401)
                self.assertEqual(derive.call_count, 1)

    def test_independent_approver_and_role_provisioning(self):
        self.setup_admin()
        expense = {'description': 'Admin expense', 'amount': 10, 'category': 'Travel', 'expense_date': '2026-10-09'}
        own = self.request('POST', '/api/expenses', expense)[1]['id']
        self.assertEqual(self.request('PATCH', f'/api/expenses/{own}', {'status': 'Approved'})[0], 403)
        reviewer = {'name': 'Other HR', 'email': 'reviewer@example.org', 'title': 'HR', 'department': 'People', 'location': 'Mumbai', 'annual_salary': 0, 'start_date': '2026-10-01', 'role': 'hr', 'password': 'ReviewerPassword123!'}
        self.assertEqual(self.request('POST', '/api/employees', reviewer)[0], 201)
        self.login('reviewer@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/expenses/{own}', {'status': 'Approved'})[0], 200)

    def test_bad_identifiers_and_surrogates_are_client_errors(self):
        self.setup_admin()
        self.assertEqual(self.request('POST', '/api/goals', {'employee_id': 10**40, 'title': 'Invalid', 'due_date': '2026-12-31'})[0], 400)
        self.assertEqual(self.request('PATCH', '/api/goals/' + '9'*40, {'progress': 1})[0], 400)
        self.assertEqual(self.request('POST', '/api/candidates', {'name': '\ud800', 'email': 'unicode@example.org', 'position': 'Analyst', 'stage': 'Applied'})[0], 400)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Regressions(name) for name in Regressions.__dict__ if name.startswith('test_'))
