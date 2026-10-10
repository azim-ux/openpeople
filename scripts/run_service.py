"""Run one explicitly selected OpenPeople host with bounded crash restarts."""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backup import process_lock
from service_runner import supervise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--public-origin')
    parser.add_argument('--production',action='store_true')
    parser.add_argument('--profile',choices=('core-hr','full'))
    parser.add_argument('--max-restarts',type=int,default=3)
    args=parser.parse_args();path=args.db.resolve(strict=True)
    command=[sys.executable,'-u',str(ROOT/'server.py'),'--db',str(path),'--host','127.0.0.1','--port',str(args.port)]
    if args.public_origin:command+=['--public-origin',args.public_origin]
    if args.production:command+=['--production']
    if args.profile:command+=['--profile',args.profile]
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        with process_lock(path,'service',timeout=.1):result=supervise(command,path.with_suffix('.service.log'),args.max_restarts,stop=stop)
    except (OSError,ValueError):parser.exit(2,'Service refused. Check the private directory, selected workspace, restart limit and existing supervisor.\n')
    print(json.dumps(result));return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
