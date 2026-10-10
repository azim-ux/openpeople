import json
from pathlib import Path
import tempfile
import unittest

from audit_integrity import verify
from test_app import HRFlows


class ProductionControls(HRFlows):
    def test_production_refuses_unconfigured_workspace_and_plain_http(self):
        from operations import production_boot_check
        result=production_boot_check(self.server)
        self.assertFalse(result['passed']);self.assertFalse(result['checks']['trusted_https_origin'])
        self.assertFalse(result['checks']['initialized_hr']);self.assertFalse(result['enterprise_production_approved'])

    def test_readiness_reports_real_policy_and_backup_state_without_certification(self):
        from operations import production_boot_check
        from identity import totp
        from backup import configure_backup,run_configured_backup,refresh_destination_health
        status,result=self.request('POST','/api/setup',{'name':'Fictional HR','email':'admin@example.org','password':'TestPassword123!','include_samples':False})
        self.assertEqual(status,201);self.csrf=result['csrf']
        secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
        self.request('POST','/api/mfa/confirm',{'otp':totp(secret)})
        self.request('POST','/api/policies',{'require_mfa':True})
        self.server.public_origin='https://fictional-hr.example'
        with tempfile.TemporaryDirectory() as folder:
            configure_backup(self.server.db_path,folder,'Fictional private recovery phrase 123!',60,30)
            run_configured_backup(self.server.db_path);refresh_destination_health(self.server.db_path)
            result=production_boot_check(self.server)
            self.assertTrue(result['passed'],result)
            self.assertFalse(result['enterprise_production_approved']);self.assertFalse(result['off_device_recovery_verified'])
            self.server.production_mode=True
            self.assertEqual(self.request('POST','/api/policies',{'require_mfa':False})[0],400)
            Path(folder).rename(folder+'-missing')
            try:self.assertFalse(production_boot_check(self.server)['passed'])
            finally:Path(folder+'-missing').rename(folder)

    def test_monitoring_is_private_and_liveness_does_not_expose_employees(self):
        self.assertEqual(self.request('GET','/api/health/live')[0],200)
        self.assertEqual(set(self.request('GET','/api/health/live')[1]),{'status','version'})
        self.assertEqual(self.request('GET','/api/operations')[0],401)
        self.setup_admin();result=self.request('GET','/api/operations')[1]
        self.assertIn('checks',result);self.assertFalse(result['passed'])
        self.add_employee();self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('GET','/api/operations')[0],403)

    def test_streaming_audit_verification_accepts_explicit_unlimited_offline_budget(self):
        self.setup_admin();self.add_employee();db=self.server.connect()
        try:
            from workspace import security_event
            with db:security_event(db,'Fictional capacity event',None,'test')
            self.assertFalse(verify(db,maximum=1)['passed'])
            anchor=verify(db,maximum=None)
            self.assertTrue(anchor['passed']);self.assertTrue(verify(db,anchor,maximum=None)['passed'])
            with self.assertRaises(ValueError):verify(db,maximum=True)
            with self.assertRaises(ValueError):verify(db,maximum=0)
        finally:db.close()


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(ProductionControls(name) for name in ProductionControls.__dict__ if name.startswith('test_'))
