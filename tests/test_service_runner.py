from pathlib import Path
import sys
import tempfile
import threading
import unittest

from service_runner import supervise


class RestartSupervision(unittest.TestCase):
    def test_restarts_only_crashes_and_preserves_private_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);path.chmod(0o700);count=path/'count'
            code="from pathlib import Path; import sys; p=Path(sys.argv[1]); n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); raise SystemExit(1 if n<2 else 0)"
            result=supervise([sys.executable,'-c',code,str(count)],path/'service.log',3,.01)
            self.assertEqual(result['restarts'],2);self.assertEqual(result['exit_code'],0);self.assertEqual(count.read_text(),'3')
            self.assertEqual((path/'service.log').stat().st_mode & 0o777,0o600)
            refused=supervise([sys.executable,'-c','raise SystemExit(2)'],path/'service.log',3,.01)
            self.assertTrue(refused['configuration_refused']);self.assertEqual(refused['restarts'],0)
            exhausted=supervise([sys.executable,'-c','raise SystemExit(1)'],path/'service.log',1,.01)
            self.assertTrue(exhausted['restart_budget_exhausted']);self.assertEqual(exhausted['restarts'],1)

    def test_stop_terminates_only_owned_child_and_bad_log_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);path.chmod(0o700);stop=threading.Event()
            timer=threading.Timer(.3,stop.set);timer.start()
            try:
                result=supervise([sys.executable,'-c','import time; time.sleep(30)'],path/'service.log',3,.01,stop)
                self.assertTrue(result['stopped']);self.assertEqual(result['restarts'],0)
            finally:timer.cancel()
            link=path/'symlink.log';link.symlink_to(path/'service.log')
            with self.assertRaises(ValueError):supervise([sys.executable],link)
            path.chmod(0o755)
            with self.assertRaises(ValueError):supervise([sys.executable],path/'service.log')
