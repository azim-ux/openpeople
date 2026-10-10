"""Bounded child restart supervision without installing an OS service."""
import os
from pathlib import Path
import signal
import subprocess
import threading


def supervise(command,log_path,max_restarts=3,restart_delay=2,stop=None):
    if type(max_restarts) is not int or not 0<=max_restarts<=10 or not .01<=restart_delay<=30:raise ValueError('Use a bounded restart budget and delay.')
    log_path=Path(log_path)
    if not log_path.parent.is_dir() or log_path.parent.is_symlink() or log_path.is_symlink():raise ValueError('Use a private ordinary service log directory.')
    if os.name=='posix' and log_path.parent.stat().st_mode & 0o077:raise ValueError('Keep service logs in a private directory.')
    stop=stop or threading.Event();restarts=0
    descriptor=os.open(log_path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
    os.fchmod(descriptor,0o600)
    with os.fdopen(descriptor,'wb',buffering=0) as log:
        while not stop.is_set():
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                while process.poll() is None and not stop.wait(.1):pass
            finally:
                if process.poll() is None:
                    if os.name=='posix':os.killpg(process.pid,signal.SIGINT)
                    else:process.terminate()
                    try:process.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        if os.name=='posix':os.killpg(process.pid,signal.SIGKILL)
                        else:process.kill()
                        process.wait(timeout=5)
            if stop.is_set() or process.returncode==0:return {'exit_code':0,'restarts':restarts,'stopped':stop.is_set()}
            if process.returncode==2:return {'exit_code':2,'restarts':restarts,'configuration_refused':True}
            if restarts>=max_restarts:return {'exit_code':70,'restarts':restarts,'restart_budget_exhausted':True}
            restarts+=1
            log.write(b'OpenPeople child exited; bounded restart scheduled.\n')
            if stop.wait(restart_delay):break
    return {'exit_code':0,'restarts':restarts,'stopped':True}
