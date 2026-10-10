"""Read-only local health or stopped-workspace technical production diagnostic."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from operations import production_boot_check


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--db',type=Path);group.add_argument('--origin');parser.add_argument('--ca',type=Path)
    args=parser.parse_args()
    try:
        if args.db:
            path=args.db.resolve(strict=True);wal=Path(str(path)+'-wal')
            if wal.exists() and wal.stat().st_size:raise ValueError('Stop the selected server before immutable database checks.')
            class ReadOnlyStore:
                db_path=str(path)
                public_origin=None
                def connect(self):
                    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row;return db
            # This offline command cannot attest to a deployed HTTPS origin.
            result=production_boot_check(ReadOnlyStore())
        else:
            parsed=urlsplit(args.origin)
            if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not parsed.hostname or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1'))):raise ValueError('Use a verified HTTPS origin or this computer\'s exact loopback HTTP origin.')
            client=requests.Session();client.trust_env=False
            try:
                response=client.get(args.origin+'/api/health/live',timeout=(3,5),verify=str(args.ca) if args.ca else True,allow_redirects=False)
                payload=response.json();passed=response.status_code==200 and set(payload)=={'status','version'} and payload['status']=='ok'
                result={'scope':'Unauthenticated liveness only','passed':passed,'version':payload.get('version'),'https_transport':parsed.scheme=='https','enterprise_production_approved':False}
            finally:client.close()
        print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
    except (OSError,ValueError,sqlite3.DatabaseError,requests.RequestException):parser.exit(1,'Health check could not complete. Check the selected path/origin and private service logs.\n')


if __name__=='__main__':raise SystemExit(main())
