"""Role-scoped operational and account lifecycle contracts."""
import hashlib
import json
import unittest
from test_app import HRFlows


class OperationalFlows(HRFlows):
    def test_session_inventory_and_revoke_do_not_expose_credentials(self):
        self.setup_admin();old_cookie=self.cookie;self.login()
        inventory=self.request('GET','/api/sessions');self.assertEqual(inventory[0],200)
        self.assertEqual(len(inventory[1]['rows']),2)
        self.assertNotIn('csrf',json.dumps(inventory[1]))
        self.assertNotIn(hashlib.sha256(old_cookie.split('=',1)[1].encode()).hexdigest(),json.dumps(inventory[1]))
        previous=next(row for row in inventory[1]['rows'] if not row['current'])
        self.assertEqual(self.request('PATCH','/api/sessions/'+previous['id'],{'revoke':True})[0],200)
        current_cookie=self.cookie;self.cookie=old_cookie
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.cookie=current_cookie
        self.assertEqual(self.request('GET','/api/state')[0],200)

    def test_account_throttle_persists_when_source_bucket_changes(self):
        self.setup_admin()
        for index in range(10):
            self.server.rates.clear()
            self.assertEqual(self.request('POST','/api/login',{'email':'hr@example.org','password':'Wrong password 123!'})[0],401)
        self.server.rates.clear()
        self.assertEqual(self.request('POST','/api/login',{'email':'hr@example.org','password':'AdminPassword123!'})[0],429)

    def test_audit_export_is_paginated_scoped_and_safe(self):
        self.setup_admin();employee=self.add_employee()
        first=self.request('GET','/api/audit/export?limit=2&offset=0')
        self.assertEqual(first[0],200);self.assertLessEqual(len(first[1]['changes']),2)
        self.assertNotIn('AdminPassword123!',json.dumps(first[1]))
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('GET','/api/audit/export')[0],403)

    def test_leave_allocation_requires_days_and_budget_applies(self):
        self.setup_admin();employee=self.add_employee()
        data={'employee_id':employee,'year':2026,'type':'Annual','reason':'Reviewed allocation'}
        self.assertEqual(self.request('POST','/api/leave_allocations',data)[0],400)
        self.assertEqual(self.request('POST','/api/leave_allocations',{**data,'days':1,'carryover':0.5})[0],201)
        self.assertEqual(self.request('POST','/api/leave',{'employee_id':employee,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Too much'})[0],400)

    def test_expense_receipt_policy_correction_cancel_and_reconcile(self):
        self.setup_admin();employee=self.add_employee()
        self.request('POST','/api/policies',{'expenses_limit_paise':500000,'receipt_required_above_paise':100000})
        self.login('person@example.org','EmployeePass123!')
        expense={'description':'Workshop','amount':1500,'category':'Travel','expense_date':'2026-10-09'}
        self.assertEqual(self.request('POST','/api/expenses',expense)[0],400)
        self.assertEqual(self.request('POST','/api/expenses',{**expense,'amount':6000,'receipt_reference':'Secure receipt ref'})[0],400)
        record=self.request('POST','/api/expenses',{**expense,'receipt_reference':'Secure receipt ref'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/expenses/{record}',{'description':'Correct workshop','reason':'Correction'})[0],200)
        self.login();self.request('PATCH',f'/api/expenses/{record}',{'status':'Approved'})
        self.assertEqual(self.request('PATCH',f'/api/expenses/{record}',{'reconciliation_reference':'Bank batch 123'})[0],200)
        row=next(row for row in self.request('GET','/api/state')[1]['expenses'] if row['id']==record)
        self.assertTrue(row['reconciled_on']);self.assertEqual(row['receipt_reference'],'Secure receipt ref')
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('PATCH',f'/api/expenses/{record}',{'status':'Cancelled','reason':'Cancel paid claim'})[0],409)

    def test_pending_leave_can_be_amended_and_restarts_approval(self):
        self.setup_admin();employee=self.add_employee();self.login('person@example.org','EmployeePass123!')
        record=self.request('POST','/api/leave',{'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Break'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/leave/{record}',{'start_date':'2026-11-04','end_date':'2026-11-04','half_day':True,'reason':'Changed plans'})[0],200)
        row=next(row for row in self.request('GET','/api/state')[1]['leave'] if row['id']==record)
        self.assertEqual(row['days'],0.5);self.assertIsNone(row['manager_reviewed_by'])

    def test_benefit_windows_and_scoped_roster_export(self):
        self.setup_admin();employee=self.add_employee()
        plan=self.request('POST','/api/benefit_plans',{'title':'Future enrollment','description':'Company window','monthly_cost_paise':0,'enrollment_opens':'2099-01-01','enrollment_closes':'2099-02-01'})[1]['id']
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('POST','/api/benefit_enrollments',{'plan_id':plan})[0],400)
        self.assertEqual(self.request('GET','/api/benefits/export')[0],403)
        self.login();self.assertEqual(self.request('GET','/api/benefits/export?limit=10')[0],200)

    def test_reports_are_paginated_and_samples_excluded(self):
        self.setup_admin();employee=self.add_employee()
        result=self.request('GET','/api/reports?entity=employees&start=2026-01-01&end=2026-12-31&limit=2')
        self.assertEqual(result[0],200)
        self.assertTrue(all(not row['is_sample'] for row in result[1]['rows']))
        self.assertEqual(result[1]['total'],2)
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('GET','/api/reports?entity=employees')[0],403)

    def test_learning_reminder_and_reassignment_are_hr_only(self):
        self.setup_admin();employee=self.add_employee()
        course=self.request('POST','/api/courses',{'title':'Training','description':'Annual training','url':''})[1]['id']
        assignment=self.request('POST','/api/course_assignments',{'employee_id':employee,'course_id':course,'due_date':'2026-10-01'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{'action':'remind'})[0],200)
        self.login('person@example.org','EmployeePass123!');self.request('PATCH',f'/api/course_assignments/{assignment}',{})
        self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{'action':'reassign','due_date':'2027-10-01','reason':'Annual refresh'})[0],403)
        self.login();self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{'action':'reassign','due_date':'2027-10-01','reason':'Annual refresh'})[0],200)
        row=next(row for row in self.request('GET','/api/state')[1]['course_assignments'] if row['id']==assignment)
        self.assertEqual(row['status'],'Assigned');self.assertIsNone(row['completed_at'])

    def test_expense_limits_use_the_selected_currency(self):
        self.setup_admin()
        worker=self.request('POST','/api/employees',{'name':'BHD worker','email':'bhd@example.org','country':'BH','title':'Analyst','department':'Global','location':'Local','annual_salary':1200000,'start_date':'2026-10-01','password':'EmployeePass123!'})[1]['id']
        self.assertEqual(self.request('POST','/api/policies',{'expense_policy_currency':'BHD','expenses_limit_paise':10000,'receipt_required_above_paise':1000})[0],200)
        self.login('bhd@example.org','EmployeePass123!')
        claim={'description':'Travel','amount':10.001,'category':'Travel','expense_date':'2026-10-09','receipt_reference':'Secure reference'}
        self.assertEqual(self.request('POST','/api/expenses',claim)[0],400)
        self.assertEqual(self.request('POST','/api/expenses',{**claim,'amount':10})[0],201)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(OperationalFlows(name) for name in OperationalFlows.__dict__ if name.startswith('test_'))
