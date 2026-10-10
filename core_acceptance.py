"""Core HR installation evidence and replacement-directory recovery checks.

Evidence never asserts physical off-device custody or a production approval.
Reference files must be retained independently; checks cannot prove that custody.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from audit_integrity import verify
from scripts.deployment_check import check_endpoint, check_offline_workspace

TABLES = ('employees', 'compensation', 'leave', 'attendance', 'attendance_corrections',
          'tasks', 'holidays', 'leave_allocations', 'app_settings')


def business_digest(db):
    digest = hashlib.sha256()
    for table in TABLES:
        columns = [row['name'] for row in db.execute(f'PRAGMA table_info({table})')]
        # These fields are deliberately removed by restore and are not business canaries.
        columns = [name for name in columns if name not in ('totp_pending',)]
        selected = ','.join('"' + name + '"' for name in columns)
        for row in db.execute(f'SELECT {selected} FROM {table} ORDER BY ' + selected):
            digest.update(json.dumps([table, tuple(row)], ensure_ascii=True, separators=(',', ':')).encode())
            digest.update(b'\n')
    return digest.hexdigest()


def open_stopped(path):
    path = Path(path).resolve(strict=True)
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:raise ValueError('Stop the selected workspace before recording evidence.')
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    return db


def capture_reference(path):
    readiness = installation_check(path)
    if not readiness['passed']:raise ValueError('Offline installation checks must pass before capturing a recovery reference.')
    with closing(open_stopped(path)) as db:
        anchor = verify(db, maximum=None)
        digest = business_digest(db)
    return {'format': 'openpeople.core-reference.v1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'data_digest': digest, 'audit_anchor': anchor, 'schema': 9,
            'independent_custody_verified': False}


def installation_check(path):
    from core_hr import ROLES
    report = check_offline_workspace(path)
    with closing(open_stopped(path)) as db:
        checks = report['checks']
        checks['no_demo_workers'] = not db.execute('SELECT 1 FROM employees WHERE is_sample=1').fetchone()
        checks['all_active_hr_enrolled'] = not db.execute("SELECT 1 FROM employees WHERE role='hr' AND status='Active' AND totp_secret IS NULL").fetchone()
        checks['core_hr_roles_only'] = not db.execute("SELECT 1 FROM employees WHERE status='Active' AND role NOT IN (?,?,?,?)", ROLES).fetchone()
    report['passed'] = all(checks.values())
    report['product_profile_runtime_verified'] = False
    report['production_approved'] = False
    return report


def endpoint_check(origin, ca=True):
    report = check_endpoint(origin, ca)
    report['stage'] = 'Core HR HTTPS endpoint from this client'
    # check_endpoint obtains this from the TLS-verified session response.
    report['checks']['core_hr_profile'] = report.get('product_profile') == 'core-hr'
    report['passed'] = all(report['checks'].values())
    report['remote_network_verified'] = False
    return report


def recover_and_check(archive, destination, passphrase, reference, max_seconds):
    from backup import restore_backup, MAX_BYTES
    if not isinstance(reference, dict) or reference.get('format') != 'openpeople.core-reference.v1' or reference.get('schema') != 9 or not re.fullmatch(r'[0-9a-f]{64}', str(reference.get('data_digest', ''))):
        raise ValueError('Supply the independently retained Core HR recovery reference.')
    anchor = reference.get('audit_anchor')
    if not isinstance(anchor, dict) or anchor.get('format') != 'openpeople.audit-anchor.v1' or set(anchor.get('chains', {})) != {'audit', 'security_events'}:
        raise ValueError('The recovery reference must include both audit chains.')
    # Validate the entire anchor before creating a recovery destination.
    for chain in anchor['chains'].values():
        if not isinstance(chain, dict) or type(chain.get('count')) is not int or chain['count'] < 0 or type(chain.get('last_id')) is not int or chain['last_id'] < 0 or not re.fullmatch(r'[0-9a-f]{64}', str(chain.get('digest', ''))):
            raise ValueError('The recovery reference has an invalid audit chain.')
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not 0 < max_seconds <= 86400:
        raise ValueError('Choose a recovery objective between zero and 86400 seconds.')
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_BYTES + 1024 * 1024:
        raise ValueError('Choose an ordinary supported downloaded backup file.')
    # Hash the exact input before restoration; restore authenticates its encryption.
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    started = time.monotonic()
    restored = restore_backup(archive, destination, passphrase)
    checks = dict(installation_check(restored)['checks'])
    with closing(open_stopped(restored)) as db:
        from cryptography.fernet import Fernet, InvalidToken
        vault = Fernet(restored.with_suffix('.key').read_bytes())
        checks['authenticator_secrets_decryptable'] = True
        for row in db.execute('SELECT totp_secret FROM employees WHERE totp_secret IS NOT NULL'):
            try:vault.decrypt(row['totp_secret'].encode())
            except InvalidToken:checks['authenticator_secrets_decryptable'] = False
        checks['independent_reference_matches'] = business_digest(db) == reference['data_digest']
        checks['retained_audit_anchor_matches'] = verify(db, anchor, maximum=None)['passed']
        checks['reusable_credentials_removed'] = all(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0 for table in ('sessions', 'oidc_states', 'idempotency', 'mfa_recovery_codes'))
        checks['pending_authenticator_removed'] = not db.execute('SELECT 1 FROM employees WHERE totp_pending IS NOT NULL').fetchone()
    elapsed = time.monotonic() - started
    checks['recovery_time_objective_met'] = elapsed <= max_seconds
    return {'stage': 'Recovery into a new directory on this computer', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'checks': checks, 'passed': all(checks.values()), 'archive_sha256': checksum,
            'restoration_seconds': round(elapsed, 3), 'recovery_objective_seconds': max_seconds,
            'restored_database': str(restored), 'off_device_recovery_verified': False,
            'authenticated_workflows_verified': False, 'production_approved': False,
            'remaining_acceptance': ['Separately held archive, reference and passphrase', 'Original physical host unavailable',
                                     'Fresh MFA login and two-device collaboration', 'Elapsed download and service restart time']}


def write_evidence(path, report):
    from workspace import private_write
    path = Path(path)
    if not path.parent.is_dir() or path.parent.is_symlink():raise ValueError('Choose an existing private evidence directory.')
    import os
    if os.name == 'posix' and path.parent.stat().st_mode & 0o077:raise ValueError('Keep evidence in an owner-only directory (0700).')
    private_write(path, (json.dumps(report, indent=2) + '\n').encode())
