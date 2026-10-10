import unittest
from test_app import HRFlows


class TeamFlows(HRFlows):
    def test_specialist_roles_do_not_gain_hr_permissions(self):
        self.setup_admin()
        employee=self.add_employee()
        for role in ('recruiter','payroll','auditor'):
            self.request('PATCH',f'/api/employees/{employee}',{'role':role})
            self.login('person@example.org','EmployeePass123!')
            state=self.request('GET','/api/state')[1]
            self.assertEqual(self.request('POST','/api/policies',{})[0],403)
            self.assertEqual(self.request('GET','/api/backup/status')[0],403)
            self.assertEqual(self.request('POST','/api/employees',{})[0],403)
            self.assertEqual('annual_salary' in state['employees'][0],role=='payroll')
            self.assertEqual(bool(state['security_events']),role=='auditor')
            candidate=self.request('POST','/api/candidates',{'name':'Applicant','email':role+'@example.org','position':'Analyst','stage':'Applied'})[0]
            self.assertEqual(candidate,201 if role=='recruiter' else 403)
            self.assertEqual(self.request('GET','/api/payroll?month=2026-10')[0],200 if role=='payroll' else 403)
            self.login()

    def test_hr_manager_and_unavailable_manager_approval(self):
        self.setup_admin()
        admin=self.request('GET','/api/state')[1]['user']['id']
        employee=self.add_employee()
        self.request('PATCH',f'/api/employees/{employee}',{'manager_id':admin})
        self.request('POST','/api/policies',{'leave_policy':'manager_then_hr'})
        request=self.request('POST','/api/leave',{'employee_id':employee,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Break'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],403)
        reviewer=self.request('POST','/api/employees',{'name':'Other HR','email':'other@example.org','title':'HR','department':'People','location':'Remote','annual_salary':0,'start_date':'2026-10-01','role':'hr','password':'ReviewerPassword123!'})[1]['id']
        self.login('other@example.org','ReviewerPassword123!')
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],200)
        second=self.request('POST','/api/leave',{'employee_id':employee,'type':'Annual','start_date':'2026-12-02','end_date':'2026-12-03','reason':'Break'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/employees/{admin}',{'status':'Inactive'})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/leave/{second}',{'status':'Approved'})[0],200)

    def test_manager_scope_and_two_stage_approval(self):
        self.setup_admin()
        manager = self.request('POST','/api/employees',{'name':'Team manager','email':'manager@example.org','title':'Manager','department':'Engineering','location':'Remote','annual_salary':0,'start_date':'2026-10-01','role':'manager','password':'ManagerPassword123!'})[1]['id']
        employee = self.add_employee()
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'manager_id':manager})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/employees/{manager}',{'manager_id':manager})[0],400)
        self.assertEqual(self.request('POST','/api/policies',{'leave_policy':'manager_then_hr'})[0],200)
        request = self.request('POST','/api/leave',{'employee_id':employee,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Break'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],403)
        self.login('manager@example.org','ManagerPassword123!')
        self.assertEqual(self.request('POST','/api/employees',{})[0],403)
        self.assertEqual(self.request('PATCH','/api/leave/1',{'status':'Approved'})[0],403)
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],200)
        row = next(r for r in self.request('GET','/api/state')[1]['leave'] if r['id']==request)
        self.assertEqual(row['status'],'Pending')
        self.assertEqual(row['manager_reviewed_by'],manager)
        self.login()
        self.assertEqual(self.request('PATCH',f'/api/leave/{request}',{'status':'Approved'})[0],200)

    def test_benefits_learning_notifications_and_audit(self):
        self.setup_admin()
        employee = self.add_employee()
        plan = self.request('POST','/api/benefit_plans',{'title':'Health plan','description':'Voluntary health benefit','monthly_cost_paise':25000})[1]['id']
        course = self.request('POST','/api/courses',{'title':'Safety training','description':'Read the safety handbook','url':'https://example.org/training'})[1]['id']
        self.assertEqual(self.request('POST','/api/courses',{'title':'Bad','description':'Bad URL','url':'javascript:alert(1)'})[0],400)
        assignment = self.request('POST','/api/course_assignments',{'employee_id':employee,'course_id':course,'due_date':'2026-12-31'})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{})[0],403)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':650000})[0],200)
        state = self.request('GET','/api/state')[1]
        self.assertTrue(any(r['action']=='Login succeeded' or r['action']=='Workspace initialized' for r in state['security_events']))
        self.assertTrue(any('650000' in r['details'] and '600000' in r['details'] for r in state['audit']))
        self.assertTrue(all('password' not in r['details'] for r in state['audit']))
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('POST','/api/benefit_enrollments',{'plan_id':plan})[0],201)
        self.assertEqual(self.request('POST','/api/benefit_enrollments',{'plan_id':plan})[0],409)
        self.assertEqual(self.request('POST','/api/courses',{})[0],403)
        self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/course_assignments/{assignment}',{})[0],409)
        state = self.request('GET','/api/state')[1]
        self.assertEqual(state['security_events'],[])
        self.assertEqual(len(state['notifications']),1)
        note = state['notifications'][0]['id']
        revision=state['revision']
        self.assertEqual(self.request('PATCH',f'/api/notifications/{note}',{})[0],200)
        self.assertGreater(self.request('GET','/api/changes')[1]['revision'],revision)

    def test_finalized_payroll_is_immutable_and_scoped(self):
        self.setup_admin()
        employee = self.add_employee()
        run = self.request('POST','/api/pay_runs',{'month':'2026-10'})[1]['id']
        rows = self.request('GET',f'/api/pay_runs/{run}')[1]['rows']
        item = next(r for r in rows if r['employee_id']==employee)
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{item["id"]}',{'deductions_paise':100000,'deduction_note':'Manually checked deduction'})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{item["id"]}',{'deductions_paise':10**10,'deduction_note':'Too much'})[0],400)
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],403)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'role':'payroll'})[0],200)
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{item["id"]}',{'deductions_paise':0,'deduction_note':''})[0],409)
        self.assertEqual(self.request('GET','/api/state')[1]['payslips'][0]['gross_paise'],5000000)
        self.login()
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':1200000})[0],200)
        self.assertEqual(next(r for r in self.request('GET',f'/api/pay_runs/{run}')[1]['rows'] if r['employee_id']==employee)['gross_paise'],5000000)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(TeamFlows(name) for name in TeamFlows.__dict__ if name.startswith('test_'))
