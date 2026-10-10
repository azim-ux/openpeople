from pathlib import Path
import sqlite3
import tempfile
import unittest
from backup import create_backup, restore_backup, configure_backup, run_configured_backup, backup_status
from server import create_server


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/'private'/'workspace.db'
        self.server=create_server('127.0.0.1',0,self.db)
        connection=self.server.connect()
        with connection:
            connection.execute("INSERT INTO employees(name,email,title,department,location,start_date,password) VALUES('Backup Person','private@example.org','Analyst','People','Remote','2026-10-01','synthetic-hash')")
            connection.execute("INSERT INTO sessions(token,employee_id,csrf,expires,last_seen,auth_time) VALUES('synthetic',1,'synthetic',9999999999,9999999999,9999999999)")
            secret=self.server.vault.encrypt(b'SYNTHETIC-AUTHENTICATOR-SECRET').decode()
            connection.execute('UPDATE employees SET totp_secret=?,totp_pending=?',(secret,secret))
        connection.close()
        self.passphrase='Long synthetic backup passphrase!'

    def tearDown(self):
        self.server.server_close()
        self.temp.cleanup()

    def test_encrypted_snapshot_restore_and_session_revocation(self):
        archive=create_backup(self.db,self.root/'cloud-folder',self.passphrase)
        self.assertNotIn(b'private@example.org',archive.read_bytes())
        self.assertNotIn(b'SQLite format',archive.read_bytes())
        restored=restore_backup(archive,self.root/'restored',self.passphrase)
        db=sqlite3.connect(restored)
        self.assertEqual(db.execute('SELECT email FROM employees').fetchone()[0],'private@example.org')
        self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        from cryptography.fernet import Fernet
        saved=db.execute('SELECT totp_secret,totp_pending FROM employees').fetchone()
        self.assertEqual(Fernet(restored.with_suffix('.key').read_bytes()).decrypt(saved[0].encode()),b'SYNTHETIC-AUTHENTICATOR-SECRET')
        self.assertIsNone(saved[1])
        db.close()
        self.assertEqual(restored.stat().st_mode & 0o777,0o600)
        self.assertEqual(restored.with_suffix('.key').read_bytes(),self.db.with_suffix('.key').read_bytes())
        with self.assertRaises(ValueError):
            restore_backup(archive,self.root/'restored',self.passphrase)

    def test_tamper_and_wrong_key_rejected_without_restored_files(self):
        archive=create_backup(self.db,self.root/'cloud',self.passphrase)
        with self.assertRaises(ValueError):
            restore_backup(archive,self.root/'wrong-key','Another wrong passphrase!')
        self.assertFalse((self.root/'wrong-key').exists())
        damaged=bytearray(archive.read_bytes());damaged[-1]^=1
        archive.write_bytes(damaged)
        with self.assertRaises(ValueError):
            restore_backup(archive,self.root/'damaged',self.passphrase)
        self.assertFalse((self.root/'damaged').exists())

    def test_configured_backup_and_unsafe_destinations(self):
        with self.assertRaises(ValueError):
            configure_backup(self.db,self.db.parent,self.passphrase,60)
        with self.assertRaises(ValueError):
            configure_backup(self.db,self.root/'cloud','short',60)
        configure_backup(self.db,self.root/'cloud',self.passphrase,60)
        archive=run_configured_backup(self.db)
        status=backup_status(self.db)
        self.assertTrue(status['configured'])
        self.assertEqual(status['last_filename'],archive.name)
        self.assertEqual(status['provider_upload_verified'],False)
        self.assertNotIn(self.passphrase,self.db.with_suffix('.backup.json').read_text())

    def test_backup_commands_and_automatic_worker(self):
        import subprocess
        import sys
        import time
        from backup import start_backup_worker
        root=Path(__file__).resolve().parents[1]
        def command(*args,passphrase=False):
            process=subprocess.run([sys.executable,str(root/'backup.py'),*args],input=(self.passphrase+'\n'+self.passphrase+'\n') if passphrase else '',text=True,capture_output=True,timeout=15)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertNotIn(self.passphrase,process.stdout)
            return process.stdout.strip()
        folder=self.root/'synced-folder'
        command('configure','--db',str(self.db),'--folder',str(folder),'--interval','5',passphrase=True)
        stop,worker=start_backup_worker(self.db)
        try:
            deadline=time.monotonic()+5
            while not backup_status(self.db).get('last_filename') and time.monotonic()<deadline:
                time.sleep(0.05)
            self.assertTrue(backup_status(self.db).get('last_filename'))
        finally:
            stop.set();worker.join(timeout=5)
        archive=Path(command('run','--db',str(self.db)))
        command('status','--db',str(self.db))
        command('create','--db',str(self.db),'--folder',str(folder),passphrase=True)
        restored=Path(command('restore',str(archive),'--destination',str(self.root/'cli-restored'),passphrase=True))
        self.assertTrue(restored.is_file())

