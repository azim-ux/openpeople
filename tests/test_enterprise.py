import hashlib
import json
import unittest

from test_app import HRFlows


class EnterpriseFlows(HRFlows):
    def fixture(self):
        self.setup_admin();worker=self.add_employee()
        reviewer=self.request('POST','/api/employees',{'name':'Fictional peer','email':'peer@example.org','title':'Payroll','department':'Finance','location':'Remote','annual_salary':600000,'start_date':'2026-10-01','role':'payroll','password':'PeerPassword123!'})[1]['id']
        employer=self.request('POST','/api/legal_entities',{'code':'FICT-IN','name':'Fictional employer <script>','country':'IN','currency':'INR','employer_reference':'Fictional registration'})[1]['id']
        center=self.request('POST','/api/cost_centers',{'legal_entity_id':employer,'code':'FIN','name':'Finance'})[1]['id']
        self.assertEqual(self.request('POST','/api/employee_assignments',{'employee_id':worker,'legal_entity_id':employer,'cost_center_id':center,'expected_version':1})[0],200)
        return worker,reviewer,employer,center

    def test_assignment_versions_country_validation_and_immutable_snapshots(self):
        worker,reviewer,employer,center=self.fixture()
        data={'employee_id':worker,'legal_entity_id':employer,'cost_center_id':center,'expected_version':1}
        self.assertEqual(self.request('POST','/api/employee_assignments',data)[0],409)
        self.assertEqual(self.request('PATCH',f'/api/employees/{worker}',{'country':'US','currency':'INR'})[0],409)
        state=self.request('GET','/api/state')[1]
        self.assertEqual(next(e for e in state['employees'] if e['id']==worker)['version'],2)
        run=self.request('POST','/api/pay_runs',{'month':'2026-10'})[1]['id']
        assignment=state['employee_assignments'][0]
        self.assertEqual(self.request('PATCH',f'/api/employee_assignments/{assignment["id"]}',{'remove':True,'expected_version':2})[0],200)
        row=next(r for r in self.request('GET',f'/api/pay_runs/{run}')[1]['rows'] if r['employee_id']==worker)
        self.assertEqual((row['legal_entity_id'],row['cost_center_id']),(employer,center))
        self.assertEqual(self.request('PATCH',f'/api/employees/{worker}',{'country':'US','currency':'INR'})[0],200)
        self.assertEqual(self.request('POST','/api/employee_assignments',{**data,'expected_version':4})[0],400)
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('POST','/api/legal_entities',{})[0],403)
        self.assertEqual(self.request('GET','/api/state')[1]['legal_entities'],[])
        self.assertEqual(self.request('GET',f'/api/filing_packets/9223372036854775808')[0],403)

    def test_filing_lifecycle_export_integrity_and_separation_of_duties(self):
        worker,reviewer,employer,center=self.fixture()
        run=self.request('POST','/api/pay_runs',{'month':'2026-10'})[1]['id']
        data={'run_id':run,'legal_entity_id':employer,'expected_version':1}
        self.assertEqual(self.request('POST','/api/filing_packets',data)[0],409)
        row=next(r for r in self.request('GET',f'/api/pay_runs/{run}')[1]['rows'] if r['employee_id']==worker)
        value={**row['external_template'],'provider':'Fictional approved provider','reference':'RESULT-001','rules_effective_date':'2026-10-01','review_note':'Fictional independently checked inputs'}
        self.assertEqual(self.request('PATCH',f'/api/pay_results/{row["id"]}',{'external_result':value})[0],200)
        self.login('peer@example.org','PeerPassword123!')
        self.assertEqual(self.request('PATCH',f'/api/pay_runs/{run}',{'status':'Finalized'})[0],200)
        self.login()
        self.assertEqual(self.request('POST','/api/filing_packets',{**data,'expected_version':2})[0],409)
        status,created=self.request('POST','/api/filing_packets',{**data,'expected_version':3})
        self.assertEqual(status,201);packet=created['id']
        self.assertEqual(self.request('POST','/api/filing_packets',{**data,'expected_version':3})[0],409)
        path=f'/api/filing_packets/{packet}'
        exported=self.request('GET',path+'/export')[1]
        digest=hashlib.sha256(json.dumps(exported['packet'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(digest,created['sha256']);self.assertFalse(exported['packet']['agency_submission_format'])
        self.assertEqual(exported['packet']['totals']['gross_minor'],row['gross_paise'])
        review={'expected_version':1,'status':'Reviewed','review_note':'Independent reconciliation completed'}
        self.assertEqual(self.request('PATCH',path,review)[0],403)
        self.login('peer@example.org','PeerPassword123!')
        self.assertTrue(self.request('GET',path)[1]['can_review'])
        self.assertEqual(self.request('PATCH',path,review)[0],200)
        self.assertEqual(self.request('PATCH',path,review)[0],409)
        self.assertEqual(self.request('PATCH',path,{'status':'Accepted externally','expected_version':2})[0],409)
        evidence={'status':'Submitted externally','expected_version':2,'receipt_sha256':'a'*64,'external_reference':'Fictional acknowledgment'}
        self.assertEqual(self.request('PATCH',path,{**evidence,'receipt_sha256':'bad'})[0],400)
        self.assertEqual(self.request('PATCH',path,evidence)[0],200)
        final=self.request('PATCH',path,{**evidence,'status':'Accepted externally','expected_version':3})
        self.assertEqual(final[0],200);self.assertFalse(final[1]['authority_verified'])
        self.assertEqual(self.request('PATCH',path,{**evidence,'expected_version':4})[0],409)
        self.login()
        audit=self.request('GET','/api/state')[1]['audit']
        self.assertTrue(any(a['entity']=='filing_packets' for a in audit))
        self.assertTrue(all('payload' not in json.loads(a['details']).get('after',{}) for a in audit if a['entity']=='filing_packets'))
        from backup import create_backup, restore_backup
        from pathlib import Path
        import sqlite3
        archive=create_backup(self.server.db_path,Path(self.temp.name)/'snapshots','Fictional enterprise recovery phrase!')
        restored=restore_backup(archive,Path(self.temp.name)/'restored','Fictional enterprise recovery phrase!')
        recovered=sqlite3.connect(restored)
        try:
            self.assertEqual(recovered.execute('PRAGMA user_version').fetchone()[0],9)
            self.assertEqual(recovered.execute('SELECT status,version,sha256 FROM filing_packets').fetchone(),('Accepted externally',4,digest))
            self.assertEqual(recovered.execute('SELECT legal_entity_id,cost_center_id FROM pay_results WHERE employee_id=?',(worker,)).fetchone(),(employer,center))
            self.assertEqual(recovered.execute('SELECT count(*) FROM employee_assignments').fetchone()[0],1)
            self.assertEqual(recovered.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertGreaterEqual(recovered.execute("SELECT count(*) FROM audit WHERE entity='filing_packets'").fetchone()[0],4)
        finally:recovered.close()
        db=self.server.connect()
        try:
            with db:db.execute('UPDATE filing_packets SET payload=? WHERE id=?',('{}',packet))
        finally:db.close()
        self.assertEqual(self.request('GET',path+'/export')[0],409)
        self.assertEqual(self.request('PATCH',path,{'status':'Reviewed','expected_version':4,'review_note':'Do not accept corrupted bytes'})[0],409)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(EnterpriseFlows(name) for name in EnterpriseFlows.__dict__ if name.startswith('test_'))
