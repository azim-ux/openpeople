"""Verify a stopped database against an independently retained audit anchor."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_integrity import verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--anchor',type=Path,help='Earlier anchor kept outside this database/host')
    args=parser.parse_args()
    path=args.database.resolve(strict=True)
    wal=Path(str(path)+'-wal')
    if wal.exists() and wal.stat().st_size:raise SystemExit('Stop the selected server cleanly before immutable verification.')
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
    try:result=verify(db,json.loads(args.anchor.read_text()) if args.anchor else None,maximum=None)
    finally:db.close()
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
