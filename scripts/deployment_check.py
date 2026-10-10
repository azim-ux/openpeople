"""Read-only deployment checks; run from the host and a teammate's computer.

Network mode never signs in or writes an HR record. Offline mode refuses an
active WAL and opens SQLite immutable/read-only, without creating side files.
Passing these checks is not payroll certification or an off-device restore.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

import requests


def check_endpoint(origin, ca=True):
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Use the exact HTTPS origin, without credentials or a path.')
    client = requests.Session()
    client.trust_env = False
    checks = {}
    try:
        response = client.get(origin + '/api/session', timeout=(5, 10), verify=ca, allow_redirects=False)
        checks['https_certificate_verified'] = True
        checks['session_endpoint_available'] = response.status_code == 200
        data = response.json() if response.status_code == 200 else {}
        checks['workspace_initialized'] = data.get('setup_required') is False
        checks['hsts_enabled'] = 'max-age=' in response.headers.get('Strict-Transport-Security', '').lower()
        checks['no_content_sniffing'] = response.headers.get('X-Content-Type-Options') == 'nosniff'
        checks['frame_embedding_blocked'] = "frame-ancestors 'none'" in response.headers.get('Content-Security-Policy', '')
        checks['private_response_not_cached'] = 'no-store' in response.headers.get('Cache-Control', '')
        denied = client.get(origin + '/api/state', timeout=(5, 10), verify=ca, allow_redirects=False)
        checks['unauthenticated_hr_data_denied'] = denied.status_code == 401 and 'employees' not in denied.json()
    except (requests.RequestException, ValueError):
        checks['endpoint_request_completed'] = False
    finally:
        client.close()
    return {'scope': 'Unauthenticated HTTPS checks from this client', 'product_profile': data.get('product', {}).get('profile') if 'data' in locals() else None, 'checks': checks, 'passed': bool(checks) and all(checks.values()), 'authenticated_workflows_verified': False, 'off_device_recovery_verified': False}


def check_offline_workspace(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Choose an existing workspace database.')
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Stop the server cleanly before the offline check; a WAL contains pending database state.')
    checks = {}
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1',uri=True)
    db.row_factory = sqlite3.Row
    try:
        checks['schema_supported'] = db.execute('PRAGMA user_version').fetchone()[0] == 9
        checks['database_integrity'] = db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        checks['foreign_key_integrity'] = not db.execute('PRAGMA foreign_key_check').fetchall()
        from audit_integrity import verify
        checks['audit_chains_verified'] = verify(db,maximum=None)['passed'] if checks['schema_supported'] else False
        checks['workspace_initialized'] = bool(db.execute("SELECT count(*) FROM employees WHERE is_sample=0 AND role='hr' AND status='Active'").fetchone()[0])
        policy = db.execute("SELECT value FROM app_settings WHERE key='require_mfa'").fetchone()
        checks['workspace_requires_mfa'] = bool(policy and json.loads(policy[0]) is True)
        checks['active_hr_has_authenticator'] = db.execute("SELECT count(*) FROM employees WHERE is_sample=0 AND role='hr' AND status='Active' AND totp_secret IS NOT NULL").fetchone()[0] > 0
        if os.name == 'posix':
            checks['database_private_permissions'] = path.stat().st_mode & 0o077 == 0
            checks['directory_private_permissions'] = path.parent.stat().st_mode & 0o077 == 0
            key = path.with_suffix('.key')
            checks['private_encryption_key_present'] = key.is_file() and key.stat().st_mode & 0o077 == 0
    finally:
        db.close()
    return {'scope': 'Stopped local workspace; immutable SQLite read only', 'checks': checks, 'passed': bool(checks) and all(checks.values()), 'cloud_upload_verified': False, 'disk_encryption_verified': False, 'windows_acl_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--origin', help='Exact HTTPS origin to check from this client.')
    group.add_argument('--db', type=Path, help='Explicit stopped workspace to check without modifying it.')
    parser.add_argument('--ca', type=Path, help='Explicit trusted CA PEM for your deployment; never disables verification.')
    arguments = parser.parse_args()
    try:
        result = check_endpoint(arguments.origin, str(arguments.ca) if arguments.ca else True) if arguments.origin else check_offline_workspace(arguments.db)
        result['enterprise_production_approved'] = False
        result['remaining_acceptance'] = ['Second-device authenticated collaboration', 'Provider-downloaded backup restored on a replacement computer', 'Actual identity-provider tenant when used', 'Jurisdiction-specific payroll validation when used']
        print(json.dumps(result, indent=2))
        return 0 if result['passed'] else 1
    except (OSError, ValueError, sqlite3.DatabaseError) as error:
        # No employee details, secrets or database contents in diagnostics.
        parser.exit(1, 'Deployment check could not complete: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
