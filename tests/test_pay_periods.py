import copy
import json
import unittest

from test_app import HRFlows


class PayPeriods(HRFlows):
    def fixture(self):
        status,data=self.request('POST','/api/setup',{'name':'Fictional HR','email':'admin@example.org','password':'TestPassword123!','include_samples':False})
        self.assertEqual(status,201);self.csrf=data['csrf'];worker=self.add_employee()
        reviewer=self.request('POST','/api/employees',{'name':'Reviewer','email':'reviewer@example.org','title':'Payroll','department':'Finance','location':'Remote','annual_salary':600000,'start_date':'2026-10-01','role':'payroll','password':'ReviewerPassword123!'})[1]['id']
        employer=self.request('POST','/api/legal_entities',{'code':'ONE','name':'Fictional employer','country':'IN','currency':'INR','employer_reference':'Fictional'})[1]['id']
        center=self.request('POST','/api/cost_centers',{'legal_entity_id':employer,'code':'FIN','name':'Finance'})[1]['id']
        self.assertEqual(self.request('POST','/api/employee_assignments',{'employee_id':worker,'legal_entity_id':employer,'cost_center_id':center,'expected_version':1})[0],200)
        status,group=self.request('POST','/api/pay_groups',{'legal_entity_id':employer,'name':'Weekly workers','frequency':'weekly'})
        self.assertEqual(status,201,group)
        self.assertEqual(self.request('POST','/api/pay_group_members',{'employee_id':worker,'pay_group_id':group['id'],'expected_employee_version':2,'expected_group_version':1})[0],200)
        period={'pay_group_id':group['id'],'expected_group_version':2,'period_start':'2026-10-01','period_end':'2026-10-07','pay_date':'2026-10-09','run_kind':'regular','reference':'OCT-W1'}
        return worker,reviewer,employer,group['id'],period

    def test_weekly_snapshot_external_binding_independent_finalization_and_own_statement(self):
        worker,reviewer,employer,group,period=self.fixture()
        status,created=self.request('POST','/api/pay_period_runs',period);self.assertEqual(status,201,created)
        run=created['id'];details=self.request('GET',f'/api/pay_runs/{run}')[1]
        row=details['rows'][0];self.assertEqual(row['employee_id'],worker)
        self.assertEqual(row['gross_paise'],1129032)  # 50,000 INR * 7/31, in paise.
        self.assertEqual(details['run']['period_start'],'2026-10-01')
        self.assertEqual(details['run']['pay_group_version'],2)
        self.login('reviewer@example.org','ReviewerPassword123!')
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],409)
        self.login();result={**row['external_template'],'provider':'Reviewed fictional provider','reference':'RESULT-W1','jurisdiction':'IN reviewed','rules_effective_date':'2026-10-01','review_note':'Checked annual applicability and provider statement','earnings':[{'label':'Gross','amount_minor':1200000}],'deductions':[{'label':'Reviewed tax','amount_minor':100000}],'employer_contributions':[],'net_minor':1100000}
        self.assertEqual(result['format'],'openpeople.external-payroll.v2')
        self.assertEqual(result['period']['run_id'],run)
        wrong=copy.deepcopy(result);wrong['period']['period_end']='2026-10-08'
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{row["id"]}',{'external_result':wrong})[0],400)
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{row["id"]}',{'external_result':result})[0],200)
        self.login('reviewer@example.org','ReviewerPassword123!')
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],200)
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{row["id"]}',{'external_result':result})[0],409)
        self.login('person@example.org','EmployeePass123!')
        state=self.request('GET','/api/state')[1];statement=state['payslips'][0]
        self.assertEqual(statement['period_end'],'2026-10-07')
        self.assertIn('Weekly workers: 2026-10-01 to 2026-10-07',state['notifications'][0]['message'])
        self.assertEqual(json.loads(statement['external_result'])['period']['pay_date'],'2026-10-09')
        self.assertEqual(self.request('GET','/api/pay_groups')[0],403)

    def test_stale_membership_scope_overlap_and_invalid_periods_rejected_atomically(self):
        worker,reviewer,employer,group,period=self.fixture()
        self.assertEqual(self.request('POST','/api/pay_group_members',{'employee_id':worker,'pay_group_id':group,'expected_employee_version':2,'expected_group_version':1})[0],409)
        self.assertEqual(self.request('POST','/api/pay_period_runs',{**period,'expected_group_version':1})[0],409)
        for fields in ({'period_end':'2026-10-06'},{'pay_date':'2026-09-01'},{'period_start':'bad'},{'run_kind':'compliant'},{'pay_group_id':True},{'reference':'x\nY'},{'extra':1}):
            self.assertEqual(self.request('POST','/api/pay_period_runs',{**period,**fields})[0],400,fields)
        self.assertEqual(self.request('POST','/api/pay_period_runs',period,csrf=False)[0],403)
        self.assertEqual(self.request('POST','/api/pay_period_runs',period)[0],201)
        self.assertEqual(self.request('POST','/api/pay_period_runs',{**period,'reference':'DUPLICATE'})[0],409)
        self.request('POST',f'/api/payroll_access/{reviewer}',{'mode':'restricted','entity_ids':[],'expected_version':0})
        self.login('reviewer@example.org','ReviewerPassword123!')
        self.assertEqual(self.request('GET','/api/pay_groups')[1]['rows'],[])
        self.assertEqual(self.request('POST','/api/pay_period_runs',{**period,'period_start':'2026-10-08','period_end':'2026-10-14','pay_date':'2026-10-16','reference':'W2'})[0],404)
        self.assertEqual(self.request('POST','/api/pay_groups',{'legal_entity_id':employer,'name':'Forbidden','frequency':'weekly'})[0],403)

    def test_adjustment_has_zero_estimate_and_regular_legacy_overlap_is_blocked(self):
        worker,reviewer,employer,group,period=self.fixture()
        self.assertEqual(self.request('POST','/api/pay_runs',{'month':'2026-10'})[0],201)
        self.assertEqual(self.request('POST','/api/pay_period_runs',period)[0],409)
        status,run=self.request('POST','/api/pay_period_runs',{**period,'run_kind':'adjustment','reference':'CORRECTION-1'})
        self.assertEqual(status,201,run)
        row=self.request('GET',f'/api/pay_runs/{run["id"]}')[1]['rows'][0]
        self.assertEqual(row['gross_paise'],0)
        self.assertTrue(row['external_template']['period']['external_review_required'])

    def test_new_regular_run_blocks_legacy_month_and_recovers_period_snapshot(self):
        from backup import create_backup,restore_backup
        import sqlite3
        from pathlib import Path
        import tempfile
        worker,reviewer,employer,group,period=self.fixture()
        run=self.request('POST','/api/pay_period_runs',period)[1]['id']
        self.assertEqual(self.request('POST','/api/pay_runs',{'month':'2026-10'})[0],409)
        with tempfile.TemporaryDirectory() as folder:
            archive=create_backup(self.server.db_path,Path(folder)/'backup','Fictional recovery passphrase for tests!')
            restored=restore_backup(archive,Path(folder)/'recovered','Fictional recovery passphrase for tests!')
            with sqlite3.connect(restored) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
                self.assertEqual(db.execute('SELECT pay_group_id,period_start,period_end,pay_date FROM pay_runs WHERE id=?',(run,)).fetchone(),(group,'2026-10-01','2026-10-07','2026-10-09'))
                self.assertEqual(db.execute('SELECT employee_id FROM pay_group_members').fetchall(),[(worker,)])

    def test_all_frequency_boundaries_and_calendar_estimates(self):
        from pay_periods import validate_period
        from server import APIError
        base={'pay_group_id':1,'expected_group_version':1,'period_start':'2028-02-01','period_end':'2028-02-29','pay_date':'2028-03-01','run_kind':'regular','reference':'TEST'}
        for frequency,first,last in [('monthly','2028-02-01','2028-02-29'),('semimonthly','2028-02-16','2028-02-29'),('semimonthly','2028-02-01','2028-02-15'),('fortnightly','2027-12-25','2028-01-07'),('weekly','2028-02-23','2028-02-29')]:
            with self.subTest(frequency=frequency):
                self.assertEqual(validate_period({**base,'period_start':first,'period_end':last}, {'frequency':frequency})[0].isoformat(),first)
                with self.assertRaises(APIError):validate_period({**base,'period_start':first,'period_end':first},{'frequency':frequency})

    def test_group_transfer_cannot_duplicate_a_workers_regular_pay_period(self):
        worker,reviewer,employer,group,period=self.fixture()
        self.assertEqual(self.request('POST','/api/pay_period_runs',period)[0],201)
        second=self.request('POST','/api/pay_groups',{'legal_entity_id':employer,'name':'Transferred workers','frequency':'weekly'})[1]['id']
        self.assertEqual(self.request('POST','/api/pay_group_members',{'employee_id':worker,'pay_group_id':second,'expected_employee_version':3,'expected_group_version':1})[0],200)
        changed={**period,'pay_group_id':second,'expected_group_version':2,'reference':'TRANSFER'}
        self.assertEqual(self.request('POST','/api/pay_period_runs',changed)[0],409)
        self.assertEqual(self.request('POST','/api/pay_period_runs',{**changed,'period_start':'2026-10-08','period_end':'2026-10-14','pay_date':'2026-10-16'})[0],201)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(PayPeriods(name) for name in PayPeriods.__dict__ if name.startswith('test_'))
