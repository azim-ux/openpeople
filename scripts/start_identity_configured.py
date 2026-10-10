"""Start an explicitly selected HR database with private generated SSO settings."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service_config import load_environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',required=True,type=Path);parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--public-origin',required=True);parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    try:settings=load_environment(args.settings)
    except (OSError,ValueError):raise SystemExit('Private identity settings are invalid; the HR server was not started.') from None
    env=os.environ.copy();env.update(settings)
    os.execve(sys.executable,[sys.executable,str(ROOT/'server.py'),'--db',str(args.db),'--port',str(args.port),'--public-origin',args.public_origin],env)


if __name__=='__main__':main()
