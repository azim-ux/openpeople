"""OpenPeople: local HR collaboration. Python 3.12+; CLI served by Waitress."""
import argparse
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import socket
import sys
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))
STAGES = ('Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected')
SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 title TEXT NOT NULL, department TEXT NOT NULL, location TEXT NOT NULL,
 annual_salary INTEGER NOT NULL DEFAULT 0, start_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Active', role TEXT NOT NULL DEFAULT 'employee',
 password TEXT, is_sample INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS leave (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, reason TEXT NOT NULL,
 days INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', reviewed_by INTEGER,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attendance (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 work_date TEXT NOT NULL, check_in TEXT NOT NULL, check_out TEXT,
 UNIQUE(employee_id, work_date));
CREATE TABLE IF NOT EXISTS candidates (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, position TEXT NOT NULL,
 stage TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS goals (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 title TEXT NOT NULL, due_date TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 description TEXT NOT NULL, amount_paise INTEGER NOT NULL, category TEXT NOT NULL,
 expense_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', reviewed_by INTEGER,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES employees(id),
 action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, created_at TEXT NOT NULL);
"""


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return salt + ':' + digest


def password_matches(password, encoded):
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


DUMMY_PASSWORD_HASH = password_hash('non-account dummy verification value')


def valid_unicode(value):
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise APIError(400, 'Text must contain valid Unicode characters.')
    return value


def text_field(data, key, maximum=200, optional=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value.strip()) > maximum or (not optional and not value.strip()):
        raise APIError(400, f'Enter a valid {key.replace("_", " ")} (maximum {maximum} characters).')
    return valid_unicode(value.strip())


def email_field(data):
    email = text_field(data, 'email', 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise APIError(400, 'Enter a valid email address.')
    return email


def password_field(data, optional=False):
    value = data.get('password', '')
    if not isinstance(value, str) or len(value) > 128 or (not optional and not value):
        raise APIError(400, 'Enter a valid password of at most 128 characters.')
    return valid_unicode(value)


def date_field(data, key):
    value = text_field(data, key, 10)
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
    except ValueError:
        raise APIError(400, f'Enter a valid {key.replace("_", " ")}.')
    return parsed


def choice(data, key, allowed):
    value = text_field(data, key)
    if value not in allowed:
        raise APIError(400, f'Choose a valid {key.replace("_", " ")}.')
    return value


def integer(data, key, minimum=0, maximum=1000000000):
    value = data.get(key)
    if type(value) is not int or not minimum <= value <= maximum:
        raise APIError(400, f'{key.replace("_", " ").capitalize()} must be between {minimum} and {maximum}.')
    return value


def now():
    return datetime.now(IST).isoformat(timespec='seconds')


def seed(db):
    people = [
        ('Aarav Mehta', 'aarav@example.org', 'Engineering Lead', 'Engineering', 'Bengaluru', 2400000),
        ('Priya Shah', 'priya@example.org', 'People Partner', 'People & Culture', 'Mumbai', 1440000),
        ('Kabir Rao', 'kabir@example.org', 'Product Designer', 'Design', 'Bengaluru', 1800000),
        ('Ananya Iyer', 'ananya@example.org', 'Finance Analyst', 'Finance', 'Mumbai', 960000),
        ('Rohan Das', 'rohan@example.org', 'Software Engineer', 'Engineering', 'Hyderabad', 1560000),
        ('Meera Kapoor', 'meera@example.org', 'Customer Success Lead', 'Operations', 'Delhi', 1200000),
        ('Dev Patel', 'dev@example.org', 'Software Engineer', 'Engineering', 'Bengaluru', 1680000),
        ('Sara Fernandes', 'sara@example.org', 'Talent Specialist', 'People & Culture', 'Mumbai', 1080000),
    ]
    today = datetime.now(IST).date()
    for i, person in enumerate(people):
        cursor = db.execute('INSERT INTO employees(name,email,title,department,location,annual_salary,start_date,is_sample) VALUES(?,?,?,?,?,?,?,1)', (*person, (today - timedelta(days=30 * (i + 1))).isoformat()))
        emp = cursor.lastrowid
        for title in ('Complete employee profile', 'Review company policies', 'Finish team orientation'):
            db.execute('INSERT INTO tasks(employee_id,title,done) VALUES(?,?,?)', (emp, title, int(i < 6)))
        db.execute('INSERT INTO goals(employee_id,title,due_date,progress) VALUES(?,?,?,?)', (emp, ['Deliver quarterly team priorities', 'Complete professional development'][i % 2], (today + timedelta(days=60)).isoformat(), [65, 40, 80, 25][i % 4]))
    db.execute('INSERT INTO candidates(name,email,position,stage,created_at,is_sample) VALUES(?,?,?,?,?,1)', ('Nisha Verma', 'nisha@example.org', 'Senior Software Engineer', 'Interview', now()))
    db.execute('INSERT INTO candidates(name,email,position,stage,created_at,is_sample) VALUES(?,?,?,?,?,1)', ('Aditya Singh', 'aditya@example.org', 'Product Designer', 'Screening', now()))
    db.execute('INSERT INTO candidates(name,email,position,stage,created_at,is_sample) VALUES(?,?,?,?,?,1)', ('Tara Nair', 'tara@example.org', 'Finance Analyst', 'Offer', now()))
    start = today + timedelta(days=(7 - today.weekday()) % 7 + 7)
    db.execute('INSERT INTO leave(employee_id,type,start_date,end_date,reason,days,created_at) VALUES(?,?,?,?,?,?,?)', (1, 'Annual', start.isoformat(), (start + timedelta(days=2)).isoformat(), 'Family holiday', 3, now()))
    db.execute('INSERT INTO expenses(employee_id,description,amount_paise,category,expense_date,created_at) VALUES(?,?,?,?,?,?)', (4, 'Travel to team workshop', 185000, 'Travel', today.isoformat(), now()))


class HRStore:
    def __init__(self, db_path, public_origin=None, port=8000, product_profile='full'):
        from core_hr import PROFILES
        if product_profile not in PROFILES:raise ValueError('Choose the core-hr or full product profile.')
        self.product_profile = product_profile
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        if Path(db_path).is_symlink():
            raise ValueError('Use a private database file, not a symbolic link.')
        os.chmod(Path(db_path).parent, 0o700)
        descriptor = os.open(db_path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        os.chmod(db_path, 0o600)
        self.request_timeout = 5
        self.public_origin = public_origin
        self.server_port = port
        self.rate_lock = threading.Lock()
        self.rates = defaultdict(deque)
        # Provider I/O must not occupy every shared HTTP worker. Admission is
        # nonblocking; callbacks share the same budget as sign-in starts.
        self.sso_slots = threading.BoundedSemaphore(2)
        self.backup_job_lock = threading.Lock()
        self.backup_threads = []
        self.instance_id = secrets.token_hex(16)
        db = self.connect()
        try:
            db.executescript(SCHEMA)
            db.execute('PRAGMA journal_mode=WAL')
            from workspace import migrate
            migrate(db)
            db.commit()
        finally:
            db.close()
        self.allowed_hosts = {f'127.0.0.1:{self.server_port}', f'localhost:{self.server_port}'}
        if public_origin:
            parsed = urlsplit(public_origin)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError('Remote access requires an HTTPS origin with no path.')
            self.allowed_hosts = {parsed.netloc.lower()}
        from workspace import initialize_private_files
        self.bootstrap_token = initialize_private_files(self)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=5)
        db.row_factory = sqlite3.Row
        from audit_integrity import register
        register(db)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def throttle(self, ip, path):
        bucket = 'auth' if path in ('/api/login', '/api/setup') else 'mfa' if path.startswith('/api/mfa/') else 'sso' if path.startswith('/api/sso/') else 'api'
        limit = {'auth':10, 'mfa':10, 'sso':30, 'api':180}[bucket]
        with self.rate_lock:
            key = (ip, bucket)
            recent = self.rates[key]
            cutoff = time.time() - 60
            while recent and recent[0] < cutoff:
                recent.popleft()
            if len(recent) >= limit:
                raise APIError(429, 'Too many requests. Try again in a minute.')
            recent.append(time.time())


class HRServer(HRStore, ThreadingHTTPServer):
    """Disposable integration-test server; the CLI uses Waitress."""
    daemon_threads = True

    def __init__(self, address, db_path, public_origin=None):
        HRStore.__init__(self, db_path, public_origin, address[1])
        ThreadingHTTPServer.__init__(self, address, Handler)
        if not public_origin:
            self.allowed_hosts = {f'127.0.0.1:{self.server_port}',f'localhost:{self.server_port}'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'OpenPeople'

    def log_message(self, *args):
        pass  # Never log request bodies, passwords, session cookies, or HR data.

    def setup(self):
        self.request.settimeout(self.server.request_timeout)
        super().setup()

    def respond(self, status, body, content_type='application/json; charset=utf-8', cookie=None):
        raw = json.dumps(body).encode() if content_type.startswith('application/json') else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        if status == 303:
            self.send_header('Location', body['redirect'])
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError()
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, 'Send a JSON object smaller than 16 KB.')
        except (TimeoutError, socket.timeout):
            raise APIError(408, 'The request body was not received in time.')

    def session(self, db):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['openpeople_session'].value if 'openpeople_session' in cookie else ''
        except Exception:
            token = ''
        digest = hashlib.sha256(token.encode()).hexdigest()
        return db.execute('SELECT e.*, s.csrf, s.token, s.last_seen, s.expires AS session_expires, s.auth_time, s.mfa_verified FROM sessions s JOIN employees e ON e.id=s.employee_id WHERE s.token=? AND s.expires>? AND s.last_seen>? AND e.status=?', (digest, time.time(), time.time()-1800, 'Active')).fetchone()

    def new_session(self, db, employee_id, mfa_verified=True):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        db.execute('INSERT INTO sessions(token,employee_id,csrf,expires,last_seen,auth_time,mfa_verified,public_id) VALUES(?,?,?,?,?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), employee_id, csrf, time.time() + 28800, time.time(), time.time(), int(mfa_verified),secrets.token_hex(16)))
        return csrf, f'openpeople_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800' + ('; Secure' if self.server.public_origin else '')

    def require_hr(self, user):
        if user['role'] != 'hr':
            raise APIError(403, 'HR access is required for this action.')

    def owner(self, data, user):
        value = data.get('employee_id', user['id'])
        if type(value) is not int or not 1 <= value <= 9223372036854775807:
            raise APIError(400, 'Choose an employee.')
        if value != user['id'] and user['role'] != 'hr':
            raise APIError(403, 'You can only submit your own records.')
        return value

    def active_employee(self, db, employee_id):
        if not db.execute('SELECT id FROM employees WHERE id=? AND status=?', (employee_id, 'Active')).fetchone():
            raise APIError(400, 'Choose an active employee.')

    def audit(self, db, user, action, entity, entity_id):
        from workspace import audit_change
        audit_change(db, user, action, entity, entity_id, getattr(self, 'before_row', None))
        self.before_row = None

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PATCH(self):
        self.dispatch()

    def dispatch(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        host = self.headers.get('Host', '').lower()
        if host not in self.server.allowed_hosts:
            return self.respond(403, {'error': 'This hostname is not allowed.'})
        if not path.startswith('/api/'):
            allowed = {'/': 'index.html', '/app.js': 'app.js', '/team.js': 'team.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg'}
            filename = allowed.get(path)
            if self.command != 'GET' or filename is None or not (ROOT / 'public' / filename).is_file():
                return self.respond(404, {'error': 'Page not found.'})
            return self.respond(200, (ROOT / 'public' / filename).read_bytes(), mimetypes.guess_type(filename)[0] or 'application/octet-stream')
        db = None
        user = None
        sso_admitted = False
        self.after_commit = None
        self.after_rollback = None
        try:
            self.server.throttle(self.client_address[0], path)
            if path in ('/api/sso/start', '/api/sso/callback') and self.command == 'GET':
                if not self.server.sso_slots.acquire(blocking=False):
                    raise APIError(503, 'Sign-in service is busy. Try again shortly.')
                sso_admitted = True
            db = self.server.connect()
            self.failed_login_logged = False
            if self.command != 'GET':
                origin = self.headers.get('Origin')
                expected_origin = self.server.public_origin or 'http://' + host
                if origin and origin != expected_origin:
                    raise APIError(403, 'Request origin is not allowed.')
            data = self.body() if self.command != 'GET' else {}
            user = self.session(db)
            auth_path = path in ('/api/session', '/api/setup', '/api/login', '/api/countries', '/api/sso/start', '/api/sso/callback', '/api/health/live')
            if not auth_path:
                if not user:
                    raise APIError(401, 'Sign in to continue.')
                supplied_csrf = self.headers.get('X-CSRF-Token', '')
                if self.command != 'GET' and (not supplied_csrf.isascii() or not hmac.compare_digest(supplied_csrf, user['csrf'])):
                    raise APIError(403, 'Your session could not be verified. Refresh and try again.')
            self.prepared_login = None
            if path == '/api/login' and self.command == 'POST':
                email, password = email_field(data), password_field(data)
                account=hashlib.sha256(email.encode()).hexdigest()
                if db.execute('SELECT count(*) FROM auth_failures WHERE account=? AND attempt>?',(account,time.time()-300)).fetchone()[0]>=10:raise APIError(429,'Too many sign-in attempts. Try again in five minutes.')
                employee = db.execute('SELECT * FROM employees WHERE email=? AND status=?', (email, 'Active')).fetchone()
                encoded = employee['password'] if employee and employee['password'] else DUMMY_PASSWORD_HASH
                matched = password_matches(password, encoded)
                if not employee or not employee['password'] or not matched:
                    from workspace import security_event
                    security_event(db, 'Login failed', employee['id'] if employee else None, self.client_address[0])
                    db.execute('DELETE FROM auth_failures WHERE attempt<?',(time.time()-300,))
                    db.execute('INSERT INTO auth_failures VALUES(?,?)',(account,time.time()))
                    db.commit()
                    self.failed_login_logged = True
                    raise APIError(401, 'Email or password is incorrect.')
                self.prepared_login = employee
            if self.command != 'GET':
                db.execute('BEGIN IMMEDIATE')
                if user:
                    user = self.session(db)  # Recheck lifecycle after acquiring the transaction.
                    if not user:
                        raise APIError(401, 'Sign in again.')
            if user and self.command!='GET' and not path.startswith('/api/sso/') and time.time()-user['last_seen'] > 60:
                db.execute('UPDATE sessions SET last_seen=? WHERE token=?', (time.time(), user['token']))
            from workspace import require_mfa, idempotent_result, save_idempotent_result
            require_mfa(db, user, path)
            from core_hr import enforce
            enforce(self.server, path, self.command, data, parse_qs(parsed.query))
            replay = idempotent_result(db, user, path, self.command, data, self.headers.get('Idempotency-Key'))
            if replay:
                db.commit()
                return self.respond(replay[0], replay[1])
            if path in ('/api/session', '/api/setup', '/api/login'):
                status, result, cookie = self.auth(db, path, data, user)
            else:
                status, result, cookie = self.api(db, path, parse_qs(parsed.query), data, user)
            save_idempotent_result(db, user, path, self.command, data, self.headers.get('Idempotency-Key'), status, result)
            db.commit()
            self.after_rollback=None
            if getattr(self,'after_commit',None):self.after_commit()
            self.respond(status, result, cookie=cookie)
        except APIError as error:
            if db:
                db.rollback()
                if path=='/api/login' and error.status==401 and not getattr(self,'failed_login_logged',False):
                    from workspace import security_event
                    employee=getattr(self,'prepared_login',None)
                    security_event(db,'Login factor failed',employee['id'] if employee else None,self.client_address[0])
                    db.execute('INSERT INTO auth_failures VALUES(?,?)',(hashlib.sha256(email_field(data).encode()).hexdigest(),time.time()))
                    db.commit()
                elif path=='/api/mfa/verify' and error.status==401:
                    from workspace import security_event
                    security_event(db,'Authenticator verification failed',user['id'] if user else None,self.client_address[0])
                    db.commit()
                elif path=='/api/sso/callback' and error.status in (401,403):
                    from workspace import security_event
                    security_event(db,'SSO login failed',None,self.client_address[0])
                    db.commit()
                elif error.status in (403,428,429):
                    from workspace import security_event
                    security_event(db,'Access denied' if error.status==403 else 'Rate limit reached' if error.status==429 else 'Missing edit precondition',user['id'] if user else None,self.client_address[0],{'path':path,'method':self.command,'status':error.status})
                    db.commit()
            self.respond(error.status, {'error': error.message})
        except sqlite3.IntegrityError:
            if db:
                db.rollback()
            self.respond(409, {'error': 'A record with these details already exists.'})
        except Exception:
            if db:
                db.rollback()
            logging.exception('Unexpected application error')
            self.respond(500, {'error': 'Unable to complete the request. Please try again.'})
        finally:
            if self.after_rollback:self.after_rollback()
            if db:
                db.close()
            if sso_admitted:
                self.server.sso_slots.release()

    def auth(self, db, path, data, user):
        setup_required = not db.execute('SELECT id FROM employees WHERE password IS NOT NULL LIMIT 1').fetchone()
        if path == '/api/session' and self.command == 'GET':
            from workspace import setting
            from core_hr import contract
            return 200, {'setup_required': setup_required, 'user': self.public_user(user), 'csrf': user['csrf'] if user else None, 'mfa_setup_required': bool(user and setting(db, 'require_mfa', False) and not user['totp_secret']), 'mfa_verify_required': bool(user and user['totp_secret'] and not user['mfa_verified']), 'sso_enabled': bool(os.environ.get('OPENPEOPLE_OIDC_ISSUER')), 'product': contract(self.server)}, None
        if path == '/api/setup' and self.command == 'POST':
            if not setup_required:
                raise APIError(409, 'This workspace has already been set up.')
            supplied_setup = self.headers.get('X-Setup-Token', '')
            if not supplied_setup.isascii() or not hmac.compare_digest(supplied_setup, self.server.bootstrap_token):
                raise APIError(403, 'Enter the one-time setup token from the local server.')
            name, email = text_field(data, 'name', 100), email_field(data)
            password = password_field(data)
            if len(password) < 12:
                raise APIError(400, 'Use a password with at least 12 characters.')
            include_samples = data.get('include_samples', False)
            if type(include_samples) is not bool:
                raise APIError(400, 'Sample records must be enabled or disabled.')
            if include_samples:
                seed(db)
            cursor = db.execute('INSERT INTO employees(name,email,title,department,location,start_date,role,password) VALUES(?,?,?,?,?,?,?,?)', (name, email, 'HR Administrator', 'People & Culture', 'Mumbai', datetime.now(IST).date().isoformat(), 'hr', password_hash(password)))
            db.execute('INSERT INTO compensation(employee_id,effective_from,annual_salary,created_by,created_at) VALUES(?,?,?,?,?)',(cursor.lastrowid,datetime.now(IST).date().isoformat(),0,cursor.lastrowid,now()))
            from localization import profile
            international=profile(data)
            if 'work_week' in data:
                from localization import validate_work_week
                db.execute('UPDATE employees SET work_week=? WHERE id=?',(json.dumps(validate_work_week(data['work_week'])),cursor.lastrowid))
            db.execute('UPDATE employees SET country=?,currency=?,timezone=? WHERE id=?',(*international.values(),cursor.lastrowid))
            csrf, cookie = self.new_session(db, cursor.lastrowid)
            from workspace import security_event
            security_event(db, 'Workspace initialized', cursor.lastrowid, self.client_address[0])
            return 201, {'csrf': csrf}, cookie
        if path == '/api/login' and self.command == 'POST':
            employee = db.execute('SELECT * FROM employees WHERE id=? AND status=?', (self.prepared_login['id'], 'Active')).fetchone()
            if not employee or employee['password'] != self.prepared_login['password']:
                raise APIError(401, 'Email or password is incorrect.')
            from identity import verify_login_factor
            from workspace import security_event, setting
            verify_login_factor(db, self.server, employee, data.get('otp', ''),data.get('recovery_code'))
            needs_setup = bool(setting(db, 'require_mfa', False) and not employee['totp_secret'])
            csrf, cookie = self.new_session(db, employee['id'], not needs_setup)
            security_event(db, 'Login succeeded', employee['id'], self.client_address[0])
            db.execute('DELETE FROM auth_failures WHERE account=?',(hashlib.sha256(employee['email'].encode()).hexdigest(),))
            return 200, {'csrf': csrf, 'mfa_setup_required': needs_setup}, cookie
        raise APIError(404, 'Endpoint not found.')

    def public_user(self, user):
        return {key: user[key] for key in ('id', 'name', 'email', 'role', 'department', 'manager_id','country','currency','timezone')} if user else None

    def state(self, db, user):
        hr = user['role'] == 'hr'
        manager = user['role'] == 'manager'
        columns = 'id,name,email,title,department,location,start_date,end_date,status,role,is_sample,manager_id,version,country,currency,timezone,work_week' + (',annual_salary' if user['role'] in ('hr', 'payroll') else '')
        result = {'user': self.public_user(user), 'today': datetime.now(IST).astimezone(__import__('localization').zone(user)).date().isoformat(), 'timezone': user['timezone'], 'currency': user['currency'],'country':user['country']}
        result['employees'] = [dict(row) for row in db.execute(f'SELECT {columns} FROM employees ORDER BY name')]
        for worker in result['employees']:worker['work_week']=json.loads(worker['work_week'])
        from access import entities
        permitted=entities(db,user)
        if permitted is not None:
            scoped_workers={r[0] for r in db.execute('SELECT employee_id,legal_entity_id FROM employee_assignments') if r[1] in permitted}
            for worker in result['employees']:
                if worker['id'] not in scoped_workers:worker.pop('annual_salary',None)
        if user['role'] in ('hr','payroll'):
            from workspace import salary_on
            for employee in result['employees']:
                if 'annual_salary' in employee:employee['annual_salary']=salary_on(db,employee['id'],result['today'],employee['annual_salary'])
        result['session']={'last_activity':user['last_seen'],'absolute_expires':user['session_expires']}
        for table in ('leave', 'attendance', 'tasks', 'goals', 'expenses'):
            query = f'SELECT t.*, e.name AS employee_name FROM {table} t JOIN employees e ON e.id=t.employee_id'
            scoped = '' if hr else (' WHERE (t.employee_id=? OR e.manager_id=?)' if manager else ' WHERE t.employee_id=?')
            params = () if hr else ((user['id'], user['id']) if manager else (user['id'],))
            result[table] = [dict(row) for row in db.execute(query + scoped + ' ORDER BY t.id DESC', params)]
        result['candidates'] = [dict(row) for row in db.execute('SELECT * FROM candidates ORDER BY id DESC')] if user['role'] in ('hr', 'recruiter') else []
        result['audit'] = [dict(row) for row in db.execute('SELECT a.*, e.name AS actor_name FROM audit a JOIN employees e ON a.actor_id=e.id ORDER BY a.id DESC LIMIT 100')] if user['role'] in ('hr', 'auditor') else []
        from workspace import extra_state
        result.update(extra_state(db, user, self.server))
        from core_hr import project_state
        return project_state(self.server, result)

    def api(self, db, path, query, data, user):
        method = self.command
        from workspace import extension_api
        extended = extension_api(self, db, path, query, data, user)
        if extended is not None:
            return extended
        if path == '/api/state' and method == 'GET':
            return 200, self.state(db, user), None
        if path == '/api/logout' and method == 'POST':
            from workspace import security_event
            security_event(db, 'Logout', user['id'], self.client_address[0])
            db.execute('DELETE FROM sessions WHERE token=?', (user['token'],))
            return 200, {'ok': True}, 'openpeople_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
        if path == '/api/payroll' and method == 'GET':
            month = query.get('month', [datetime.now(IST).strftime('%Y-%m')])[0]
            from workspace import payroll_preview
            return 200, payroll_preview(db,user,month), None
        if method == 'POST' and path in ('/api/employees', '/api/leave', '/api/attendance', '/api/candidates', '/api/goals', '/api/expenses'):
            return self.create(db, path.split('/')[-1], data, user)
        match = re.fullmatch(r'/api/(employees|leave|candidates|tasks|goals|expenses)/(\d+)', path)
        if method == 'PATCH' and match:
            if len(match[2]) > 19 or not 1 <= int(match[2]) <= 9223372036854775807:
                raise APIError(400, 'Choose a valid record identifier.')
            return self.update(db, match[1], int(match[2]), data, user)
        raise APIError(404, 'Endpoint not found.')

    def create(self, db, entity, data, user):
        if entity == 'employees':
            self.require_hr(user)
        if entity == 'candidates' and user['role'] not in ('hr', 'recruiter'):
            raise APIError(403, 'Recruitment access is required.')
        if entity == 'employees':
            from localization import profile
            profile(data)
            values = [text_field(data, 'name', 100), email_field(data), text_field(data, 'title', 100), text_field(data, 'department', 100), text_field(data, 'location', 100), integer(data, 'annual_salary'), date_field(data, 'start_date').isoformat()]
            password = password_field(data, optional=True)
            if password and len(password) < 12:
                raise APIError(400, 'Use a password with at least 12 characters.')
            cursor = db.execute('INSERT INTO employees(name,email,title,department,location,annual_salary,start_date,password) VALUES(?,?,?,?,?,?,?,?)', (*values, password_hash(password) if password else None))
            from localization import profile
            international=profile(data)
            db.execute('UPDATE employees SET country=?,currency=?,timezone=? WHERE id=?',(*international.values(),cursor.lastrowid))
            from workspace import update_employment_access
            if 'work_week' in data:
                from localization import validate_work_week
                db.execute('UPDATE employees SET work_week=? WHERE id=?',(json.dumps(validate_work_week(data['work_week'])),cursor.lastrowid))
            update_employment_access(db, cursor.lastrowid, data, user)
            db.execute('INSERT INTO compensation(employee_id,effective_from,annual_salary,created_by,created_at) VALUES(?,?,?,?,?)',(cursor.lastrowid,values[6],values[5],user['id'],now()))
            for title in ('Complete employee profile', 'Review company policies', 'Finish team orientation'):
                db.execute('INSERT INTO tasks(employee_id,title) VALUES(?,?)', (cursor.lastrowid, title))
        elif entity == 'candidates':
            cursor = db.execute('INSERT INTO candidates(name,email,position,stage,created_at) VALUES(?,?,?,?,?)', (text_field(data, 'name', 100), email_field(data), text_field(data, 'position', 100), choice(data, 'stage', STAGES), now()))
        else:
            emp = self.owner(data, user)
            self.active_employee(db, emp)
            if entity == 'leave':
                from workspace import validate_leave
                fields=validate_leave(db,emp,data)
                cursor = db.execute('INSERT INTO leave(employee_id,type,start_date,end_date,reason,days,charge_dates,created_at) VALUES(?,?,?,?,?,?,?,?)', (emp,fields['type'],fields['start_date'],fields['end_date'],fields['reason'],fields['days'],fields['charge_dates'],now()))
                from workspace import set_approval_policy
                set_approval_policy(db, 'leave', cursor.lastrowid)
            elif entity == 'attendance':
                if emp != user['id']:
                    raise APIError(403, 'You can only record your own attendance.')
                action = choice(data, 'action', ('in', 'out'))
                from localization import zone
                stamp=datetime.now(IST).astimezone(zone(user))
                today=stamp.date().isoformat()
                existing = db.execute('SELECT * FROM attendance WHERE employee_id=? AND check_out IS NULL AND requires_correction=0 ORDER BY id DESC LIMIT 1', (emp,)).fetchone()
                if action == 'in':
                    if existing:
                        raise APIError(409, 'Finish your open attendance session before checking in again.')
                    cursor = db.execute('INSERT INTO attendance(employee_id,work_date,check_in) VALUES(?,?,?)', (emp, today, stamp.isoformat(timespec='seconds')))
                else:
                    if not existing or existing['check_out']:
                        raise APIError(409, 'There is no open check-in.')
                    self.before_row=dict(existing)
                    db.execute('UPDATE attendance SET check_out=?,version=version+1 WHERE id=?', (stamp.isoformat(timespec='seconds'), existing['id']))
                    self.audit(db, user, 'Checked out', entity, existing['id'])
                    return 200, {'id': existing['id']}, None
            elif entity == 'goals':
                cursor = db.execute('INSERT INTO goals(employee_id,title,due_date) VALUES(?,?,?)', (emp, text_field(data, 'title', 200), date_field(data, 'due_date').isoformat()))
            elif entity == 'expenses':
                from workspace import validate_expense
                currency=db.execute('SELECT currency FROM employees WHERE id=?',(emp,)).fetchone()[0]
                values=validate_expense(db,data,currency)
                cursor=db.execute('INSERT INTO expenses(employee_id,description,amount_paise,category,expense_date,receipt_reference,currency,created_at) VALUES(?,?,?,?,?,?,?,?)',(emp,values['description'],values['amount_paise'],values['category'],values['expense_date'],values['receipt_reference'],currency,now()))
                from workspace import set_approval_policy
                set_approval_policy(db, 'expenses', cursor.lastrowid)
        self.audit(db, user, 'Created', entity, cursor.lastrowid)
        return 201, {'id': cursor.lastrowid}, None

    def update(self, db, entity, entity_id, data, user):
        if entity == 'employees':
            self.require_hr(user)
        if entity == 'candidates' and user['role'] not in ('hr', 'recruiter'):
            raise APIError(403, 'Recruitment access is required.')
        row = db.execute(f'SELECT * FROM {entity} WHERE id=?', (entity_id,)).fetchone()
        if not row:
            raise APIError(404, 'Record not found.')
        self.before_row = dict(row)
        from workspace import may_manage_employee
        if entity in ('tasks', 'goals') and row['employee_id'] != user['id'] and not may_manage_employee(db, user, row['employee_id']):
            raise APIError(403, 'You can only update your own records.')
        if entity == 'employees':
            fields = {}
            if any(key in data for key in ('country','currency','timezone')):
                from localization import profile
                international=profile(data,row)
                if international['currency']!=row['currency'] and (row['annual_salary'] or db.execute('SELECT id FROM expenses WHERE employee_id=? UNION ALL SELECT id FROM pay_results WHERE employee_id=? LIMIT 1',(entity_id,entity_id)).fetchone()):raise APIError(409,'Existing financial records retain their currency. Create a separately reviewed employment record for a currency transfer.')
                fields.update(international)
            if 'work_week' in data:
                from localization import validate_work_week
                fields['work_week']=json.dumps(validate_work_week(data['work_week']))
            for key in ('name', 'title', 'department', 'location'):
                if key in data:
                    fields[key] = text_field(data, key, 100)
            if 'email' in data:fields['email']=email_field(data)
            if 'start_date' in data:fields['start_date']=date_field(data,'start_date').isoformat()
            if 'end_date' in data:
                fields['end_date']=date_field(data,'end_date').isoformat() if data['end_date'] else None
            if (fields.get('end_date',row['end_date']) or '9999-12-31')<fields.get('start_date',row['start_date']):
                raise APIError(400,'Employment end date cannot precede the start date.')
            if 'annual_salary' in data:
                fields['annual_salary'] = integer(data, 'annual_salary')
            if 'status' in data:
                fields['status'] = choice(data, 'status', ('Active', 'Inactive'))
                if entity_id == user['id'] and fields['status'] == 'Inactive':
                    raise APIError(400, 'You cannot deactivate your own HR account.')
            if not fields:
                if not any(key in data for key in ('role', 'manager_id')):
                    raise APIError(400, 'Provide an employee field to update.')
            if 'expected_version' not in data:raise APIError(428,'Reload this employee before editing; a record version is required.')
            if integer(data,'expected_version',1)!=row['version']:
                raise APIError(409,'This employee was changed by a teammate. Reopen the form and review the latest values before saving.')
            if fields.get('status')=='Inactive' and not fields.get('end_date',row['end_date']):
                fields['end_date']=datetime.now(IST).astimezone(__import__('localization').zone(row)).date().isoformat()
            if fields.get('status')=='Active' and row['status']=='Inactive' and 'end_date' not in data:
                fields['end_date']=None
            if fields:
                employer=db.execute('SELECT l.country,l.currency FROM employee_assignments a JOIN legal_entities l ON l.id=a.legal_entity_id WHERE a.employee_id=?',(entity_id,)).fetchone()
                if employer and (fields.get('country',row['country']),fields.get('currency',row['currency']))!=(employer['country'],employer['currency']):
                    raise APIError(409,'Remove the existing employer assignment before changing this worker’s country or currency. Payroll snapshots retain their original assignment.')
                db.execute('UPDATE employees SET ' + ','.join(f'{key}=?' for key in fields) + ' WHERE id=?', (*fields.values(), entity_id))
            from workspace import update_employment_access
            update_employment_access(db, entity_id, data, user)
            db.execute('UPDATE employees SET version=version+1 WHERE id=?',(entity_id,))
            if 'email' in fields and fields['email']!=row['email']:
                db.execute('DELETE FROM sessions WHERE employee_id=?',(entity_id,))
                from workspace import security_event
                security_event(db,'Account email corrected',entity_id,self.client_address[0])
            if 'start_date' in fields and fields['start_date']!=row['start_date']:
                db.execute('UPDATE compensation SET effective_from=? WHERE employee_id=? AND effective_from=?',(fields['start_date'],entity_id,row['start_date']))
            if 'annual_salary' in fields:
                effective=date_field(data,'effective_date').isoformat() if data.get('effective_date') else datetime.now(IST).astimezone(__import__('localization').zone(row)).date().isoformat()
                if effective<fields.get('start_date',row['start_date']):raise APIError(400,'Compensation cannot take effect before employment starts.')
                old_compensation=db.execute('SELECT * FROM compensation WHERE employee_id=? AND effective_from=?',(entity_id,effective)).fetchone()
                db.execute('INSERT INTO compensation(employee_id,effective_from,annual_salary,created_by,created_at) VALUES(?,?,?,?,?) ON CONFLICT(employee_id,effective_from) DO UPDATE SET annual_salary=excluded.annual_salary,created_by=excluded.created_by,created_at=excluded.created_at',(entity_id,effective,fields['annual_salary'],user['id'],now()))
                compensation_id=db.execute('SELECT id FROM compensation WHERE employee_id=? AND effective_from=?',(entity_id,effective)).fetchone()[0]
                from workspace import audit_change
                audit_change(db,user,'Compensation changed','compensation',compensation_id,dict(old_compensation) if old_compensation else None)
            if fields.get('status') == 'Inactive':
                db.execute('DELETE FROM sessions WHERE employee_id=?', (entity_id,))
        elif entity in ('leave', 'expenses'):
            if entity=='expenses' and 'reconciliation_reference' in data:
                self.require_hr(user)
                if row['employee_id']==user['id']:raise APIError(403,'A different HR reviewer must reconcile your expense.')
                if row['status']!='Approved' or row['reconciled_on']:raise APIError(409,'Only an approved, unreconciled expense can be reconciled.')
                db.execute('UPDATE expenses SET reconciled_on=?,reconciliation_reference=? WHERE id=?',(now(),text_field(data,'reconciliation_reference',500),entity_id))
                self.audit(db,user,'Reconciled',entity,entity_id)
                return 200,{'id':entity_id,'status':'Approved'},None
            if 'status' not in data:
                if row['employee_id']!=user['id']:raise APIError(403,'Only the owner can amend a pending request.')
                if row['status']!='Pending':raise APIError(409,'Only a pending request can be amended. Request cancellation before resubmitting approved leave.')
                from workspace import validate_leave,validate_expense
                amended={**dict(row),**data}
                if entity=='leave':
                    if 'half_day' not in amended:amended['half_day']=row['days']==0.5
                    values=validate_leave(db,row['employee_id'],amended,entity_id)
                else:
                    from localization import currency_digits
                    amended['amount']=data.get('amount',row['amount_paise']/10**currency_digits(row['currency']))
                    values=validate_expense(db,amended,row['currency'])
                    text_field(data,'reason',500)
                db.execute(f'UPDATE {entity} SET '+','.join(f'{key}=?' for key in values)+',manager_reviewed_by=NULL WHERE id=?',(*values.values(),entity_id))
                self.audit(db,user,'Amended',entity,entity_id)
                return 200,{'id':entity_id,'status':'Pending'},None
            status = choice(data, 'status', ('Approved', 'Rejected','Cancelled'))
            if status=='Cancelled':
                if entity=='expenses' and row['reconciled_on']:raise APIError(409,'A reconciled expense needs a separately recorded reversal, not cancellation.')
                if row['employee_id']!=user['id']:raise APIError(403,'Only the request owner can initiate cancellation.')
                if row['status'] not in ('Pending','Approved'):raise APIError(409,'This request cannot be cancelled in its current state.')
                cancel_status='Cancelled' if row['status']=='Pending' else 'Cancellation pending'
                db.execute(f'UPDATE {entity} SET status=?,cancel_reason=?,manager_reviewed_by=NULL WHERE id=?',(cancel_status,text_field(data,'reason',500),entity_id))
                self.audit(db,user,cancel_status,entity,entity_id)
                return 200,{'id':entity_id,'status':cancel_status},None
            if row['status'] not in ('Pending','Cancellation pending'):
                raise APIError(409, 'This request has already been reviewed.')
            from workspace import approve_request
            approve_request(db, entity, row, status, user)
        elif entity == 'candidates':
            db.execute('UPDATE candidates SET stage=? WHERE id=?', (choice(data, 'stage', STAGES), entity_id))
        elif entity == 'tasks':
            if type(data.get('done')) is not bool:
                raise APIError(400, 'Task completion must be true or false.')
            db.execute('UPDATE tasks SET done=? WHERE id=?', (int(data['done']), entity_id))
        elif entity == 'goals':
            db.execute('UPDATE goals SET progress=? WHERE id=?', (integer(data, 'progress', 0, 100), entity_id))
        action = data['status'] if entity in ('leave', 'expenses') else 'Updated'
        self.audit(db, user, action, entity, entity_id)
        result={'id':entity_id}
        if entity in ('leave','expenses'):
            saved=db.execute(f'SELECT status,manager_reviewed_by FROM {entity} WHERE id=?',(entity_id,)).fetchone()
            result.update(dict(saved))
        return 200, result, None


def create_server(host='127.0.0.1', port=8000, db_path=None, public_origin=None):
    return HRServer((host, port), db_path or ROOT / 'data' / 'openpeople.db', public_origin)


if __name__ == '__main__':
    sys.modules.setdefault('server',sys.modules[__name__])
    parser = argparse.ArgumentParser(description='Run OpenPeople locally.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'openpeople.db')
    parser.add_argument('--public-origin', help='Exact HTTPS origin of your local reverse proxy, e.g. https://hr.internal')
    parser.add_argument('--production',action='store_true',help='Refuse launch unless HTTPS, mandatory MFA, private files and current scheduled backups pass technical checks.')
    parser.add_argument('--profile',choices=('core-hr','full'),help='Production defaults to core-hr; local testing defaults to the full feature preview.')
    args = parser.parse_args()
    if args.host not in ('127.0.0.1','localhost','::1'):
        parser.error('Keep the backend on loopback. Use an HTTPS reverse proxy and --public-origin for remote access.')
    from serving import serve_workspace
    try:
        serve_workspace(args.db,args.host,args.port,args.public_origin,args.production,args.profile)
    except KeyboardInterrupt:
        pass
    except ValueError as error:
        parser.error(str(error))
