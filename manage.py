"""Local administrator password recovery. Requires filesystem access to the DB."""
import argparse
import getpass
import sqlite3
from pathlib import Path
from server import ROOT, password_hash


def reset_password(db_path, email, password, disable_mfa=False):
    if len(password) < 12 or len(password) > 128:
        raise ValueError('Use a password with 12–128 characters.')
    if not Path(db_path).is_file():
        raise ValueError('Workspace database does not exist.')
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        from workspace import migrate, security_event
        migrate(db)
        db.commit()
        with db:
            row = db.execute('SELECT id FROM employees WHERE email=? COLLATE NOCASE', (email,)).fetchone()
            if not row:
                raise ValueError('Employee account not found.')
            db.execute('UPDATE employees SET password=? WHERE id=?', (password_hash(password), row[0]))
            db.execute('DELETE FROM sessions WHERE employee_id=?', (row[0],))
            db.execute('DELETE FROM mfa_recovery_codes WHERE employee_id=?',(row[0],))
            if disable_mfa:
                db.execute('UPDATE employees SET totp_secret=NULL,totp_pending=NULL,totp_counter=-1 WHERE id=?',(row[0],))
            security_event(db,'Local password recovery' + (' and authenticator reset' if disable_mfa else ''),row[0])
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reset a local OpenPeople account password and revoke its sessions.')
    parser.add_argument('email')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'openpeople.db')
    parser.add_argument('--disable-mfa',action='store_true',help='Reset a lost authenticator after verifying identity locally. Workspace MFA policy still applies.')
    args = parser.parse_args()
    password = getpass.getpass('New password (12–128 characters): ')
    confirm = getpass.getpass('Confirm password: ')
    try:
        if password != confirm:
            raise ValueError('Passwords do not match.')
        reset_password(args.db, args.email, password,args.disable_mfa)
        print('Password reset. Existing sessions have been revoked.')
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
