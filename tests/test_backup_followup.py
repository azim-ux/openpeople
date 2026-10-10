import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import backup
from server import HRStore


class BackupFollowup(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name).resolve()
        self.db=self.root/'private/workspace.db';HRStore(self.db)
        self.phrase='Long synthetic recovery phrase!'

    def tearDown(self):self.temporary.cleanup()

    def test_cross_process_rotation_is_not_overwritten(self):
        old,new=self.root/'old',self.root/'new';new_phrase='New independently kept recovery phrase!'
        backup.configure_backup(self.db,old,self.phrase,60)
        entered,released=threading.Event(),threading.Event();original=backup.create_backup
        def delayed(*args,**kwargs):
            entered.set()
            if not released.wait(5):raise TimeoutError('Test barrier expired')
            return original(*args,**kwargs)
        with patch('backup.create_backup',side_effect=delayed),ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(backup.run_configured_backup,self.db)
            self.assertTrue(entered.wait(2))
            try:
                process=subprocess.run([sys.executable,'backup.py','configure','--db',str(self.db),'--folder',str(new),'--interval','90'],input=new_phrase+'\n'+new_phrase+'\n',text=True,capture_output=True,timeout=4)
                self.assertEqual(process.returncode,0,process.stderr)
            finally:released.set()
            future.result(timeout=5)
        config=json.loads(self.db.with_suffix('.backup.json').read_text())
        self.assertEqual(config['folder'],str(new))
        self.assertEqual(config['interval_minutes'],90)
        archive=backup.run_configured_backup(self.db)
        self.assertEqual(archive.parent,new)
        restored=backup.restore_backup(archive,self.root/'restored',new_phrase)
        self.assertTrue(restored.exists())

    def test_missing_or_replaced_destination_fails_without_recreation(self):
        folder=self.root/'sync';backup.configure_backup(self.db,folder,self.phrase,60)
        backup.run_configured_backup(self.db)
        folder.rename(self.root/'detached')
        with self.assertRaises(ValueError):backup.run_configured_backup(self.db)
        self.assertFalse(folder.exists())
        self.assertTrue(backup.backup_status(self.db)['last_error'])
        folder.mkdir()
        with self.assertRaises(ValueError):backup.run_configured_backup(self.db)
        self.assertFalse(backup.backup_status(self.db)['destination_available'])

    def test_retention_never_deletes_other_workspace_files(self):
        folder=self.root/'sync'
        backup.configure_backup(self.db,folder,self.phrase,60,retention_count=2)
        unrelated=folder/'openpeople-other-workspace.opbackup';unrelated.write_bytes(b'Unrelated fixture')
        archives=[backup.run_configured_backup(self.db) for _ in range(3)]
        self.assertFalse(archives[0].exists())
        self.assertTrue(archives[-1].exists())
        self.assertTrue(unrelated.exists())


    def test_disk_full_and_permission_failures_persist_without_losing_last_good_copy(self):
        folder=self.root/'sync';backup.configure_backup(self.db,folder,self.phrase,60)
        good=backup.run_configured_backup(self.db)
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')(1024,1024,0)
        with patch('backup.shutil.disk_usage',return_value=usage),self.assertRaises(ValueError):backup.run_configured_backup(self.db)
        self.assertTrue(good.exists());self.assertTrue(backup.backup_status(self.db)['last_error'])
        original=backup.atomic_private_write
        def deny_destination(path,data):
            if Path(path).suffix=='.opbackup':raise PermissionError('Fixture write denied')
            return original(path,data)
        with patch('backup.atomic_private_write',side_effect=deny_destination),self.assertRaises(PermissionError):backup.run_configured_backup(self.db)
        self.assertTrue(good.exists());self.assertEqual(backup.backup_status(self.db)['last_filename'],good.name)
        self.assertTrue(backup.verify_backup(good,self.phrase)['verified'])

    def test_interrupted_job_after_restart_is_reported_and_retryable(self):
        path=self.db.with_suffix('.backup-job.json')
        path.write_text(json.dumps({'id':'old-job','status':'Running','host_instance':'old-host'}))
        recover=getattr(backup,'recover_interrupted_job',None)
        self.assertIsNotNone(recover)
        recover(self.db,'new-host')
        result=json.loads(path.read_text());self.assertEqual(result['status'],'Failed')
        self.assertIn('interrupted',result['error'].lower())

    def test_stopped_worker_catches_up_after_restart(self):
        folder=self.root/'sync';backup.configure_backup(self.db,folder,self.phrase,60)
        stop,worker=backup.start_backup_worker(self.db)
        import time
        deadline=time.monotonic()+4
        while not backup.backup_status(self.db).get('last_filename') and time.monotonic()<deadline:time.sleep(0.05)
        stop.set();worker.join(timeout=4)
        before=backup.backup_status(self.db)['last_filename'];self.assertTrue(before)
        config=json.loads(self.db.with_suffix('.backup.json').read_text());config['last_success']='2000-01-01T00:00:00+00:00';self.db.with_suffix('.backup.json').write_text(json.dumps(config))
        self.assertTrue(backup.backup_status(self.db)['overdue'])
        stop,worker=backup.start_backup_worker(self.db)
        try:
            deadline=time.monotonic()+4
            while backup.backup_status(self.db).get('last_filename')==before and time.monotonic()<deadline:time.sleep(0.05)
            self.assertNotEqual(backup.backup_status(self.db)['last_filename'],before)
        finally:stop.set();worker.join(timeout=4)

    def test_api_status_uses_cached_health_without_touching_destination(self):
        folder=self.root/'sync';backup.configure_backup(self.db,folder,self.phrase,60)
        with patch('backup.destination_matches',side_effect=AssertionError('Request accessed destination')):
            status=backup.backup_status(self.db,check_destination=False)
            self.assertTrue(status['destination_available'])
        folder.rename(self.root/'lost-sync')
        backup.refresh_destination_health(self.db)
        self.assertFalse(backup.backup_status(self.db,check_destination=False)['destination_available'])

    def test_write_readback_failure_preserves_previous_recoverable_archives(self):
        folder=self.root/'sync';backup.configure_backup(self.db,folder,self.phrase,60,retention_count=2)
        previous=[backup.run_configured_backup(self.db) for _ in range(2)]
        original=backup.atomic_private_write
        def damaged_write(path,data):
            if Path(path).suffix=='.opbackup':data=data[:-1]+bytes([data[-1]^1])
            return original(path,data)
        with patch('backup.atomic_private_write',side_effect=damaged_write),self.assertRaises(ValueError):backup.run_configured_backup(self.db)
        self.assertTrue(all(path.exists() for path in previous))
        self.assertTrue(backup.verify_backup(previous[-1],self.phrase)['verified'])
