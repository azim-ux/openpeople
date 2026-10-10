"""Adversarial validation and compensation-history edge cases."""
import unittest
from datetime import datetime
from unittest.mock import patch
from test_app import HRFlows

class SecurityFollowup(HRFlows):
    def test_malformed_country_and_export_identifiers_never_raise_500(self):
        self.setup_admin();employee=self.add_employee()
        for invalid in ([],{},None,True,12):
            self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'country':invalid})[0],400)
        for entity in ('benefit_enrollments','attendance_corrections','pay_runs','pay_results','course_assignments','notifications'):
            self.assertNotEqual(self.request('PATCH','/api/'+entity+'/'+str(2**63),{'status':'Approved'})[0],500)
        self.assertEqual(self.request('GET','/api/reports?entity=employees%3BDELETE%20FROM%20employees')[0],400)
        self.assertEqual(self.request('GET','/api/audit/export?limit=1000000000000000000000000')[0],400)
        self.assertEqual(self.request('POST','/api/policies',{'leave_limits':{'Annual':float('nan'),'Sick':12,'Personal':6}})[0],400)

    def test_future_salary_does_not_prevent_intentional_current_raise(self):
        self.setup_admin();employee=self.add_employee()
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':720000,'effective_date':'2027-01-01'})[0],200)
        row=next(e for e in self.request('GET','/api/state')[1]['employees'] if e['id']==employee)
        self.assertEqual(row['annual_salary'],600000)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':720000,'effective_date':'2026-10-09'})[0],200)
        row=next(e for e in self.request('GET','/api/state')[1]['employees'] if e['id']==employee)
        self.assertEqual(row['annual_salary'],720000)
        history=self.request('GET','/api/audit/export')[1]['changes']
        self.assertTrue(any(e['entity']=='compensation' for e in history))

    def test_pending_correction_cannot_overwrite_newer_checkout(self):
        self.setup_admin();self.add_employee();self.login('person@example.org','EmployeePass123!')
        with patch('server.datetime') as clock:
            clock.now.return_value=datetime.fromisoformat('2026-10-09T09:00:00+05:30')
            record=self.request('POST','/api/attendance',{'action':'in'})[1]['id']
            proposal=self.request('POST','/api/attendance_corrections',{'attendance_id':record,'expected_version':1,'check_in':'2026-10-09T09:00:00+05:30','check_out':'2026-10-09T17:00:00+05:30','break_minutes':30,'reason':'Forgot time'})
            self.assertEqual(proposal[0],201)
            clock.now.return_value=datetime.fromisoformat('2026-10-09T18:00:00+05:30')
            self.request('POST','/api/attendance',{'action':'out'})
        self.login()
        self.assertEqual(self.request('PATCH','/api/attendance_corrections/'+str(proposal[1]['id']),{'status':'Approved'})[0],409)
        row=next(r for r in self.request('GET','/api/state')[1]['attendance'] if r['id']==record)
        self.assertTrue(row['check_out'].startswith('2026-10-09T18:00:00'))


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(SecurityFollowup(name) for name in SecurityFollowup.__dict__ if name.startswith('test_'))
