"""Technical production checks; never payroll approval or off-device evidence."""
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
import tomllib
from functools import lru_cache


@lru_cache(maxsize=1)
def version():
    return tomllib.loads((Path(__file__).parent/'pyproject.toml').read_text())['project']['version']


def production_boot_check(store,full_audit=True,check_destination=True):
    from workspace import setting
    from audit_integrity import verify
    from backup import backup_status
    checks={}
    parsed=urlsplit(store.public_origin or '')
    checks['trusted_https_origin']=parsed.scheme=='https' and bool(parsed.hostname) and not any((parsed.username,parsed.password,parsed.path,parsed.query,parsed.fragment))
    db=store.connect()
    try:
        db.execute('BEGIN')
        checks['schema_supported']=db.execute('PRAGMA user_version').fetchone()[0]==9
        if full_audit:
            checks['database_integrity']=db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            checks['foreign_key_integrity']=not db.execute('PRAGMA foreign_key_check').fetchall()
        checks['initialized_hr']=bool(db.execute("SELECT 1 FROM employees WHERE role='hr' AND status='Active' AND password IS NOT NULL AND is_sample=0").fetchone())
        checks['mandatory_mfa']=setting(db,'require_mfa',False) is True
        checks['administrators_enrolled']=checks['initialized_hr'] and not db.execute("SELECT 1 FROM employees WHERE role='hr' AND status='Active' AND is_sample=0 AND totp_secret IS NULL").fetchone()
        checks['no_demo_workers']=not db.execute('SELECT 1 FROM employees WHERE is_sample=1').fetchone()
        from core_hr import enabled, ROLES
        if enabled(store):
            checks['core_hr_roles_only']=not db.execute('SELECT 1 FROM employees WHERE status=\'Active\' AND role NOT IN (?,?,?,?)',ROLES).fetchone()
        if full_audit:checks['audit_integrity']=verify(db,maximum=None)['passed']
    finally:db.close()
    path=Path(store.db_path)
    checks['private_workspace_files']=os.name=='posix' and all(p.is_file() and not p.is_symlink() and p.stat().st_mode & 0o077==0 for p in (path,path.with_suffix('.key'))) and path.parent.stat().st_mode & 0o077==0
    status=backup_status(path,check_destination=check_destination)
    checks['scheduled_backup_configured']=status.get('configured',False) is True
    checks['backup_destination_available']=status.get('destination_available',False) is True
    checks['successful_backup_current']=checks['scheduled_backup_configured'] and not status.get('overdue',True) and not status.get('last_error')
    from core_hr import contract
    return {'scope':'Technical checks on this host only','product':contract(store),'full_database_check_performed':full_audit,'destination_check_cached':not check_destination,'checked_at':datetime.now(timezone.utc).isoformat(),'version':version(),'checks':checks,'passed':all(checks.values()),'off_device_recovery_verified':False,'enterprise_production_approved':False,
            'remaining_acceptance':['Actual second-network HTTPS collaboration','Independently held backup/passphrase and replacement-device restore','Applicable payroll rules and authority/provider acceptance','Host disk encryption, reboot operation, capacity and incident ownership']}


def api(handler,db,path,user):
    from server import APIError
    if path=='/api/health/live' and handler.command=='GET':return 200,{'status':'ok','version':version()},None
    if path=='/api/operations' and handler.command=='GET':
        handler.require_hr(user)
        # Full verification is a startup/offline job, not an unbounded HTTP job.
        return 200,production_boot_check(handler.server,full_audit=False,check_destination=False),None
    return None
