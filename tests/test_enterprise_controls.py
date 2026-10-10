import copy
import json
import sqlite3
import unittest

from audit_integrity import verify
from test_app import HRFlows
from statutory import calculate
from statutory_uk import template


class Controls(HRFlows):
    def fixtures(self):
        self.setup_admin();one=self.add_employee()
        def person(email):
            status,data=self.request('POST','/api/employees',{'name':email,'email':email,'title':'Payroll','department':'Finance','location':'Remote','annual_salary':600000,'start_date':'2026-10-01','role':'payroll','password':'ReviewerPassword123!'})
            self.assertEqual(status,201,data);return data['id']
        reviewer=person('reviewer@example.org');two=person('other@example.org')
        employers=[];self.centers=[]
        for code in ('ONE','TWO'):
            status,data=self.request('POST','/api/legal_entities',{'code':code,'name':code,'country':'IN','currency':'INR','employer_reference':'Fictional'})
            self.assertEqual(status,201);employers.append(data['id'])
            self.centers.append(self.request('POST','/api/cost_centers',{'legal_entity_id':data['id'],'code':'FIN','name':'Finance'})[1]['id'])
        for worker,employer,center in zip((one,two),employers,self.centers):
            self.assertEqual(self.request('POST','/api/employee_assignments',{'employee_id':worker,'legal_entity_id':employer,'cost_center_id':center,'expected_version':1})[0],200)
        return one,two,reviewer,employers

    def test_employer_scope_salary_preview_snapshot_writes_and_session_revocation(self):
        one,two,reviewer,employers=self.fixtures()
        run=self.request('POST','/api/pay_runs',{'month':'2026-10'})[1]['id']
        rows=self.request('GET',f'/api/pay_runs/{run}')[1]['rows']
        denied=next(row for row in rows if row['employee_id']==two)
        self.login('reviewer@example.org','ReviewerPassword123!');old=(self.cookie,self.csrf)
        self.login();grant={'mode':'restricted','entity_ids':[employers[0]],'expected_version':0}
        self.assertEqual(self.request('POST',f'/api/payroll_access/{reviewer}',grant)[0],200)
        admin=(self.cookie,self.csrf);self.cookie,self.csrf=old
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.login('reviewer@example.org','ReviewerPassword123!')
        state=self.request('GET','/api/state')[1]
        self.assertIn('annual_salary',next(e for e in state['employees'] if e['id']==one))
        self.assertNotIn('annual_salary',next(e for e in state['employees'] if e['id']==two))
        self.assertEqual([e['id'] for e in state['legal_entities']],[employers[0]])
        self.assertEqual(self.request('POST','/api/pay_runs',{'month':'2026-11'})[0],403)
        snapshot=self.request('GET',f'/api/pay_runs/{run}')[1]
        self.assertEqual([r['employee_id'] for r in snapshot['rows']],[one])
        self.assertTrue(snapshot['scope_limited']);self.assertFalse(snapshot['can_finalize'])
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{denied["id"]}',{'deductions_paise':100,'deduction_note':'Not allowed'})[0],404)
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],403)
        preview=self.request('GET','/api/payroll?month=2026-10')[1]
        self.assertEqual([row['id'] for row in preview['rows']],[one])
        self.assertEqual(self.request('POST',f'/api/payroll_access/{reviewer}',grant)[0],403)
        self.cookie,self.csrf=admin
        self.assertEqual(self.request('POST',f'/api/payroll_access/{reviewer}',grant)[0],409)
        # Current employer changes must not reveal a historical salary snapshot.
        self.assertEqual(self.request('PATCH',f'/api/employee_assignments/{state["employee_assignments"][0]["id"]}',{'remove':True,'expected_version':2})[0],200)
        self.assertEqual(self.request('POST','/api/employee_assignments',{'employee_id':two,'legal_entity_id':employers[0],'cost_center_id':self.centers[0],'expected_version':2})[0],200)
        self.login('reviewer@example.org','ReviewerPassword123!')
        self.assertEqual([r['employee_id'] for r in self.request('GET',f'/api/pay_runs/{run}')[1]['rows']],[one])

    def test_access_requires_fresh_auth_valid_exact_payload_and_empty_scope_denies(self):
        one,two,reviewer,employers=self.fixtures();path=f'/api/payroll_access/{reviewer}'
        for data in ({},{'mode':'restricted','entity_ids':[True],'expected_version':0},
                     {'mode':'restricted','entity_ids':[employers[0],employers[0]],'expected_version':0},
                     {'mode':'all','entity_ids':employers,'expected_version':0},
                     {'mode':'restricted','entity_ids':[999999],'expected_version':0}):
            self.assertEqual(self.request('POST',path,data)[0],400)
        self.assertEqual(self.request('POST','/api/payroll_access/9223372036854775808',{})[0],400)
        self.assertEqual(self.request('POST',path,{'mode':'restricted','entity_ids':[],'expected_version':0},csrf=False)[0],403)
        db=self.server.connect()
        with db:db.execute('UPDATE sessions SET auth_time=auth_time-301')
        db.close()
        self.assertEqual(self.request('POST',path,{'mode':'restricted','entity_ids':[],'expected_version':0})[0],403)
        self.login();self.assertEqual(self.request('POST',path,{'mode':'restricted','entity_ids':[],'expected_version':0})[0],200)
        self.login('reviewer@example.org','ReviewerPassword123!')
        self.assertEqual(self.request('GET','/api/payroll?month=2026-10')[1]['rows'],[])

    def test_append_only_chains_anchor_prefix_and_corruption_detection(self):
        self.setup_admin();db=self.server.connect()
        try:
            before=verify(db);self.assertTrue(before['passed'])
            self.add_employee()
            self.assertTrue(verify(db,before)['passed'])
            for sql in ("UPDATE audit SET action='altered'","DELETE FROM security_events","DELETE FROM audit_seals"):
                with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):db.execute(sql)
            db.rollback()
            with self.assertRaises(ValueError):verify(db,maximum=0)
            with self.assertRaises(ValueError):verify(db,{})
            wrong=copy.deepcopy(before);wrong['chains']['audit']['digest']='f'*64
            self.assertFalse(verify(db,wrong)['passed'])
            # A privileged owner bypasses the DB guard; the verifier still sees it.
            with db:
                db.execute('DROP TRIGGER audit_deny_update')
                db.execute("UPDATE audit SET action='altered' WHERE id=(SELECT min(id) FROM audit)")
            self.assertFalse(verify(db)['passed'])
        finally:db.close()
        self.assertFalse(self.request('GET','/api/audit/verify')[1]['passed'])
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('GET','/api/audit/verify')[0],403)

    def test_recovery_refuses_corrupted_audit_history_before_publishing_files(self):
        from backup import create_backup,restore_backup
        from pathlib import Path
        self.setup_admin();self.add_employee();db=self.server.connect()
        with db:
            db.execute('DROP TRIGGER audit_deny_update')
            db.execute("UPDATE audit SET action='tampered' WHERE id=(SELECT min(id) FROM audit)")
        db.close();root=Path(self.temp.name);phrase='Fictional audit recovery passphrase!'
        archive=create_backup(self.server.db_path,root/'snapshots',phrase)
        with self.assertRaisesRegex(ValueError,'audit history'):restore_backup(archive,root/'must-not-exist',phrase)
        self.assertFalse((root/'must-not-exist').exists())


class UKMath(unittest.TestCase):
    def test_official_third_decimal_rounding_examples(self):
        from decimal import Decimal
        from statutory_uk import round_contribution
        self.assertEqual(round_contribution(Decimal('6755.58')),6755)
        self.assertEqual(round_contribution(Decimal('6755.68')),6756)
        self.assertEqual(round_contribution(Decimal('.5')),0)
    def test_published_thresholds_and_all_categories(self):
        # Independently calculated from published HMRC thresholds/rates:
        # A at £5,000: (4189-1048)*8%+(5000-4189)*2%=£267.50.
        for category,employee,employer in [('A',26750,68745),('B',7433,68745),('C',0,68745),('J',7904,68745),
                ('D',7904,43755),('E',7433,43755),('F',26750,43755),('I',7433,43755),('K',0,43755),('L',7904,43755),('N',26750,43755),('S',0,43755),
                ('H',26750,12165),('M',26750,12165),('V',26750,12165),('Z',7904,12165)]:
            result=calculate({**template(),'category':category})
            self.assertEqual(result['deductions'][0]['amount_minor'],employee,category)
            self.assertEqual(result['employer_contributions'][0]['amount_minor'],employer,category)
        for wages,employee,employer in [(9600,0,0),(24200,0,2190),(96700,5800,13065),(100000,5866,13560)]:
            result=calculate({**template(),'frequency':'weekly','gross_minor':wages,'ni_earnings_minor':wages})
            self.assertEqual(result['deductions'][0]['amount_minor'],employee)
            self.assertEqual(result['employer_contributions'][0]['amount_minor'],employer)

    def test_boundaries_expiration_and_unsupported_inputs_fail_closed(self):
        for paid in ('2026-04-06','2027-04-05'):self.assertFalse(calculate({**template(),'pay_date':paid})['complete_statutory_supported'])
        for changes in ({'pay_date':'2026-04-05'},{'pay_date':'2027-04-06'},{'pay_date':None},{'category':[]},{'frequency':[]},{'frequency':'annual'},
                        {'ordinary_non_director':False},{'category_eligibility_reviewed':False},{'currency':'USD'},{'gross_minor':True},{'ni_earnings_minor':500001},{'extra':1}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):calculate({**template(),**changes})


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([*(Controls(name) for name in Controls.__dict__ if name.startswith('test_')),loader.loadTestsFromTestCase(UKMath)])
