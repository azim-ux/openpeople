import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from server import create_server, password_hash, password_matches


class HRFlows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server('127.0.0.1', 0, Path(self.temp.name) / 'test.db')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, body=None, csrf=True, origin=None, extra=None, version=True):
        # Older workflow tests supply a current precondition by default. Conflict
        # tests pass an explicit saved version or version=False to test rejection.
        if method=='PATCH' and path.startswith(('/api/employees/', '/api/pay_runs/', '/api/pay_results/')) and isinstance(body,dict) and version:
            try:
                employee=int(path.rsplit('/',1)[1])
                db=self.server.connect()
                if path.startswith('/api/employees/'):
                    row=db.execute('SELECT version FROM employees WHERE id=?',(employee,)).fetchone()
                elif path.startswith('/api/pay_runs/'):
                    row=db.execute('SELECT version FROM pay_runs WHERE id=?',(employee,)).fetchone()
                else:
                    row=db.execute('SELECT r.version FROM pay_runs r JOIN pay_results p ON p.run_id=r.id WHERE p.id=?',(employee,)).fetchone()
                db.close()
                if row:body={**body,'expected_version':body.get('expected_version',row['version'])}
            except (ValueError,OverflowError):pass
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json', 'Cookie': self.cookie}
        if path == '/api/setup':
            headers['X-Setup-Token'] = getattr(self.server, 'bootstrap_token', '')
        if csrf:
            headers['X-CSRF-Token'] = self.csrf
        if origin:
            headers['Origin'] = origin
        headers.update(extra or {})
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        cookie = response.getheader('Set-Cookie')
        if cookie:
            self.cookie = cookie.split(';')[0]
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw) if raw and 'application/json' in response.getheader('Content-Type', '') else raw

    def setup_admin(self):
        status, data = self.request('POST', '/api/setup', {'name': 'HR Admin', 'email': 'admin@example.org', 'password': 'TestPassword123!','include_samples':True})
        self.assertEqual(status, 201, data)
        self.csrf = data['csrf']
        return data

    def add_employee(self):
        status, data = self.request('POST', '/api/employees', {'name': 'Test Person', 'email': 'person@example.org', 'title': 'Analyst', 'department': 'Finance', 'location': 'Mumbai', 'annual_salary': 600000, 'start_date': '2026-10-01', 'password': 'EmployeePass123!'})
        self.assertEqual(status, 201, data)
        return data['id']

    def login(self, email='admin@example.org', password='TestPassword123!'):
        self.cookie = ''
        status, data = self.request('POST', '/api/login', {'email': email, 'password': password})
        self.assertEqual(status, 200, data)
        self.csrf = data['csrf']

    def test_password_hashing(self):
        hashed = password_hash('correct horse battery staple')
        self.assertTrue(password_matches('correct horse battery staple', hashed))
        self.assertFalse(password_matches('wrong', hashed))
        self.assertNotEqual(hashed, password_hash('correct horse battery staple'))
        self.assertFalse(password_matches('x', 'malformed'))

    def test_initial_setup_login_and_logout(self):
        self.assertTrue(self.request('GET', '/api/session')[1]['setup_required'])
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.assertEqual(self.request('POST', '/api/setup', {'name': 'X', 'email': 'bad', 'password': 'short'})[0], 400)
        self.setup_admin()
        self.assertEqual(self.request('POST', '/api/setup', {})[0], 409)
        self.assertEqual(self.request('GET', '/api/state')[1]['user']['role'], 'hr')
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.assertEqual(self.request('POST', '/api/login', {'email': 'admin@example.org', 'password': 'wrong'})[0], 401)
        self.login()
        self.assertFalse(self.request('GET', '/api/session')[1]['setup_required'])

    def test_employee_crud_and_permissions(self):
        self.setup_admin()
        employee = self.add_employee()
        self.assertEqual(self.request('POST', '/api/employees', {'name': 'X', 'email': 'person@example.org', 'title': 'A', 'department': 'D', 'location': 'L', 'annual_salary': 1, 'start_date': '2026-10-01'})[0], 409)
        self.assertEqual(self.request('PATCH', f'/api/employees/{employee}', {'title': 'Senior Analyst', 'status': 'Active'})[0], 200)
        self.login('person@example.org', 'EmployeePass123!')
        state = self.request('GET', '/api/state')[1]
        self.assertNotIn('annual_salary', state['employees'][0])
        self.assertEqual(state['candidates'], [])
        self.assertEqual(self.request('POST', '/api/employees', {})[0], 403)
        self.assertEqual(self.request('PATCH', f'/api/employees/{employee}', {'status': 'Inactive'})[0], 403)
        self.assertEqual(self.request('GET', '/api/payroll?month=2026-10')[0], 403)

    def test_leave_approval_and_overlap(self):
        self.setup_admin()
        employee = self.add_employee()
        self.login('person@example.org', 'EmployeePass123!')
        body = {'type': 'Annual', 'start_date': '2026-11-02', 'end_date': '2026-11-04', 'reason': 'Family trip'}
        status, leave = self.request('POST', '/api/leave', body)
        self.assertEqual(status, 201, leave)
        self.assertEqual(self.request('POST', '/api/leave', body)[0], 409)
        self.assertEqual(self.request('PATCH', f"/api/leave/{leave['id']}", {'status': 'Approved'})[0], 403)
        self.assertEqual(self.request('POST', '/api/leave', {**body, 'employee_id': 1, 'start_date': '2026-12-01', 'end_date': '2026-12-02'})[0], 403)
        self.login()
        self.assertEqual(self.request('PATCH', f"/api/leave/{leave['id']}", {'status': 'Approved'})[0], 200)
        self.assertEqual(self.request('PATCH', f"/api/leave/{leave['id']}", {'status': 'Rejected'})[0], 409)
        self.assertEqual(self.request('POST', '/api/leave', {**body, 'start_date': 'bad'})[0], 400)

    def test_attendance_and_goals(self):
        self.setup_admin()
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'out'})[0], 409)
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'in'})[0], 201)
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'in'})[0], 409)
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'out'})[0], 200)
        self.assertEqual(self.request('POST', '/api/attendance', {'action': 'out'})[0], 409)
        status, goal = self.request('POST', '/api/goals', {'title': 'Complete training', 'due_date': '2026-12-31'})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('PATCH', f"/api/goals/{goal['id']}", {'progress': 70})[0], 200)
        self.assertEqual(self.request('PATCH', f"/api/goals/{goal['id']}", {'progress': 101})[0], 400)

    def test_recruitment_onboarding_and_expenses(self):
        self.setup_admin()
        status, candidate = self.request('POST', '/api/candidates', {'name': 'Applicant', 'email': 'applicant@example.org', 'position': 'Engineer', 'stage': 'Applied'})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('PATCH', f"/api/candidates/{candidate['id']}", {'stage': 'Interview'})[0], 200)
        self.assertEqual(self.request('PATCH', f"/api/candidates/{candidate['id']}", {'stage': 'Invalid'})[0], 400)
        employee = self.add_employee()
        state = self.request('GET', '/api/state')[1]
        tasks = [t for t in state['tasks'] if t['employee_id'] == employee]
        self.assertEqual(len(tasks), 3)
        self.assertEqual(self.request('PATCH', f"/api/tasks/{tasks[0]['id']}", {'done': True})[0], 200)
        self.login('person@example.org', 'EmployeePass123!')
        status, expense = self.request('POST', '/api/expenses', {'description': 'Client meeting travel', 'amount': 1250, 'category': 'Travel', 'expense_date': '2026-10-09'})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('PATCH', f"/api/expenses/{expense['id']}", {'status': 'Approved'})[0], 403)
        self.login()
        self.assertEqual(self.request('PATCH', f"/api/expenses/{expense['id']}", {'status': 'Approved'})[0], 200)
        self.assertEqual(self.request('POST', '/api/expenses', {'amount': -1})[0], 400)

    def test_payroll_and_security_boundaries(self):
        self.setup_admin()
        self.add_employee()
        status, payroll = self.request('GET', '/api/payroll?month=2026-10')
        self.assertEqual(status, 200)
        row = next(r for r in payroll['rows'] if r['email'] == 'person@example.org')
        self.assertEqual(row['monthly_gross'], 50000)
        self.assertEqual(self.request('GET', '/api/payroll?month=invalid')[0], 400)
        self.assertEqual(self.request('POST', '/api/goals', {}, csrf=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/goals', {}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('PATCH', '/api/goals/9999', {'progress': 50})[0], 404)
        self.assertEqual(self.request('GET', '/api/nonexistent')[0], 404)
        self.assertEqual(self.request('GET', '/')[0], 200)
        self.assertEqual(self.request('GET', '/server.py')[0], 404)


if __name__ == '__main__':
    unittest.main()
