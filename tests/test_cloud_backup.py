import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backup import create_backup, restore_backup, configure_backup, run_configured_backup, backup_status, process_lock
from cloud_backup import upload_verified, download_verified, configuration, cloud_status, sync_after_backup
from probe_oidc_https import certificates
from server import create_server


class WebDAVTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        ca,context=certificates(self.root)
        self.objects={};self.mode='valid';self.requests=[]
        self.blocked=threading.Event();self.release=threading.Event()
        owner=self
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,body=b''):
                self.send_response(status)
                self.send_header('Content-Length',str(len(body)))
                if owner.mode=='redirect':self.send_header('Location','https://203.0.113.1/never-contact')
                self.end_headers()
                try:self.wfile.write(body)
                except OSError:pass
            def authorized(self):
                owner.requests.append((self.command,self.path))
                if self.headers.get('Authorization')!='Basic '+base64.b64encode(b'fictional-user:fictional-password').decode():
                    self.reply(401);return False
                if owner.mode=='redirect':self.reply(307);return False
                return True
            def do_PUT(self):
                if not self.authorized():return
                assert self.headers.get('If-None-Match')=='*'
                assert not self.headers.get('Transfer-Encoding')
                content=self.rfile.read(int(self.headers['Content-Length']))
                if self.path in owner.objects:self.reply(412)
                else:owner.objects[self.path]=content;self.reply(201)
            def do_GET(self):
                if not self.authorized():return
                if owner.mode=='stall':owner.blocked.set();owner.release.wait(3)
                content=owner.objects.get(self.path)
                if content is None:self.reply(404)
                else:self.reply(200,content[:-1]+bytes([content[-1]^1]) if owner.mode=='tamper' else content)
        self.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        self.provider.socket=context.wrap_socket(self.provider.socket,server_side=True)
        self.thread=threading.Thread(target=self.provider.serve_forever,daemon=True);self.thread.start()
        self.environment=patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_URL':f'https://127.0.0.1:{self.provider.server_port}/backups/','OPENPEOPLE_WEBDAV_USER':'fictional-user','OPENPEOPLE_WEBDAV_PASSWORD':'fictional-password','OPENPEOPLE_WEBDAV_CA':str(ca)})
        self.environment.start()
        self.db=self.root/'source'/'workspace.db';self.server=create_server('127.0.0.1',0,self.db)
        connection=self.server.connect()
        with connection:
            connection.execute("INSERT INTO employees(name,email,title,department,location,start_date,password) VALUES('Cloud Person','fictional-cloud@example.org','Tester','HR','Remote','2026-10-01','synthetic')")
            connection.execute("INSERT INTO sessions(token,employee_id,csrf,expires,last_seen,auth_time) VALUES('old-session',1,'old-csrf',9999999999,9999999999,9999999999)")
        connection.close()
        self.phrase='Fictional cloud recovery phrase!'
        self.archive=create_backup(self.db,self.root/'snapshots',self.phrase)

    def tearDown(self):
        self.release.set()
        self.environment.stop();self.server.server_close()
        self.provider.shutdown();self.provider.server_close();self.thread.join(timeout=2);self.temp.cleanup()

    def test_real_https_upload_retry_download_and_host_loss_recovery(self):
        result=upload_verified(self.archive)
        self.assertTrue(result['uploaded_and_read_back']);self.assertFalse(result['off_device_restore_verified'])
        self.assertEqual(upload_verified(self.archive)['sha256'],result['sha256'])
        for body in self.objects.values():
            self.assertNotIn(b'fictional-cloud@example.org',body);self.assertNotIn(b'SQLite format',body)
        # Stop the fictional source server; remove its original paths by moving
        # only this test's temporary directory. Download bytes from the separate
        # HTTPS service after the archive and database paths disappear.
        self.server.server_close();self.db.parent.rename(self.root/'unavailable-source')
        self.archive.parent.rename(self.root/'unavailable-snapshots')
        self.assertFalse(self.db.exists());self.assertFalse(self.archive.exists())
        target=self.root/'download';target.mkdir()
        downloaded=download_verified(result['filename'],target,result['sha256'])
        self.assertEqual(downloaded.stat().st_mode & 0o777,0o600)
        restored=restore_backup(downloaded,self.root/'restored',self.phrase)
        connection=sqlite3.connect(restored)
        self.assertEqual(connection.execute('SELECT email FROM employees').fetchone()[0],'fictional-cloud@example.org')
        self.assertEqual(connection.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        connection.close()
        with self.assertRaises(ValueError):download_verified(result['filename'],target,result['sha256'])

    def test_cloud_failures_never_invalidate_local_backup_and_status_redacts_secrets(self):
        configure_backup(self.db,self.root/'configured',self.phrase)
        with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_PASSWORD':'bad-private-secret'}):
            archive=run_configured_backup(self.db)
        self.assertTrue(archive.exists())
        status=backup_status(self.db)
        self.assertIsNotNone(status['last_success']);self.assertEqual(status['cloud']['status'],'Failed')
        self.assertNotIn('bad-private-secret',json.dumps(status));self.assertFalse(status['cloud']['off_device_restore_verified'])
        with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_USER':'changed-account'}):
            self.assertEqual(cloud_status(self.db)['status'],'Not verified for current destination')
            self.assertFalse(cloud_status(self.db)['uploaded_and_read_back'])
        with process_lock(self.db,'cloud',timeout=0):
            self.assertEqual(sync_after_backup(self.db,self.archive)['status'],'Skipped')
        self.db.with_suffix('.cloud-status.json').write_text('invalid')
        self.assertEqual(cloud_status(self.db)['status'],'Unknown')
        self.db.with_suffix('.cloud-status.json').write_text('42')
        self.assertEqual(cloud_status(self.db)['status'],'Unknown')

    def test_tampering_and_conflicting_names_never_overwrite(self):
        result=upload_verified(self.archive)
        original=self.objects['/backups/'+self.archive.name]
        self.mode='tamper'
        with self.assertRaises(ValueError):upload_verified(self.archive)
        folder=self.root/'downloads';folder.mkdir()
        with self.assertRaises(ValueError):download_verified(self.archive.name,folder,result['sha256'])
        self.assertEqual(list(folder.iterdir()),[])
        self.assertEqual(self.objects['/backups/'+self.archive.name],original)
        self.mode='valid'
        with self.assertRaises(ValueError):download_verified(self.archive.name,folder,'0'*64)
        self.assertEqual(list(folder.iterdir()),[])

    def test_redirects_untrusted_certificates_and_plaintext_are_rejected(self):
        self.mode='redirect'
        with self.assertRaises(ValueError):upload_verified(self.archive)
        self.assertEqual(len(self.requests),1)
        self.mode='valid'
        import requests
        with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_CA':''}):
            with self.assertRaises(requests.RequestException):upload_verified(self.archive)
        plaintext=self.root/'openpeople-plaintext.opbackup';plaintext.write_text('not an encrypted snapshot')
        with self.assertRaises(ValueError):upload_verified(plaintext)
        link=self.root/'openpeople-symlink.opbackup';link.symlink_to(self.archive)
        with self.assertRaises(ValueError):upload_verified(link)
        with self.assertRaises(ValueError):download_verified('../workspace.db',self.root,'0'*64)

    def test_private_configuration_validation_and_missing_objects(self):
        for url in ('http://127.0.0.1/','https://user:password@example.org/','https://example.org/?token=secret','https://example.org/#fragment'):
            with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_URL':url}):
                with self.assertRaises(ValueError):configuration()
        with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_USER':''}):
            with self.assertRaises(ValueError):configuration()
        with self.assertRaises(ValueError):download_verified(self.archive.name,self.root,'0'*64)
        with self.assertRaises(ValueError):download_verified(self.archive.name,self.root,'invalid-hash')
        with patch.dict(os.environ,{'OPENPEOPLE_WEBDAV_URL':''}):
            self.assertIsNone(sync_after_backup(self.db,self.archive))

    def test_stalled_provider_worker_is_killed_without_blocking_database_writes(self):
        configure_backup(self.db,self.root/'configured',self.phrase)
        self.mode='stall';results=[]
        with patch('cloud_backup.WORKER_TIMEOUT',1.5):
            worker=threading.Thread(target=lambda:results.append(run_configured_backup(self.db)))
            worker.start()
            try:
                self.assertTrue(self.blocked.wait(1.4),'HTTPS worker did not reach the provider')
                started=time.monotonic();connection=self.server.connect()
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    connection.execute("UPDATE employees SET title='Still writable' WHERE id=1")
                connection.close()
                self.assertLess(time.monotonic()-started,1)
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive());self.assertEqual(len(results),1)
                self.assertTrue(results[0].exists());self.assertEqual(cloud_status(self.db)['status'],'Failed')
            finally:self.release.set();worker.join(timeout=3)
