import json
import unittest

from test_app import HRFlows


class ExternalPayrollFlows(HRFlows):
    def fixture(self):
        self.setup_admin()
        employee = self.add_employee()
        status, reviewer = self.request('POST', '/api/employees', {'name': 'Independent reviewer', 'email': 'reviewer@example.org', 'title': 'Payroll', 'department': 'Finance', 'location': 'Remote', 'annual_salary': 600000, 'start_date': '2026-10-01', 'role': 'payroll', 'password': 'ReviewerPassword123!'})
        self.assertEqual(status, 201)
        run = self.request('POST', '/api/pay_runs', {'month': '2026-10'})[1]['id']
        details = self.request('GET', f'/api/pay_runs/{run}')[1]
        row = next(item for item in details['rows'] if item['employee_id'] == employee)
        result = {**row['external_template'], 'provider': 'Fictional reviewed payroll', 'reference': 'FICT-2026-10-001', 'rules_effective_date': '2026-10-01', 'review_note': 'Compared with independently reviewed provider statement', 'earnings': [{'label': 'Basic pay', 'amount_minor': 4500000}, {'label': 'Allowance', 'amount_minor': 500000}], 'deductions': [{'label': 'Tax', 'amount_minor': 900000}, {'label': 'Employee pension', 'amount_minor': 100000}], 'employer_contributions': [{'label': 'Employer pension', 'amount_minor': 200000}], 'net_minor': 4000000}
        return run, row, result

    def test_external_result_retains_provenance_and_peer_approval(self):
        run, row, result = self.fixture()
        payload = {'expected_version': 1, 'external_result': result}
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', payload)[0], 200)
        details = self.request('GET', f'/api/pay_runs/{run}')[1]
        saved = next(item for item in details['rows'] if item['id'] == row['id'])
        provenance = json.loads(saved['external_result'])
        self.assertEqual((saved['gross_paise'], saved['deductions_paise'], details['run']['version']), (5000000, 1000000, 2))
        self.assertEqual(provenance['employer_contributions'][0]['amount_minor'], 200000)
        self.assertEqual(provenance['reference'], result['reference'])
        self.assertEqual(json.loads(saved['calculation'])['source'], 'external')
        self.assertEqual(set(saved['external_template']), set(result))
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {'deductions_paise': 0, 'deduction_note': ''})[0], 409)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', payload)[0], 409)
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 403)
        self.login('reviewer@example.org', 'ReviewerPassword123!')
        self.assertEqual(self.request('PATCH', f'/api/pay_runs/{run}', {'status': 'Finalized'})[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {'expected_version': 3, 'external_result': result})[0], 409)
        self.login('person@example.org', 'EmployeePass123!')
        payslips = self.request('GET', '/api/state')[1]['payslips']
        self.assertEqual(len(payslips), 1)
        self.assertEqual(json.loads(payslips[0]['external_result'])['reference'], result['reference'])
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', payload)[0], 403)

    def test_import_validation_is_atomic_and_requires_fresh_review(self):
        run, row, result = self.fixture()
        def submit(value, expected=1):
            return self.request('PATCH', f'/api/pay_results/{row["id"]}', {'expected_version': expected, 'external_result': value}, version=False)[0]
        variants = [None, [], {**result, 'unverified_claim': 'compliant'}, {**result, 'format': 'unknown'}, {**result, 'employee_id': True}, {**result, 'currency': 'USD'}, {**result, 'month': '2026-09'}, {**result, 'country': 'US'}, {**result, 'reference': ''}, {**result, 'rules_effective_date': 'invalid'}, {**result, 'net_minor': 3999999}, {**result, 'net_minor': True}, {**result, 'earnings': []}, {**result, 'earnings': [{'label': 'Too much', 'amount_minor': 9000000000001}]}, {**result, 'deductions': [{'label': 'Negative', 'amount_minor': -1}]}, {**result, 'earnings': [{'label': 'Boolean', 'amount_minor': True}]}, {**result, 'earnings': [{'label': 'Fractional', 'amount_minor': 1.5}]}, {**result, 'earnings': [{'label': 'Invalid', 'amount_minor': 1, 'secret': 'no'}]}]
        for invalid in variants:
            with self.subTest(value=invalid):
                self.assertEqual(submit(invalid), 400)
        self.assertEqual(submit(result, expected=99), 409)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {'external_result': result}, version=False)[0], 428)
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{row["id"]}', {'external_result': result, 'expected_version': 1, 'deductions_paise': 0}, version=False)[0], 400)
        details = self.request('GET', f'/api/pay_runs/{run}')[1]
        self.assertEqual(details['run']['version'], 1)
        self.assertFalse(next(item for item in details['rows'] if item['id'] == row['id'])['external_result'])
        own = next(item for item in details['rows'] if item['employee_id'] == details['run']['created_by'])
        self.assertIsNone(own['external_template'])
        self.assertEqual(self.request('PATCH', f'/api/pay_results/{own["id"]}', {'external_result': result})[0], 403)

    def test_all_documented_native_countries_have_truthful_capabilities(self):
        catalog = self.request('GET', '/api/countries')[1]['payroll_capabilities']
        self.assertEqual({row['code'] for row in catalog['countries']}, {'AU', 'CA', 'FR', 'IE', 'GB', 'US'})
        self.assertFalse(catalog['automatic_statutory_supported'])
        self.assertFalse(catalog['government_filing_supported'])
        self.assertEqual(catalog['available_modes'], ['manual_review', 'external_results'])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(ExternalPayrollFlows(name) for name in ExternalPayrollFlows.__dict__ if name.startswith('test_'))
