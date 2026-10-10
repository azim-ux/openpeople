import http.client
import json
from datetime import date, timedelta
from pathlib import Path
import unittest

from test_app import HRFlows
from manage import reset_password


class Boundaries(HRFlows):
    # Reuse the HTTP harness, without rerunning its test methods in this class.
    def test_empty_setup_and_recovery(self):
        status, result = self.request('POST', '/api/setup', {'name': 'Admin', 'email': 'owner@example.org', 'password': 'StrongPassword123!', 'include_samples': False})
        self.assertEqual(status, 201)
        self.csrf = result['csrf']
        state = self.request('GET', '/api/state')[1]
        self.assertEqual(len(state['employees']), 1)
        self.assertEqual(state['candidates'], [])
        self.assertEqual(self.request('PATCH', '/api/employees/1', {'status': 'Inactive'})[0], 400)
        db_path = Path(self.temp.name) / 'test.db'
        reset_password(db_path, 'owner@example.org', ' NewPassword123! ')
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.login('owner@example.org', ' NewPassword123! ')
        with self.assertRaises(ValueError):
            reset_password(db_path, 'missing@example.org', 'NewPassword123!')
        with self.assertRaises(ValueError):
            reset_password(db_path, 'owner@example.org', 'short')
        with self.assertRaises(ValueError):
            reset_password(Path(self.temp.name) / 'missing.db', 'owner@example.org', 'NewPassword123!')

    def test_private_records_and_deactivation(self):
        self.setup_admin()
        employee = self.add_employee()
        self.login('person@example.org', 'EmployeePass123!')
        state = self.request('GET', '/api/state')[1]
        self.assertTrue(all(t['employee_id'] == employee for t in state['tasks']))
        self.assertTrue(all(g['employee_id'] == employee for g in state['goals']))
        self.assertEqual(state['expenses'], [])
        self.assertEqual(state['leave'], [])
        self.assertEqual(state['audit'], [])
        self.assertTrue(all('password' not in e and 'csrf' not in e for e in state['employees']))
        self.assertEqual(self.request('PATCH', '/api/tasks/1', {'done': True})[0], 403)
        self.assertEqual(self.request('PATCH', '/api/goals/1', {'progress': 20})[0], 403)
        self.assertEqual(self.request('POST', '/api/goals', {'employee_id': 1, 'title': 'x', 'due_date': '2026-12-31'})[0], 403)
        employee_cookie = self.cookie
        self.login()
        self.assertEqual(self.request('PATCH', f'/api/employees/{employee}', {'status': 'Inactive'})[0], 200)
        self.cookie = employee_cookie
        self.assertEqual(self.request('GET', '/api/state')[0], 401)

    def test_validation_errors(self):
        self.setup_admin()
        self.assertEqual(self.request('PATCH', '/api/employees/1', {})[0], 400)
        self.assertEqual(self.request('PATCH', '/api/employees/1', {'annual_salary': -1})[0], 400)
        self.assertEqual(self.request('PATCH', '/api/tasks/1', {'done': 'true'})[0], 400)
        self.assertEqual(self.request('POST', '/api/goals', {'employee_id': '1', 'title': 'x', 'due_date': '2026-12-31'})[0], 400)
        self.assertEqual(self.request('POST', '/api/goals', {'employee_id': 9999, 'title': 'x', 'due_date': '2026-12-31'})[0], 400)
        self.assertEqual(self.request('POST', '/api/attendance', {'employee_id': 1, 'action': 'in'})[0], 403)
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'invalid'})[0], 400)
        saturday = date.today() + timedelta(days=(5-date.today().weekday())%7)
        leave = {'type': 'Annual', 'start_date': saturday.isoformat(), 'end_date': saturday.isoformat(), 'reason': 'Weekend'}
        self.assertEqual(self.request('POST', '/api/leave', leave)[0], 400)
        self.assertEqual(self.request('POST', '/api/leave', {**leave, 'end_date': '2000-01-01'})[0], 400)
        self.assertEqual(self.request('POST', '/api/leave', {**leave, 'start_date': '2026-02-30'})[0], 400)
        self.assertEqual(self.request('POST', '/api/candidates', {'name': 'X'*101, 'email':'x@example.org','position':'X','stage':'Applied'})[0], 400)
        expense = {'description':'Test', 'amount':12.345, 'category':'Travel', 'expense_date':'2026-10-09'}
        self.assertEqual(self.request('POST', '/api/expenses', expense)[0], 400)
        employee = self.add_employee()
        status, record = self.request('POST', '/api/expenses', {**expense,'amount':12.34,'employee_id':employee})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('PATCH', f"/api/expenses/{record['id']}", {'status':'Rejected'})[0], 200)
        self.assertEqual(self.request('PATCH', f"/api/expenses/{record['id']}", {'status':'Approved'})[0], 409)

    def test_malformed_json_and_rate_limit(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('POST', '/api/setup', '[1]', {'Content-Type':'application/json'})
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()
        for _ in range(9):
            self.request('POST', '/api/login', {'email':'bad','password':'x'})
        self.assertEqual(self.request('POST', '/api/login', {'email':'bad','password':'x'})[0], 429)


# Only collect tests declared here; avoid duplicating the base class's suite.
def load_tests(loader, tests, pattern):
    names = [name for name in Boundaries.__dict__ if name.startswith('test_')]
    return unittest.TestSuite(Boundaries(name) for name in names)
