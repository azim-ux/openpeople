"""Generate private Dex and HR-client configuration from reviewed user records."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service_config import configure_identity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('directory','certificate','key','ca','users'):parser.add_argument('--'+flag,required=True,type=Path)
    parser.add_argument('--origin',required=True);parser.add_argument('--issuer',required=True)
    args=parser.parse_args()
    if args.users.is_symlink() or args.users.stat().st_size>2000000 or (os.name=='posix' and args.users.stat().st_mode & 0o077):raise SystemExit('Supply an ordinary bounded private users JSON file (0600).')
    try:result=configure_identity(args.directory,args.origin,args.issuer,args.certificate,args.key,args.ca,json.loads(args.users.read_text()))
    except (ValueError,OSError):raise SystemExit('Configuration failed validation; check the private inputs, HTTPS addresses and certificates.') from None
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
