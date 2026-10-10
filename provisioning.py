"""Local operator bootstrap; no network calls or default credentials."""
import base64
import getpass
import secrets
import sys
from datetime import datetime
from pathlib import Path

from identity import check_totp
from localization import profile,zone
from server import APIError,HRStore,email_field,now,password_field,password_hash,text_field
from workspace import private_write,security_event,set_setting


def initialize_administrator(store,name,email,password,secret,otp,country):
    """Create exactly one owner only after verifying enrollment, in one transaction."""
    name=text_field({'name':name},'name',100)
    email=email_field({'email':email})
    password=password_field({'password':password})
    if len(password)<12:raise APIError(400,'Use a password with 12–128 characters.')
    international=profile({'country':country})
    try:
        if not isinstance(secret,str) or len(secret)!=32 or len(base64.b32decode(secret))!=20:
            raise ValueError()
        counter=check_totp(secret,otp)
    except (ValueError,TypeError):
        raise APIError(400,'The authenticator enrollment secret is invalid.') from None
    if counter is None:raise APIError(400,'Enter a current six-digit authenticator code.')
    encoded=password_hash(password)
    encrypted=store.vault.encrypt(secret.encode()).decode()
    started=datetime.now(zone(international)).date().isoformat()
    db=store.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        # Empty means empty: imported or sample accounts must not be overwritten.
        if db.execute('SELECT 1 FROM employees LIMIT 1').fetchone():
            raise APIError(409,'This workspace already contains accounts. Use its existing administrator or local recovery command.')
        owner=db.execute('INSERT INTO employees(name,email,title,department,location,start_date,role,password,country,currency,timezone,totp_secret,totp_counter) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (name,email,'HR Administrator','People & Culture','Local workspace',started,'hr',encoded,*international.values(),encrypted,counter)).lastrowid
        db.execute('INSERT INTO compensation(employee_id,effective_from,annual_salary,created_by,created_at) VALUES(?,?,?,?,?)',(owner,started,0,owner,now()))
        set_setting(db,'require_mfa',True)
        security_event(db,'Workspace initialized with verified authenticator',owner)
        db.commit()
    except BaseException:
        db.rollback();raise
    finally:db.close()
    store.bootstrap_token=''
    Path(store.db_path).with_suffix('.setup-token').unlink(missing_ok=True)
    return owner


def interactive_setup(db_path,name='Administrator',email='admin@openpeople.invalid',country='IN'):
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError('Run setup in an interactive terminal. Secret input through pipes or command arguments is not supported.')
    # Validate public options before creating any workspace files.
    text_field({'name':name},'name',100);email_field({'email':email});profile({'country':country})
    password=getpass.getpass('New administrator password (12–128 characters): ')
    confirm=getpass.getpass('Confirm password: ')
    if password!=confirm:raise ValueError('Passwords do not match.')
    if len(password)<12:raise ValueError('Use a password with 12–128 characters.')
    password_field({'password':password})
    store=HRStore(db_path)
    db=store.connect()
    try:
        if db.execute('SELECT 1 FROM employees LIMIT 1').fetchone():
            raise ValueError('This workspace already contains accounts. Use its existing administrator or local recovery command.')
    finally:db.close()
    secret=base64.b32encode(secrets.token_bytes(20)).decode()
    enrollment=Path(store.db_path).parent/('enrollment-'+secrets.token_hex(8)+'.private')
    private_write(enrollment,('OpenPeople authenticator enrollment\nAccount: '+email+'\nIssuer: OpenPeople\nSecret: '+secret+'\nType: TOTP / SHA1 / 6 digits / 30 seconds\nDelete any separate copy after enrolling.\n').encode())
    try:
        print('Open this private local file and add its secret to your authenticator: '+str(enrollment))
        otp=getpass.getpass('Current authenticator code: ')
        return initialize_administrator(store,name,email,password,secret,otp,country)
    finally:
        enrollment.unlink(missing_ok=True)
