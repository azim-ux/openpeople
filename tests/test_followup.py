"""Regression contracts for the 0.2.0 follow-up audit; fictional workspaces only."""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import backup
from test_app import HRFlows


class FollowupFlows(HRFlows):
    def person_version(self, employee):
        return next(row['version'] for row in self.request('GET','/api/state')[1]['employees'] if row['id']==employee)

    def test_stale_employee_edit_is_rejected_and_precondition_required(self):
        self.setup_admin();employee=self.add_employee()
        row=next(row for row in self.request('GET','/api/state')[1]['employees'] if row['id']==employee)
        version=row.get('version',0)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':720000,'expected_version':version})[0],200)
        stale={key:row[key] for key in ('name','title','department','location','annual_salary','status','role','manager_id')}
        stale.update(location='Remote',expected_version=version)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',stale)[0],409)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'location':'Remote'},version=False)[0],428)
        saved=next(row for row in self.request('GET','/api/state')[1]['employees'] if row['id']==employee)
        self.assertEqual(saved['annual_salary'],720000)

    def test_passive_polling_does_not_renew_idle_session(self):
        self.setup_admin();base=time.time()
        for elapsed in (900,1700):
            with patch('server.time.time',return_value=base+elapsed):
                self.assertEqual(self.request('GET','/api/changes')[0],200)
        with patch('server.time.time',return_value=base+1801):
            self.assertEqual(self.request('GET','/api/state')[0],401)

    def test_intentional_activity_renews_idle_but_not_absolute_expiry(self):
        self.setup_admin();base=time.time()
        with patch('server.time.time',return_value=base+1700):
            self.assertEqual(self.request('POST','/api/activity',{})[0],200)
        with patch('server.time.time',return_value=base+3200):
            self.assertEqual(self.request('GET','/api/state')[0],200)
        with patch('server.time.time',return_value=base+28801):
            self.assertEqual(self.request('POST','/api/activity',{})[0],401)

    def test_policy_audit_and_permission_denials_have_safe_details(self):
        self.setup_admin();employee=self.add_employee()
        self.assertEqual(self.request('POST','/api/policies',{'leave_policy':'hr_only'})[0],200)
        state=self.request('GET','/api/state')[1]
        event=next(row for row in state['audit'] if row['action']=='Policy changed')
        details=json.loads(event['details'])
        self.assertEqual(details['before']['leave_policy'],'manager_or_hr')
        self.assertEqual(details['after']['leave_policy'],'hr_only')
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('POST','/api/policies',{'require_mfa':False})[0],403)
        self.login()
        state=self.request('GET','/api/state')[1]
        denied=next(row for row in state['security_events'] if row['action']=='Access denied')
        self.assertEqual(denied['actor_id'],employee)
        self.assertNotIn('TestPassword',denied['details'])

    def test_backup_job_does_not_block_saves_and_is_audited(self):
        self.setup_admin();db=Path(self.server.db_path)
        backup.configure_backup(db,Path(self.temp.name)/'synced','Synthetic long recovery phrase!',60)
        entered,released=threading.Event(),threading.Event();original=backup.create_backup
        def delayed(*args,**kwargs):
            entered.set()
            if not released.wait(5):raise TimeoutError('Test barrier expired')
            return original(*args,**kwargs)
        with patch('backup.create_backup',side_effect=delayed):
            try:
                response=self.request('POST','/api/backup/run',{})
                self.assertEqual(response[0],202)
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.request('POST','/api/goals',{'title':'While backup runs','due_date':'2026-12-31'})[0],201)
            finally:released.set()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                status=self.request('GET','/api/backup/status')[1]
                if status.get('job',{}).get('status') in ('Completed','Failed'):break
                time.sleep(0.03)
        self.assertEqual(status['job']['status'],'Completed')
        self.assertTrue(any(row['action']=='Backup completed' for row in self.request('GET','/api/state')[1]['security_events']))

    def test_samples_excluded_and_month_end_joiner_is_prorated(self):
        self.setup_admin()
        response=self.request('POST','/api/employees',{'name':'Late joiner','email':'late@example.org','title':'Analyst','department':'Operations','location':'Local','annual_salary':600000,'start_date':'2026-10-31'})
        self.assertEqual(response[0],201)
        state=self.request('GET','/api/state')[1]
        sample_ids={row['id'] for row in state['employees'] if row['is_sample']}
        preview=self.request('GET','/api/payroll?month=2026-10')[1]
        self.assertFalse(sample_ids.intersection(row['id'] for row in preview['rows']))
        row=next(row for row in preview['rows'] if row['id']==response[1]['id'])
        self.assertEqual(row['monthly_gross'],1612.90)
        self.assertEqual(row['paid_days'],1)

    def test_overnight_checkout_and_second_session(self):
        self.setup_admin();self.add_employee();self.login('person@example.org','EmployeePass123!')
        with patch('server.datetime') as clock:
            clock.now.return_value=datetime.fromisoformat('2026-10-09T23:55:00+05:30')
            self.assertEqual(self.request('POST','/api/attendance',{'action':'in'})[0],201)
            clock.now.return_value=datetime.fromisoformat('2026-10-10T00:10:00+05:30')
            self.assertEqual(self.request('POST','/api/attendance',{'action':'out'})[0],200)
            self.assertEqual(self.request('POST','/api/attendance',{'action':'in'})[0],201)
            self.assertEqual(self.request('POST','/api/attendance',{'action':'in'})[0],409)

    def test_leave_budget_cancellation_holidays_and_half_days(self):
        self.setup_admin();self.add_employee()
        self.assertEqual(self.request('POST','/api/holidays',{'date':'2026-11-03','name':'Company holiday'})[0],201)
        self.login('person@example.org','EmployeePass123!')
        large={'type':'Annual','start_date':'2027-01-01','end_date':'2027-12-31','reason':'Over budget'}
        self.assertEqual(self.request('POST','/api/leave',large)[0],400)
        leave=self.request('POST','/api/leave',{'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-04','reason':'Break'})
        self.assertEqual(leave[0],201)
        row=next(row for row in self.request('GET','/api/state')[1]['leave'] if row['id']==leave[1]['id'])
        self.assertEqual(row['days'],2)
        self.assertEqual(self.request('PATCH',f'/api/leave/{row["id"]}',{'status':'Cancelled','reason':'Plans changed'})[0],200)
        half=self.request('POST','/api/leave',{'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-02','reason':'Half day','half_day':True})
        self.assertEqual(half[0],201)
        self.assertEqual(next(row for row in self.request('GET','/api/state')[1]['leave'] if row['id']==half[1]['id'])['days'],0.5)

    def test_benefit_withdrawal_and_identity_correction(self):
        self.setup_admin();employee=self.add_employee()
        row=next(row for row in self.request('GET','/api/state')[1]['employees'] if row['id']==employee)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'email':'corrected@example.org','start_date':'2026-10-02','expected_version':row.get('version',0)})[0],200)
        plan=self.request('POST','/api/benefit_plans',{'title':'Health','description':'Plan','monthly_cost_paise':25000})[1]['id']
        self.login('corrected@example.org','EmployeePass123!')
        enrollment=self.request('POST','/api/benefit_enrollments',{'plan_id':plan})[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/benefit_enrollments/{enrollment}',{'status':'Withdrawn'})[0],200)
        self.assertEqual(self.request('POST','/api/benefit_enrollments',{'plan_id':plan})[0],201)

    def test_approved_leave_cancellation_needs_independent_review(self):
        self.setup_admin();employee=self.add_employee();self.login('person@example.org','EmployeePass123!')
        record=self.request('POST','/api/leave',{'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Break'})[1]['id']
        self.login();self.assertEqual(self.request('PATCH',f'/api/leave/{record}',{'status':'Approved'})[0],200)
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('PATCH',f'/api/leave/{record}',{'status':'Cancelled','reason':'Changed plans'})[1]['status'],'Cancellation pending')
        self.assertEqual(self.request('PATCH',f'/api/leave/{record}',{'status':'Approved'})[0],403)
        self.login();self.assertEqual(self.request('PATCH',f'/api/leave/{record}',{'status':'Approved'})[1]['status'],'Cancelled')
        balance=next(row for row in self.request('GET','/api/state')[1]['leave_balances'] if row['employee_id']==employee and row['type']=='Annual')
        self.assertEqual(balance['reserved_and_used'],0)

    def test_attendance_corrections_are_independent_and_version_checked(self):
        self.setup_admin();employee=self.add_employee();self.login('person@example.org','EmployeePass123!')
        with patch('server.datetime') as clock:
            clock.now.return_value=datetime.fromisoformat('2026-10-09T09:00:00+05:30')
            record=self.request('POST','/api/attendance',{'action':'in'})[1]['id']
            clock.now.return_value=datetime.fromisoformat('2026-10-09T18:00:00+05:30')
            self.request('POST','/api/attendance',{'action':'out'})
        original=next(row for row in self.request('GET','/api/state')[1]['attendance'] if row['id']==record)
        submitted=self.request('POST','/api/attendance_corrections',{'attendance_id':record,'expected_version':original['version'],'check_in':'2026-10-09T09:30:00+05:30','check_out':'2026-10-09T18:00:00+05:30','break_minutes':30,'reason':'Corrected start and break'})
        self.assertEqual(submitted[0],201)
        correction=submitted[1]['id']
        self.assertEqual(self.request('PATCH',f'/api/attendance_corrections/{correction}',{'status':'Approved'})[0],403)
        self.login();self.assertEqual(self.request('PATCH',f'/api/attendance_corrections/{correction}',{'status':'Approved'})[0],200)
        saved=next(row for row in self.request('GET','/api/state')[1]['attendance'] if row['id']==record)
        self.assertTrue(saved['check_in'].startswith('2026-10-09T09:30:00'))
        self.assertEqual(saved['break_minutes'],30)
        self.assertGreater(saved['version'],original['version'])

    def test_payroll_uses_effective_salary_and_employment_end_dates(self):
        self.setup_admin();employee=self.add_employee()
        self.request('PATCH',f'/api/employees/{employee}',{'annual_salary':1200000,'effective_date':'2026-10-16'})
        preview=self.request('GET','/api/payroll?month=2026-10')[1]
        row=next(row for row in preview['rows'] if row['id']==employee)
        self.assertEqual(row['gross_paise'],7580645)
        self.request('PATCH',f'/api/employees/{employee}',{'status':'Inactive','end_date':'2026-10-20'})
        preview=self.request('GET','/api/payroll?month=2026-10')[1]
        row=next(row for row in preview['rows'] if row['id']==employee)
        self.assertEqual(row['paid_days'],20)
        self.assertEqual(row['gross_paise'],4032258)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(FollowupFlows(name) for name in FollowupFlows.__dict__ if name.startswith('test_'))
