"""Interactive operator enrollment. Does not publish or upload any information."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from provisioning import interactive_setup
from server import APIError,ROOT


def main():
    parser=argparse.ArgumentParser(description='Set up an empty local workspace with a private password and verified authenticator. No email is sent.')
    parser.add_argument('--db',type=Path,default=ROOT/'data'/'openpeople.db')
    parser.add_argument('--name',default='Administrator')
    parser.add_argument('--login',default='admin@openpeople.invalid',help='Local email-format login identifier; a personal email is not required.')
    parser.add_argument('--country',default='IN',help='Worker profile country code; not a statutory payroll engine.')
    args=parser.parse_args()
    try:
        interactive_setup(args.db,args.name,args.login,args.country)
        print('Administrator created with mandatory MFA. No samples or sessions were created.')
        print('Next configure encrypted scheduled backups, HTTPS and remote access; run the technical deployment checks before production launch.')
    except (ValueError,APIError) as error:parser.exit(1,(error.message if isinstance(error,APIError) else str(error))+'\n')
    except (KeyboardInterrupt,EOFError):parser.exit(1,'Setup interrupted. Temporary enrollment material was removed; check workspace status before retrying.\n')


if __name__=='__main__':main()
