"""Record private Core HR installation, HTTPS or recovery evidence."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core_acceptance import capture_reference, endpoint_check, installation_check, recover_and_check, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='stage', required=True)
    install = commands.add_parser('installation', help='Check a stopped workspace without modifying it.')
    install.add_argument('--db', type=Path, required=True)
    reference = commands.add_parser('reference', help='Capture a stopped-workspace data fingerprint and audit anchor.')
    reference.add_argument('--db', type=Path, required=True)
    endpoint = commands.add_parser('endpoint', help='Run from each actual client; verifies TLS and the Core HR profile.')
    endpoint.add_argument('--origin', required=True)
    endpoint.add_argument('--ca', type=Path)
    recovery = commands.add_parser('recovery', help='Restore a downloaded archive to a new directory and compare independent evidence.')
    recovery.add_argument('--archive', type=Path, required=True)
    recovery.add_argument('--destination', type=Path, required=True)
    recovery.add_argument('--reference', type=Path, required=True)
    recovery.add_argument('--max-seconds', type=float, default=300)
    for command in (install, reference, endpoint, recovery):
        command.add_argument('--output', type=Path, required=True, help='New 0600 JSON file in an existing owner-only directory.')
    args = parser.parse_args()
    try:
        # Refuse an existing report before network access or recovery writes.
        if args.output.exists() or args.output.is_symlink():raise ValueError('Choose a new evidence file; previous evidence is never replaced.')
        if not args.output.parent.is_dir() or args.output.parent.is_symlink() or os.name == 'posix' and args.output.parent.stat().st_mode & 0o077:
            raise ValueError('Create an owner-only evidence directory first (0700).')
        if args.stage == 'reference':result = capture_reference(args.db)
        elif args.stage == 'installation':result = installation_check(args.db)
        elif args.stage == 'endpoint':result = endpoint_check(args.origin, str(args.ca) if args.ca else True)
        else:
            if not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError('Run recovery in an interactive terminal; secrets are never command arguments.')
            if args.reference.is_symlink() or args.reference.stat().st_size > 65536:raise ValueError('Choose an ordinary bounded recovery reference file.')
            value = json.loads(args.reference.read_text())
            result = recover_and_check(args.archive, args.destination, getpass.getpass('Separately retained recovery passphrase: '), value, args.max_seconds)
        result['production_approved'] = False
        write_evidence(args.output, result)
        print(json.dumps({'stage':args.stage, 'technical_checks_passed':result.get('passed'), 'evidence_written':True,
                          'production_approved':False, 'off_device_recovery_verified':False}))
        return 0 if result.get('passed', args.stage == 'reference') else 1
    except (OSError, ValueError, sqlite3.DatabaseError):
        parser.exit(1, 'Acceptance could not complete. Check selected paths, private permissions, stopped-workspace state, TLS, reference and passphrase. No production approval was issued.\n')
    except (KeyboardInterrupt, EOFError):parser.exit(1, 'Acceptance interrupted. Check the selected recovery destination before retrying.\n')


if __name__ == '__main__':raise SystemExit(main())
