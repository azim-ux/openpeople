import base64
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_app import HRFlows


class ReleaseControls(HRFlows):
    def enroll(self):
        from identity import totp
        self.setup_admin()
        secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':totp(secret)})[0],200)
        return secret

    def issue(self,secret):
        from identity import totp
        # Advance the proof counter without waiting or weakening replay checks.
        moment=time.time()+60
        with patch('identity.time.time',return_value=moment):
            return self.request('POST','/api/mfa/recovery-codes',{'otp':totp(secret,moment)})

    def test_private_bootstrap_verifies_factor_and_refuses_existing_owner(self):
        from provisioning import initialize_administrator
        from identity import totp
        from server import APIError,password_matches
        secret=base64.b32encode(b'01234567890123456789').decode()
        with self.assertRaises(APIError):
            initialize_administrator(self.server,'Fictional Owner','admin@openpeople.invalid','FictionalPassword123!',secret,'bad','GB')
        db=self.server.connect()
        self.assertEqual(db.execute('SELECT count(*) FROM employees').fetchone()[0],0);db.close()
        owner=initialize_administrator(self.server,'Fictional Owner','admin@openpeople.invalid','FictionalPassword123!',secret,totp(secret),'GB')
        db=self.server.connect()
        row=db.execute('SELECT * FROM employees WHERE id=?',(owner,)).fetchone()
        self.assertTrue(password_matches('FictionalPassword123!',row['password']))
        self.assertEqual((row['country'],row['currency'],row['timezone'],row['is_sample']),('GB','GBP','Europe/London',0))
        self.assertTrue(row['totp_secret']);self.assertNotIn(secret,row['totp_secret'])
        self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        from workspace import setting
        self.assertTrue(setting(db,'require_mfa'));db.close()
        self.assertFalse(Path(self.server.db_path).with_suffix('.setup-token').exists())
        with self.assertRaises(APIError):
            initialize_administrator(self.server,'Another Owner','other@openpeople.invalid','OtherPassword123!',secret,totp(secret),'US')

    def test_recovery_codes_are_hashed_single_use_and_revoke_sessions(self):
        secret=self.enroll();status,result=self.issue(secret)
        self.assertEqual(status,201,result);codes=result['codes'];self.assertEqual(len(set(codes)),10)
        db=self.server.connect()
        stored=[row[0] for row in db.execute('SELECT digest FROM mfa_recovery_codes')]
        self.assertEqual(len(stored),10)
        self.assertTrue(all(len(value)==64 for value in stored))
        events=' '.join(row[0] for row in db.execute('SELECT details FROM security_events'))
        self.assertTrue(all(code not in events and code not in stored for code in codes));db.close()
        old_cookie=self.cookie;self.cookie=''
        status,result=self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','recovery_code':codes[0]})
        self.assertEqual(status,200,result);new_cookie=self.cookie
        self.cookie=old_cookie;self.assertEqual(self.request('GET','/api/state')[0],401)
        self.cookie=new_cookie;self.csrf=result['csrf']
        self.assertEqual(self.request('GET','/api/security')[1]['recovery_codes_remaining'],9)
        self.cookie=''
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','recovery_code':codes[0]})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'wrong','recovery_code':codes[1]})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','recovery_code':codes[1]})[0],200)

    def test_recovery_code_generation_needs_csrf_factor_and_recent_session(self):
        secret=self.enroll()
        self.assertEqual(self.request('POST','/api/mfa/recovery-codes',{'otp':'bad'})[0],401)
        self.assertEqual(self.request('POST','/api/mfa/recovery-codes',{},csrf=False)[0],403)
        db=self.server.connect()
        with db:db.execute('UPDATE sessions SET auth_time=?',(time.time()-301,))
        db.close()
        self.assertEqual(self.issue(secret)[0],403)

    def test_recovery_codes_do_not_survive_password_recovery_or_archival_restore(self):
        from backup import create_backup,restore_backup
        from manage import reset_password
        secret=self.enroll();self.assertEqual(self.issue(secret)[0],201)
        with tempfile.TemporaryDirectory() as folder:
            archive=create_backup(self.server.db_path,Path(folder)/'archives','Fictional archive phrase 123!')
            recovered=restore_backup(archive,Path(folder)/'restored','Fictional archive phrase 123!')
            with closing(sqlite3.connect(recovered)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM mfa_recovery_codes').fetchone()[0],0)
            reset_password(self.server.db_path,'admin@example.org','ReplacementPassword123!')
            db=self.server.connect();self.assertEqual(db.execute('SELECT count(*) FROM mfa_recovery_codes').fetchone()[0],0);db.close()

    def test_ssO_recovery_is_single_use_and_replacement_invalidates_old_codes(self):
        secret=self.enroll();_,first=self.issue(secret)
        from identity import totp
        moment=time.time()+120
        with patch('identity.time.time',return_value=moment):
            status,second=self.request('POST','/api/mfa/recovery-codes',{'otp':totp(secret,moment)})
        self.assertEqual(status,201)
        original_cookie=self.cookie;self.cookie=''
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','recovery_code':first['codes'][0]})[0],401)
        # Model an authenticated OIDC session that still needs its local factor.
        db=self.server.connect()
        with db:db.execute('UPDATE sessions SET mfa_verified=0')
        db.close()
        # Restore the valid local session cookie created during enrollment.
        self.cookie=original_cookie
        # The session cookie name and CSRF remain those of the enrollment session.
        self.assertEqual(self.request('POST','/api/mfa/verify',{'recovery_code':second['codes'][0]})[0],200)
        self.assertEqual(self.request('GET','/api/state')[0],200)

    def test_interactive_enrollment_cleanup_and_no_secret_arguments(self):
        import contextlib
        import io
        from identity import totp
        from provisioning import interactive_setup
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'workspace.db'
            output=io.StringIO()
            def prompt(label):
                if 'code' in label:
                    enrollment=next(Path(folder).glob('enrollment-*.private'))
                    self.assertEqual(enrollment.stat().st_mode&0o777,0o600)
                    secret=enrollment.read_text().split('Secret: ')[1].splitlines()[0]
                    self.assertNotIn(secret,output.getvalue())
                    return totp(secret)
                return 'FictionalTerminalPassword123!'
            with patch('provisioning.sys.stdin.isatty',return_value=True),patch('provisioning.sys.stderr.isatty',return_value=True),patch('provisioning.getpass.getpass',side_effect=prompt),contextlib.redirect_stdout(output):
                interactive_setup(target,country='JP')
            self.assertFalse(list(Path(folder).glob('enrollment-*.private')))
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('SELECT email,country FROM employees').fetchone(),('admin@openpeople.invalid','JP'))
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'workspace.db'
            with patch('provisioning.sys.stdin.isatty',return_value=False),self.assertRaises(ValueError):interactive_setup(target)
            self.assertFalse(target.exists())
            answers=iter(['FictionalTerminalPassword123!','FictionalTerminalPassword123!'])
            def interrupted(label):
                if 'code' in label:raise KeyboardInterrupt()
                return next(answers)
            with patch('provisioning.sys.stdin.isatty',return_value=True),patch('provisioning.sys.stderr.isatty',return_value=True),patch('provisioning.getpass.getpass',side_effect=interrupted),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(KeyboardInterrupt):
                interactive_setup(target)
            self.assertFalse(list(Path(folder).glob('enrollment-*.private')))
            with closing(sqlite3.connect(target)) as db:self.assertEqual(db.execute('SELECT count(*) FROM employees').fetchone()[0],0)

    def test_concurrent_recovery_consumes_exactly_once_and_disabled_accounts_fail(self):
        from concurrent.futures import ThreadPoolExecutor
        import requests
        secret=self.enroll();status,result=self.issue(secret);self.assertEqual(status,201)
        payload={'email':'admin@example.org','password':'TestPassword123!','recovery_code':result['codes'][0]}
        def login():
            client=requests.Session();client.trust_env=False
            return client.post(f'http://127.0.0.1:{self.server.server_port}/api/login',json=payload,timeout=5).status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(sorted(workers.map(lambda _:login(),range(2))),[200,401])
        db=self.server.connect()
        with db:db.execute("UPDATE employees SET status='Inactive' WHERE email='admin@example.org'")
        db.close();self.cookie=''
        self.assertEqual(self.request('POST','/api/login',{**payload,'recovery_code':result['codes'][1]})[0],401)
        db=self.server.connect();self.assertEqual(db.execute('SELECT count(*) FROM mfa_recovery_codes').fetchone()[0],9);db.close()

    def test_failed_private_material_write_is_removed_without_overwriting_existing_file(self):
        from workspace import private_write
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'enrollment.private'
            with patch('workspace.os.fsync',side_effect=OSError('Fictional disk failure')),self.assertRaises(OSError):
                private_write(target,b'Fictional enrollment material')
            self.assertFalse(target.exists())
            target.write_text('Existing protected material')
            with self.assertRaises(FileExistsError):private_write(target,b'Must not replace')
            self.assertEqual(target.read_text(),'Existing protected material')


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(ReleaseControls(name) for name in ReleaseControls.__dict__ if name.startswith('test_'))
