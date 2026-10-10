"""Workspace migrations, permission rules, and HR team capabilities."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import calendar
from datetime import date,datetime,timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROLES = ('employee', 'manager', 'hr', 'recruiter', 'payroll', 'auditor')
POLICIES = ('hr_only', 'manager_or_hr', 'manager_then_hr')


def execute_schema(db,script):
    # These are static DDL statements. Avoid executescript's implicit COMMIT.
    for statement in script.split(';'):
        if statement.strip():db.execute(statement)


def migrate(db):
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version>9:
        raise ValueError('This workspace needs a newer OpenPeople release.')
    from audit_integrity import register
    register(db)
    if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
    additions = {
        'employees': {'manager_id': 'INTEGER REFERENCES employees(id)', 'totp_secret': 'TEXT', 'totp_pending': 'TEXT', 'totp_counter': 'INTEGER NOT NULL DEFAULT -1','version':'INTEGER NOT NULL DEFAULT 1','end_date':'TEXT','country':"TEXT NOT NULL DEFAULT 'IN'",'currency':"TEXT NOT NULL DEFAULT 'INR'",'timezone':"TEXT NOT NULL DEFAULT 'Asia/Kolkata'",'work_week':"TEXT NOT NULL DEFAULT '[0,1,2,3,4]'"},
        'sessions': {'last_seen': 'REAL NOT NULL DEFAULT 0', 'auth_time': 'REAL NOT NULL DEFAULT 0', 'mfa_verified': 'INTEGER NOT NULL DEFAULT 1','public_id':'TEXT'},
        'audit': {'details': "TEXT NOT NULL DEFAULT '{}'"},
        'leave': {'approval_policy': "TEXT NOT NULL DEFAULT 'hr_only'", 'manager_reviewed_by': 'INTEGER','charge_dates':'TEXT','cancel_reason':'TEXT'},
        'expenses': {'approval_policy': "TEXT NOT NULL DEFAULT 'hr_only'", 'manager_reviewed_by': 'INTEGER','cancel_reason':'TEXT','receipt_reference':"TEXT NOT NULL DEFAULT ''",'reconciled_on':'TEXT','reconciliation_reference':'TEXT','currency':"TEXT NOT NULL DEFAULT 'INR'"},
        'security_events': {'details': "TEXT NOT NULL DEFAULT '{}'"},
        'candidates':{'is_sample':'INTEGER NOT NULL DEFAULT 0'},
        'benefit_enrollments': {'status':"TEXT NOT NULL DEFAULT 'Active'",'ended_on':'TEXT'},
        'pay_runs': {'version': 'INTEGER NOT NULL DEFAULT 1'},
    }
    for table, columns in additions.items():
        existing = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
        if not existing:continue
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    if version<2:
        db.execute('DELETE FROM sessions')  # Legacy sessions did not carry current lifecycle/MFA guarantees.
    execute_schema(db,"""
    CREATE TABLE IF NOT EXISTS auth_failures(account TEXT NOT NULL,attempt REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS auth_failure_lookup ON auth_failures(account,attempt);
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS idempotency(employee_id INTEGER NOT NULL,path TEXT NOT NULL,key TEXT NOT NULL,fingerprint TEXT NOT NULL,status INTEGER NOT NULL,result TEXT NOT NULL,expires REAL NOT NULL,PRIMARY KEY(employee_id,path,key));
    CREATE TABLE IF NOT EXISTS security_events(id INTEGER PRIMARY KEY,actor_id INTEGER,action TEXT NOT NULL,address TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS oidc_states(state TEXT PRIMARY KEY,nonce TEXT NOT NULL,verifier TEXT NOT NULL,expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS oidc_links(issuer TEXT NOT NULL,subject TEXT NOT NULL,employee_id INTEGER NOT NULL REFERENCES employees(id),PRIMARY KEY(issuer,subject));
    CREATE TABLE IF NOT EXISTS mfa_recovery_codes(employee_id INTEGER NOT NULL REFERENCES employees(id),digest TEXT NOT NULL,PRIMARY KEY(employee_id,digest));
    CREATE TABLE IF NOT EXISTS benefit_plans(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,monthly_cost_paise INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS benefit_enrollments(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),plan_id INTEGER NOT NULL REFERENCES benefit_plans(id),created_at TEXT NOT NULL,UNIQUE(employee_id,plan_id));
    CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,url TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS course_assignments(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),course_id INTEGER NOT NULL REFERENCES courses(id),due_date TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Assigned',completed_at TEXT,UNIQUE(employee_id,course_id));
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),message TEXT NOT NULL,created_at TEXT NOT NULL,seen INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS pay_runs(id INTEGER PRIMARY KEY,month TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'Draft',created_by INTEGER NOT NULL REFERENCES employees(id),reviewed_by INTEGER,created_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS pay_results(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES pay_runs(id),employee_id INTEGER NOT NULL REFERENCES employees(id),employee_name TEXT NOT NULL,department TEXT NOT NULL,gross_paise INTEGER NOT NULL,deductions_paise INTEGER NOT NULL DEFAULT 0,deduction_note TEXT NOT NULL DEFAULT '',UNIQUE(run_id,employee_id));
    CREATE TABLE IF NOT EXISTS pay_run_editors(run_id INTEGER NOT NULL REFERENCES pay_runs(id),employee_id INTEGER NOT NULL REFERENCES employees(id),PRIMARY KEY(run_id,employee_id));
    """)
    if version < 4:
        # Preserve separation of duties for drafts edited before this upgrade.
        # Keep every editor; another edit must not erase earlier participation.
        db.execute("INSERT OR IGNORE INTO pay_run_editors(run_id,employee_id) SELECT p.run_id,a.actor_id FROM audit a JOIN pay_results p ON p.id=a.entity_id JOIN pay_runs r ON r.id=p.run_id JOIN employees e ON e.id=a.actor_id WHERE a.entity='pay_results' AND a.action='Updated' AND r.status='Draft'")
    if 'details' not in {row['name'] for row in db.execute('PRAGMA table_info(security_events)')}:
        db.execute("ALTER TABLE security_events ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
    for row in db.execute('SELECT token FROM sessions WHERE public_id IS NULL').fetchall():db.execute('UPDATE sessions SET public_id=? WHERE token=?',(secrets.token_hex(16),row['token']))
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS session_public_id ON sessions(public_id)')
    for table,columns in {'pay_results':{'calculation':"TEXT NOT NULL DEFAULT '{}'",'currency':"TEXT NOT NULL DEFAULT 'INR'",'country':"TEXT NOT NULL DEFAULT 'IN'",'external_result':"TEXT NOT NULL DEFAULT ''"},'benefit_plans':{'enrollment_opens':'TEXT','enrollment_closes':'TEXT','currency':"TEXT NOT NULL DEFAULT 'INR'"}}.items():
        existing={row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
        for column,definition in columns.items():
            if column not in existing:db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    for column,definition in additions['benefit_enrollments'].items():
        if column not in {row['name'] for row in db.execute('PRAGMA table_info(benefit_enrollments)')}:
            db.execute(f'ALTER TABLE benefit_enrollments ADD COLUMN {column} {definition}')
    if version<3:
        execute_schema(db,"""
        CREATE TABLE attendance_v3(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),work_date TEXT NOT NULL,check_in TEXT NOT NULL,check_out TEXT,break_minutes INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,requires_correction INTEGER NOT NULL DEFAULT 0);
        INSERT INTO attendance_v3(id,employee_id,work_date,check_in,check_out) SELECT id,employee_id,work_date,check_in,check_out FROM attendance;
        DROP TABLE attendance;
        ALTER TABLE attendance_v3 RENAME TO attendance;
        UPDATE attendance SET requires_correction=1 WHERE check_out IS NULL AND id NOT IN (SELECT max(id) FROM attendance WHERE check_out IS NULL GROUP BY employee_id);
        CREATE UNIQUE INDEX one_open_attendance ON attendance(employee_id) WHERE check_out IS NULL AND requires_correction=0;
        """)
    execute_schema(db,"""
    CREATE TABLE IF NOT EXISTS compensation(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),effective_from TEXT NOT NULL,annual_salary INTEGER NOT NULL,created_by INTEGER,created_at TEXT NOT NULL,UNIQUE(employee_id,effective_from));
    CREATE TABLE IF NOT EXISTS holidays(id INTEGER PRIMARY KEY,date TEXT NOT NULL,name TEXT NOT NULL,country TEXT NOT NULL DEFAULT '*',UNIQUE(date,country));
    CREATE TABLE IF NOT EXISTS leave_allocations(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),year INTEGER NOT NULL,type TEXT NOT NULL,days REAL NOT NULL,carryover REAL NOT NULL DEFAULT 0,reason TEXT NOT NULL,UNIQUE(employee_id,year,type));
    CREATE TABLE IF NOT EXISTS attendance_corrections(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),attendance_id INTEGER NOT NULL REFERENCES attendance(id),expected_version INTEGER NOT NULL,check_in TEXT NOT NULL,check_out TEXT,break_minutes INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Pending',approval_policy TEXT NOT NULL DEFAULT 'manager_or_hr',manager_reviewed_by INTEGER,reviewed_by INTEGER,created_by INTEGER NOT NULL REFERENCES employees(id),created_at TEXT NOT NULL);
    PRAGMA user_version=9;
    """)
    if 'country' not in {row['name'] for row in db.execute('PRAGMA table_info(holidays)')}:
        execute_schema(db,"""
        CREATE TABLE holidays_scoped(id INTEGER PRIMARY KEY,date TEXT NOT NULL,name TEXT NOT NULL,country TEXT NOT NULL DEFAULT '*',UNIQUE(date,country));
        INSERT INTO holidays_scoped(id,date,name) SELECT id,date,name FROM holidays;
        DROP TABLE holidays;
        ALTER TABLE holidays_scoped RENAME TO holidays;
        """)
    from enterprise import schema as enterprise_schema
    enterprise_schema(db)
    from pay_periods import schema as period_schema
    period_schema(db)
    from access import schema as access_schema
    access_schema(db)
    from audit_integrity import schema as audit_schema
    audit_schema(db)
    db.execute("INSERT OR IGNORE INTO compensation(employee_id,effective_from,annual_salary,created_at) SELECT id,start_date,annual_salary,datetime('now') FROM employees")


def private_write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        # Exclusive creation above succeeded: remove only this new partial file.
        # An existing file fails at os.open and never enters this cleanup path.
        Path(path).unlink(missing_ok=True)
        raise


def initialize_private_files(server):
    from cryptography.fernet import Fernet
    key_path = Path(server.db_path).with_suffix('.key')
    if not key_path.exists():
        private_write(key_path, Fernet.generate_key())
    if key_path.is_symlink():
        raise ValueError('Workspace key cannot be a symbolic link.')
    os.chmod(key_path, 0o600)
    server.vault = Fernet(key_path.read_bytes())
    db = server.connect()
    try:
        configured = db.execute('SELECT id FROM employees WHERE password IS NOT NULL LIMIT 1').fetchone()
    finally:
        db.close()
    token_path = Path(server.db_path).with_suffix('.setup-token')
    if configured:
        return ''
    if not token_path.exists():
        private_write(token_path, secrets.token_urlsafe(32).encode())
    if token_path.is_symlink():
        raise ValueError('Setup token cannot be a symbolic link.')
    os.chmod(token_path, 0o600)
    return token_path.read_text().strip()


def setting(db, key, default=None):
    row = db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    return json.loads(row['value']) if row else default


def set_setting(db, key, value):
    db.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))


def policy_values(db):
    return {key:setting(db,key,default) for key,default in (
        ('leave_policy','manager_or_hr'),('expenses_policy','manager_or_hr'),('require_mfa',False),
        ('leave_limits',{'Annual':24,'Sick':12,'Personal':6}),('leave_accrual','annual'),
        ('expense_policies',{}),('expenses_limit_paise',10000000),('receipt_required_above_paise',250000))}


def salary_on(db,employee,day,fallback=0):
    row=db.execute('SELECT annual_salary FROM compensation WHERE employee_id=? AND effective_from<=? ORDER BY effective_from DESC LIMIT 1',(employee,day)).fetchone()
    return row['annual_salary'] if row else fallback


def charged_dates(row):
    if row['charge_dates']:return json.loads(row['charge_dates'])
    start,end=date.fromisoformat(row['start_date']),date.fromisoformat(row['end_date'])
    dates=[(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1) if (start+timedelta(days=i)).weekday()<5]
    return dates


def leave_budget(db,employee,kind,year,asof=None,exclude_id=None):
    limits=setting(db,'leave_limits',{'Annual':24,'Sick':12,'Personal':6})
    allocation=db.execute('SELECT * FROM leave_allocations WHERE employee_id=? AND year=? AND type=?',(employee,year,kind)).fetchone()
    entitled=None if kind=='Unpaid' else limits.get(kind,0)
    if allocation:entitled=allocation['days']+allocation['carryover']
    elif entitled is not None and setting(db,'leave_accrual','annual')=='monthly':
        asof=asof or date.today()
        joined=date.fromisoformat(db.execute('SELECT start_date FROM employees WHERE id=?',(employee,)).fetchone()['start_date'])
        first=max(date(year,1,1),joined)
        months=max(0,min(12,(min(asof,date(year,12,31)).year-first.year)*12+min(asof,date(year,12,31)).month-first.month+1))
        entitled=float((Decimal(str(entitled))*months/12*2).to_integral_value(rounding='ROUND_FLOOR')/2)
    used=0
    for row in db.execute("SELECT * FROM leave WHERE employee_id=? AND type=? AND status IN ('Pending','Approved','Cancellation pending')",(employee,kind)):
        if row['id']==exclude_id:continue
        dates=charged_dates(row)
        fraction=row['days']/len(dates) if dates else 0
        used+=sum(day.startswith(str(year)+'-') for day in dates)*fraction
    return {'employee_id':employee,'year':year,'type':kind,'entitlement':entitled,'reserved_and_used':used,'remaining':None if entitled is None else entitled-used}


def validate_leave(db,employee,data,exclude_id=None):
    from server import APIError,date_field,choice,text_field
    start,end=date_field(data,'start_date'),date_field(data,'end_date')
    if end<start or (end-start).days>365:raise APIError(400,'Leave must span at most one year with valid ordered dates.')
    if type(data.get('half_day',False)) is not bool:raise APIError(400,'Half-day selection must be a boolean.')
    if data.get('half_day') and start!=end:raise APIError(400,'A half-day request must have a single date.')
    worker=db.execute('SELECT country,work_week FROM employees WHERE id=?',(employee,)).fetchone()
    work_week=json.loads(worker['work_week'])
    holidays={row['date'] for row in db.execute("SELECT date FROM holidays WHERE date>=? AND date<=? AND country IN ('*',?)",(start.isoformat(),end.isoformat(),worker['country']))}
    dates=[(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1) if (start+timedelta(days=i)).weekday() in work_week and (start+timedelta(days=i)).isoformat() not in holidays]
    if not dates:raise APIError(400,'Select at least one working day outside company holidays.')
    kind=choice(data,'type',('Annual','Sick','Personal','Unpaid'));fraction=0.5 if data.get('half_day') else 1
    overlap=db.execute("SELECT id FROM leave WHERE employee_id=? AND status IN ('Pending','Approved','Cancellation pending') AND start_date<=? AND end_date>=? AND id<>?",(employee,end.isoformat(),start.isoformat(),exclude_id or -1)).fetchone()
    if overlap:raise APIError(409,'This request overlaps an existing pending or approved leave request.')
    for year in range(start.year,end.year+1):
        budget=leave_budget(db,employee,kind,year,end,exclude_id)
        requested=sum(day.startswith(str(year)+'-') for day in dates)*fraction
        if budget['remaining'] is not None and requested>budget['remaining']:
            raise APIError(400,f'This request exceeds the available {kind.lower()} leave balance for {year}. Ask HR to review the allocation.')
    return {'type':kind,'start_date':start.isoformat(),'end_date':end.isoformat(),'reason':text_field(data,'reason',1000),'days':len(dates)*fraction,'charge_dates':json.dumps(dates)}


def validate_expense(db,data,currency='INR'):
    from server import APIError,text_field,choice,date_field
    from decimal import InvalidOperation
    from localization import currency_digits
    digits=currency_digits(currency);factor=10**digits
    try:
        amount=Decimal(str(data.get('amount')))
        if not amount.is_finite() or not Decimal('0.01')<=amount<=10000000 or amount.as_tuple().exponent<-digits:raise InvalidOperation()
    except (InvalidOperation,ValueError):raise APIError(400,'Enter an amount from ₹0.01 to ₹10,000,000 with at most two decimal places.')
    paise=int(amount*factor);receipt=text_field(data,'receipt_reference',500,optional=True)
    policies=setting(db,'expense_policies',{})
    policy=policies.get(currency,{})
    limit=policy.get('expenses_limit_paise',setting(db,'expenses_limit_paise',10000000) if currency=='INR' else 100000*factor)
    receipt_limit=policy.get('receipt_required_above_paise',setting(db,'receipt_required_above_paise',250000) if currency=='INR' else 2500*factor)
    if paise>limit:raise APIError(400,'This claim exceeds the workspace expense limit. Ask HR to review the policy.')
    if paise>receipt_limit and not receipt:raise APIError(400,'A secure receipt reference is required for this amount.')
    return {'description':text_field(data,'description',500),'amount_paise':paise,'category':choice(data,'category',('Travel','Meals','Equipment','Other')),'expense_date':date_field(data,'expense_date').isoformat(),'receipt_reference':receipt,'currency':currency}


def security_event(db, action, actor_id, address='local', details=None):
    from server import now
    db.execute('INSERT INTO security_events(actor_id,action,address,created_at,details) VALUES(?,?,?,?,?)', (actor_id, action, address, now(),json.dumps(details or {})))
    set_setting(db,'revision',setting(db,'revision',0)+1)


def require_mfa(db, user, path):
    from server import APIError
    allowed = ('/api/session', '/api/logout', '/api/security', '/api/mfa/begin', '/api/mfa/confirm', '/api/mfa/verify')
    if user and (user['totp_secret'] or setting(db, 'require_mfa', False)) and not user['mfa_verified'] and path not in allowed:
        raise APIError(403, 'Enroll an authenticator before continuing.')


def fingerprint(method, data):
    return hashlib.sha256((method + json.dumps(data, sort_keys=True, separators=(',', ':'))).encode()).hexdigest()


def idempotent_result(db, user, path, method, data, key):
    from server import APIError
    if not key or not user or method == 'GET' or path.startswith(('/api/mfa/', '/api/sso/')):
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', key):
        raise APIError(400, 'Use a valid submission identifier.')
    row = db.execute('SELECT * FROM idempotency WHERE employee_id=? AND path=? AND key=? AND expires>?', (user['id'], path, key, time.time())).fetchone()
    if not row:
        return None
    if not hmac.compare_digest(row['fingerprint'], fingerprint(method, data)):
        raise APIError(409, 'This submission identifier was already used for different data.')
    return row['status'], json.loads(row['result'])


def save_idempotent_result(db, user, path, method, data, key, status, result):
    if key and user and method != 'GET' and not path.startswith(('/api/mfa/', '/api/sso/')):
        db.execute('DELETE FROM idempotency WHERE expires<?', (time.time(),))
        db.execute('INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?,?,?)', (user['id'], path, key, fingerprint(method, data), status, json.dumps(result), time.time()+86400))


def may_manage_employee(db, user, employee_id):
    if user['role'] == 'hr':
        return True
    row = db.execute('SELECT manager_id FROM employees WHERE id=?', (employee_id,)).fetchone()
    return bool(user['role'] == 'manager' and row and row['manager_id'] == user['id'])


def update_employment_access(db, employee_id, data, actor):
    from server import APIError, integer, choice
    if 'role' in data:
        role = choice(data, 'role', ROLES)
        if actor['id'] == employee_id and role != 'hr':
            raise APIError(400, 'Have another HR administrator change your access.')
        old_role = db.execute('SELECT role FROM employees WHERE id=?', (employee_id,)).fetchone()['role']
        db.execute('UPDATE employees SET role=? WHERE id=?', (role, employee_id))
        if old_role != role:
            db.execute('DELETE FROM sessions WHERE employee_id=?', (employee_id,))
            security_event(db, 'Role changed', employee_id)
    if 'manager_id' in data:
        manager_id = data['manager_id']
        if manager_id is not None:
            manager_id = integer(data, 'manager_id', 1, 9223372036854775807)
            manager = db.execute('SELECT id FROM employees WHERE id=? AND status=? AND role IN (?,?)', (manager_id, 'Active', 'manager', 'hr')).fetchone()
            if not manager:
                raise APIError(400, 'Choose an active manager or HR administrator.')
            visited = {employee_id}
            cursor = manager_id
            while cursor:
                if cursor in visited:
                    raise APIError(400, 'The reporting hierarchy cannot contain a cycle.')
                visited.add(cursor)
                row = db.execute('SELECT manager_id FROM employees WHERE id=?', (cursor,)).fetchone()
                cursor = row['manager_id'] if row else None
        db.execute('UPDATE employees SET manager_id=? WHERE id=?', (manager_id, employee_id))


def set_approval_policy(db, entity, record_id):
    policy = setting(db, entity+'_policy', 'manager_or_hr')
    db.execute(f'UPDATE {entity} SET approval_policy=? WHERE id=?', (policy, record_id))


def approve_request(db, entity, row, status, user):
    from server import APIError
    if row['employee_id'] == user['id'] or ('created_by' in row.keys() and row['created_by']==user['id']):
        raise APIError(403, 'Your request needs an independent approver.')
    employee = db.execute('SELECT manager_id FROM employees WHERE id=?', (row['employee_id'],)).fetchone()
    manager = employee['manager_id'] == user['id'] and user['role'] in ('manager', 'hr')
    policy = row['approval_policy']
    if user['role'] != 'hr' and (not manager or policy == 'hr_only'):
        raise APIError(403, 'You cannot review this employee’s request.')
    available_manager = db.execute('SELECT id FROM employees WHERE id=? AND status=? AND role IN (?,?)', (employee['manager_id'], 'Active', 'manager', 'hr')).fetchone()
    if policy == 'manager_then_hr' and available_manager:
        if manager and status == 'Approved':
            if row['manager_reviewed_by']:
                raise APIError(403, 'A different HR reviewer must finish this approval.')
            db.execute(f'UPDATE {entity} SET manager_reviewed_by=? WHERE id=?', (user['id'], row['id']))
            notify(db,row['employee_id'],f'Your {"time off" if entity=="leave" else "expense"} request was reviewed by your manager and is awaiting HR.')
            return
        if user['role'] == 'hr' and status == 'Approved' and (not row['manager_reviewed_by'] or row['manager_reviewed_by'] == user['id']):
            raise APIError(403, 'An independent manager must approve before HR.')
    final_status=('Cancelled' if status=='Approved' else 'Approved') if row['status']=='Cancellation pending' else status
    db.execute(f'UPDATE {entity} SET status=?,reviewed_by=? WHERE id=?', (final_status, user['id'], row['id']))
    notify(db, row['employee_id'], f'Your {"time off" if entity == "leave" else "expense"} request is now {final_status.lower()}.')


def notify(db, employee_id, message):
    from server import now
    db.execute('INSERT INTO notifications(employee_id,message,created_at) VALUES(?,?,?)', (employee_id, message, now()))


def audit_change(db, user, action, entity, entity_id, before=None):
    from server import now
    tables = {'employees', 'leave', 'attendance', 'candidates', 'tasks', 'goals', 'expenses', 'benefit_plans', 'benefit_enrollments', 'courses', 'course_assignments', 'pay_runs', 'pay_results','holidays','leave_allocations','attendance_corrections','compensation'}
    tables.update({'legal_entities','cost_centers','employee_assignments','filing_packets'})
    tables.add('pay_groups')
    details = {}
    if entity in tables:
        row = db.execute(f'SELECT * FROM {entity} WHERE id=?', (entity_id,)).fetchone()
        hidden = {'password', 'totp_secret', 'totp_pending', 'totp_counter','payload'}
        details = {'before': {k:v for k,v in (before or {}).items() if k not in hidden}, 'after': {k:v for k,v in dict(row or {}).items() if k not in hidden}}
    elif entity=='settings':
        details={'before':before or {},'after':policy_values(db)}
    elif entity=='pay_group_members':
        row=db.execute('SELECT * FROM pay_group_members WHERE employee_id=?',(entity_id,)).fetchone()
        details={'before':before or {},'after':dict(row or {})}
    db.execute('INSERT INTO audit(actor_id,action,entity,entity_id,created_at,details) VALUES(?,?,?,?,?,?)', (user['id'], action, entity, entity_id, now(), json.dumps(details)))
    set_setting(db, 'revision', setting(db, 'revision', 0)+1)


def extra_state(db, user, server):
    hr = user['role'] == 'hr'
    scope = '' if hr else ' WHERE t.employee_id=? OR t.employee_id IN (SELECT id FROM employees WHERE manager_id=? AND ?=?)'
    args = () if hr else (user['id'], user['id'], user['role'], 'manager')
    result = {'revision': setting(db, 'revision', 0), 'benefit_plans': [dict(r) for r in db.execute('SELECT * FROM benefit_plans ORDER BY id DESC')], 'courses': [dict(r) for r in db.execute('SELECT * FROM courses ORDER BY id DESC')], 'notifications': [dict(r) for r in db.execute('SELECT * FROM notifications WHERE employee_id=? ORDER BY id DESC LIMIT 100', (user['id'],))]}
    for table in ('benefit_enrollments', 'course_assignments', 'attendance_corrections'):
        table_scope = ' WHERE t.employee_id=?' if table=='benefit_enrollments' and not hr else scope
        table_args = (user['id'],) if table=='benefit_enrollments' and not hr else args
        result[table] = [dict(r) for r in db.execute(f'SELECT t.* FROM {table} t'+table_scope+' ORDER BY id DESC', table_args)]
    from access import entities, entity_allowed, permissions
    allowed=entities(db,user)
    result['pay_runs'] = [dict(r) for r in db.execute('SELECT * FROM pay_runs ORDER BY month DESC') if allowed is None or any(entity_allowed(db,user,p[0]) for p in db.execute('SELECT legal_entity_id FROM pay_results WHERE run_id=?',(r['id'],)))] if user['role'] in ('hr', 'payroll') else []
    result['payroll_access']=permissions(db) if hr else []
    result['policies'] = policy_values(db) if hr else {}
    result['holidays']=[dict(row) for row in db.execute('SELECT * FROM holidays ORDER BY date')]
    from server import IST
    from localization import zone
    today=datetime.now(IST).astimezone(zone(user)).date()
    scope_ids=[row['id'] for row in db.execute('SELECT id FROM employees WHERE is_sample=0'+('' if hr else ' AND (id=? OR (manager_id=? AND ?=\'manager\'))'),() if hr else (user['id'],user['id'],user['role']))]
    result['leave_balances']=[leave_budget(db,employee,kind,today.year,today) for employee in scope_ids for kind in ('Annual','Sick','Personal','Unpaid')]
    for assignment in result['course_assignments']:assignment['is_overdue']=assignment['status']!='Completed' and assignment['due_date']<today.isoformat()
    result['security_events'] = [dict(r) for r in db.execute('SELECT s.*,e.name AS actor_name FROM security_events s LEFT JOIN employees e ON e.id=s.actor_id ORDER BY s.id DESC LIMIT 100')] if user['role'] in ('hr','auditor') else []
    result['sessions']=[{'id':row['public_id'],'signed_in_at':row['auth_time'],'last_activity':row['last_seen'],'expires_at':row['expires'],'current':row['token']==user['token']} for row in db.execute('SELECT * FROM sessions WHERE employee_id=? AND expires>? AND last_seen>? ORDER BY auth_time DESC',(user['id'],time.time(),time.time()-1800))]
    result['security'] = {'mfa_enabled':bool(user['totp_secret']),'mfa_required':setting(db,'require_mfa',False),'sso_enabled':bool(os.environ.get('OPENPEOPLE_OIDC_ISSUER')),'recovery_codes_remaining':db.execute('SELECT count(*) FROM mfa_recovery_codes WHERE employee_id=?',(user['id'],)).fetchone()[0]}
    from enterprise import state as enterprise_state
    result.update(enterprise_state(db,user))
    from pay_periods import state as period_state
    result.update(period_state(db,user))
    result['payslips'] = [dict(r) for r in db.execute("SELECT p.*,r.month,r.pay_group_id,r.pay_group_name,r.period_start,r.period_end,r.pay_date,r.frequency,r.run_kind,r.reference FROM pay_results p JOIN pay_runs r ON r.id=p.run_id WHERE p.employee_id=? AND r.status='Finalized' ORDER BY r.id DESC",(user['id'],))]
    if hr:
        from backup import backup_status
        result['backup'] = backup_status(server.db_path,check_destination=False)
    return result


def payroll_preview(db,user,month):
    from server import APIError
    if user['role'] not in ('hr','payroll'):
        raise APIError(403,'Payroll access is required.')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month) or not 1900<=int(month[:4])<=9998:
        raise APIError(400,'Choose a valid payroll month.')
    year,number=map(int,month.split('-'));calendar_days=calendar.monthrange(year,number)[1]
    first,last=date(year,number,1),date(year,number,calendar_days)
    from localization import currency_digits
    rows=[];totals={}
    for row in db.execute('SELECT id,name,email,department,annual_salary,start_date,end_date,status,country,currency,timezone FROM employees WHERE is_sample=0 AND start_date<=? ORDER BY name',(last.isoformat(),)):
        from access import entity_allowed
        assignment=db.execute('SELECT legal_entity_id FROM employee_assignments WHERE employee_id=?',(row['id'],)).fetchone()
        if not entity_allowed(db,user,assignment[0] if assignment else None):continue
        if row['status']=='Inactive' and not row['end_date']:raise APIError(409,'Record employment end dates for inactive workers before preparing payroll.')
        start=max(first,date.fromisoformat(row['start_date']));end=min(last,date.fromisoformat(row['end_date']) if row['end_date'] else last)
        if end<start:continue
        unpaid={}
        for leave in db.execute("SELECT * FROM leave WHERE employee_id=? AND type='Unpaid' AND status IN ('Approved','Cancellation pending')",(row['id'],)):
            dates=charged_dates(leave);fraction=Decimal(str(leave['days']))/len(dates) if dates else Decimal(0)
            for day in dates:unpaid[day]=unpaid.get(day,Decimal(0))+fraction
        factor=10**currency_digits(row['currency'])
        gross=Decimal(0);paid_days=Decimal(0);salary_days={}
        for offset in range((end-start).days+1):
            day=(start+timedelta(days=offset)).isoformat();salary=salary_on(db,row['id'],day,row['annual_salary'])
            paid=Decimal(1)-unpaid.get(day,Decimal(0));paid_days+=paid
            gross+=Decimal(salary)*factor/12/calendar_days*paid
            salary_days[salary]=salary_days.get(salary,Decimal(0))+paid
        paise=int(gross.quantize(Decimal('1'),rounding=ROUND_HALF_UP));item=dict(row)
        item.update(annual_salary=salary_on(db,row['id'],end.isoformat(),row['annual_salary']),monthly_gross=paise/factor,gross_paise=paise,paid_days=float(paid_days),calendar_days=calendar_days,unpaid_days=float(sum(unpaid.get((start+timedelta(days=i)).isoformat(),Decimal(0)) for i in range((end-start).days+1))),calculation=[{'annual_salary':salary,'paid_days':float(days)} for salary,days in salary_days.items()])
        item['statutory_status']='Manual review required'
        rows.append(item);totals[row['currency']]=totals.get(row['currency'],0)+paise
    total_amounts={code:amount/10**currency_digits(code) for code,amount in totals.items()}
    return {'month':month,'rows':rows,'total':next(iter(total_amounts.values())) if len(total_amounts)==1 else None,'currency':next(iter(total_amounts)) if len(total_amounts)==1 else None,'totals_by_currency':total_amounts,'note':'Reviewed gross estimate: calendar-day join/exit proration, effective-dated salary and approved unpaid leave. Tax/statutory deductions and payments remain manual.'}


def extension_api(handler, db, path, query, data, user):
    from server import APIError, text_field, integer, date_field, now, choice
    from identity import identity_api
    identity = identity_api(handler, db, path, query, data, user)
    if identity is not None:
        return identity
    method = handler.command
    from operations import api as operations_api
    operations=operations_api(handler,db,path,user)
    if operations is not None:return operations
    from pay_periods import api as periods_api
    periods=periods_api(handler,db,path,data,user)
    if periods is not None:return periods
    from access import api as access_api
    access=access_api(handler,db,path,data,user)
    if access is not None:return access
    from enterprise import api as enterprise_api
    enterprise = enterprise_api(handler,db,path,data,user)
    if enterprise is not None:return enterprise
    if path=='/api/countries' and method=='GET':
        from localization import COUNTRIES,CURRENCIES,currency_digits
        from payroll import capabilities
        from core_hr import enabled,contract
        return 200,{'countries':list(COUNTRIES.values()),'currencies':CURRENCIES,'currency_digits':{code:currency_digits(code) for code in CURRENCIES},'statutory_payroll_supported':False,'payroll_capabilities':{} if enabled(handler.server) else capabilities(),'product':contract(handler.server)},None
    if path == '/api/changes' and method == 'GET':
        return 200, {'revision': setting(db, 'revision', 0)}, None
    if path=='/api/audit/verify' and method=='GET':
        if user['role'] not in ('hr','auditor'):raise APIError(403,'You do not have access to audit verification.')
        from audit_integrity import verify
        return 200,verify(db),None
    if path == '/api/activity' and method == 'POST':
        db.execute('UPDATE sessions SET last_seen=? WHERE token=?',(time.time(),user['token']))
        return 200,{'ok':True},None
    if path in ('/api/audit/export','/api/benefits/export','/api/reports') and method=='GET':
        allowed=('hr','auditor') if path=='/api/audit/export' else ('hr',)
        if user['role'] not in allowed:raise APIError(403,'You do not have access to this export.')
        def number(key,default,maximum):
            value=query.get(key,[str(default)])[0]
            if not re.fullmatch(r'[0-9]{1,7}',value) or not 0<=int(value)<=maximum:raise APIError(400,'Choose a valid export page.')
            return int(value)
        limit=number('limit',100,500);offset=number('offset',0,1000000)
        if not limit:raise APIError(400,'Page size must be positive.')
        start=query.get('start',['1900-01-01'])[0];end=query.get('end',['9998-12-31'])[0]
        start=date_field({'start':start},'start').isoformat();end=date_field({'end':end},'end').isoformat()
        if end<start:raise APIError(400,'Report end must follow its start.')
        if path=='/api/audit/export':
            security_event(db,'Audit exported',user['id'],handler.client_address[0],{'start':start,'end':end,'limit':limit,'offset':offset})
            changes=[dict(r) for r in db.execute('SELECT a.*,e.name AS actor_name FROM audit a LEFT JOIN employees e ON e.id=a.actor_id WHERE substr(a.created_at,1,10) BETWEEN ? AND ? ORDER BY a.id LIMIT ? OFFSET ?',(start,end,limit,offset))]
            events=[dict(r) for r in db.execute('SELECT * FROM security_events WHERE substr(created_at,1,10) BETWEEN ? AND ? ORDER BY id LIMIT ? OFFSET ?',(start,end,limit,offset))]
            return 200,{'changes':changes,'security_events':events,'limit':limit,'offset':offset},None
        if path=='/api/benefits/export':
            entity='benefit_enrollments';column='substr(t.created_at,1,10)'
        else:
            entity=query.get('entity',['employees'])[0]
            columns={'employees':'e.start_date','leave':'t.start_date','expenses':'t.expense_date','attendance':'t.work_date','benefit_enrollments':'substr(t.created_at,1,10)'}
            if entity not in columns:raise APIError(400,'Choose employees, leave, expenses, attendance or benefit_enrollments.')
            column=columns[entity]
        source='employees e' if entity=='employees' else f'{entity} t JOIN employees e ON e.id=t.employee_id'
        fields='e.id,e.name,e.email,e.department,e.title,e.location,e.start_date,e.end_date,e.status,e.is_sample' if entity=='employees' else 't.*,e.name AS employee_name'
        where=f'e.is_sample=0 AND {column} BETWEEN ? AND ?'
        total=db.execute(f'SELECT count(*) FROM {source} WHERE {where}',(start,end)).fetchone()[0]
        rows=[dict(r) for r in db.execute(f'SELECT {fields} FROM {source} WHERE {where} ORDER BY '+('e.id' if entity=='employees' else 't.id')+' LIMIT ? OFFSET ?',(start,end,limit,offset))]
        security_event(db,'Report exported',user['id'],handler.client_address[0],{'entity':entity,'start':start,'end':end,'limit':limit,'offset':offset})
        return 200,{'entity':entity,'rows':rows,'total':total,'limit':limit,'offset':offset,'start':start,'end':end},None
    if path == '/api/backup/status' and method == 'GET':
        handler.require_hr(user)
        from backup import backup_status
        return 200, backup_status(handler.server.db_path,check_destination=False), None
    if path == '/api/backup/run' and method == 'POST':
        handler.require_hr(user)
        from backup import prepare_backup_job
        try:
            result,handler.after_commit,handler.after_rollback = prepare_backup_job(handler.server,user['id'])
        except (ValueError, OSError) as error:
            raise APIError(400, 'Backup could not run. Check the local backup configuration and destination.') from error
        security_event(db, 'Backup queued', user['id'],handler.client_address[0],{'job_id':result['id']})
        return 202, result, None
    if path == '/api/policies' and method == 'POST':
        handler.require_hr(user)
        handler.before_row=policy_values(db)
        for key in ('leave_policy','expenses_policy'):
            if key in data:
                set_setting(db, key, choice(data, key, POLICIES))
        if 'require_mfa' in data:
            if getattr(handler.server,'production_mode',False) and data['require_mfa'] is not True:raise APIError(400,'Mandatory MFA cannot be disabled in production mode.')
            if type(data['require_mfa']) is not bool:
                raise APIError(400, 'Authenticator policy must be a boolean.')
            if data['require_mfa'] and not user['totp_secret']:
                raise APIError(400, 'Enroll your own authenticator before requiring it for everyone.')
            set_setting(db, 'require_mfa', data['require_mfa'])
            if data['require_mfa']:
                db.execute('DELETE FROM sessions WHERE employee_id<>?', (user['id'],))
        if 'leave_accrual' in data:set_setting(db,'leave_accrual',choice(data,'leave_accrual',('annual','monthly')))
        if 'leave_limits' in data:
            limits=data['leave_limits']
            if not isinstance(limits,dict) or set(limits)!= {'Annual','Sick','Personal'}:raise APIError(400,'Provide annual, sick and personal leave limits.')
            for value in limits.values():
                if type(value) not in (int,float) or not 0<=value<=366 or value*2!=int(value*2):raise APIError(400,'Leave limits must use half-day increments from 0 to 366.')
            set_setting(db,'leave_limits',limits)
        if any(key in data for key in ('expenses_limit_paise','receipt_required_above_paise')):
            from localization import CURRENCIES
            currency=choice(data,'expense_policy_currency',CURRENCIES) if data.get('expense_policy_currency') else 'INR'
            policies=setting(db,'expense_policies',{})
            policy=dict(policies.get(currency,{}))
            for key in ('expenses_limit_paise','receipt_required_above_paise'):
                if key in data:
                    policy[key]=integer(data,key,0,1000000000)
                    if currency=='INR':set_setting(db,key,policy[key])
            policies[currency]=policy;set_setting(db,'expense_policies',policies)
        handler.audit(db, user, 'Policy changed', 'settings', None)
        return 200, {'ok': True}, None
    if path=='/api/attendance_corrections' and method=='POST':
        from server import IST
        from localization import zone
        attendance=integer(data,'attendance_id',1,9223372036854775807)
        row=db.execute('SELECT * FROM attendance WHERE id=?',(attendance,)).fetchone()
        if not row:raise APIError(404,'Attendance record not found.')
        if row['employee_id']!=user['id'] and user['role']!='hr':raise APIError(403,'You can only request a correction for your own attendance.')
        expected=integer(data,'expected_version',1,2147483647)
        if expected!=row['version']:raise APIError(409,'Attendance changed. Reload before requesting a correction.')
        employee=db.execute('SELECT * FROM employees WHERE id=?',(row['employee_id'],)).fetchone()
        employee_zone=zone(employee)
        times=[]
        for key in ('check_in','check_out'):
            try:
                value=datetime.fromisoformat(text_field(data,key,50))
                if value.tzinfo is None:
                    naive=value
                    value=value.replace(tzinfo=employee_zone)
                    from datetime import timezone
                    if value.astimezone(timezone.utc).astimezone(employee_zone).replace(tzinfo=None)!=naive or naive.replace(tzinfo=employee_zone,fold=0).utcoffset()!=naive.replace(tzinfo=employee_zone,fold=1).utcoffset():raise ValueError('Use an explicit offset for a DST transition time.')
                value=value.astimezone(employee_zone)
                if not 1900<=value.year<=9998:raise ValueError()
            except ValueError as error:raise APIError(400,'Enter valid check-in and check-out times in IST or with a timezone offset.') from error
            times.append(value)
        duration=(times[1].timestamp()-times[0].timestamp())/60
        minutes=integer(data,'break_minutes',0,1440)
        if not 0<duration<=1440 or minutes>=duration:raise APIError(400,'A corrected shift must last at most 24 hours, with breaks shorter than the shift.')
        if db.execute("SELECT id FROM attendance_corrections WHERE attendance_id=? AND status='Pending'",(attendance,)).fetchone():raise APIError(409,'This attendance record already has a pending correction.')
        cursor=db.execute('INSERT INTO attendance_corrections(employee_id,attendance_id,expected_version,check_in,check_out,break_minutes,reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(row['employee_id'],attendance,expected,times[0].isoformat(timespec='seconds'),times[1].isoformat(timespec='seconds'),minutes,text_field(data,'reason',500),user['id'],now()))
        handler.audit(db,user,'Correction requested','attendance_corrections',cursor.lastrowid)
        return 201,{'id':cursor.lastrowid},None
    match=re.fullmatch(r'/api/attendance_corrections/(\d{1,19})',path)
    if match and method=='PATCH':
        record=integer({'id':int(match[1])},'id',1,9223372036854775807)
        row=db.execute('SELECT * FROM attendance_corrections WHERE id=?',(record,)).fetchone()
        if not row:raise APIError(404,'Correction not found.')
        if row['status']!='Pending':raise APIError(409,'This correction has already been reviewed.')
        status=choice(data,'status',('Approved','Rejected'))
        handler.before_row=dict(row)
        approve_request(db,'attendance_corrections',row,status,user)
        if status=='Approved':
            source=db.execute('SELECT * FROM attendance WHERE id=?',(row['attendance_id'],)).fetchone()
            if source['version']!=row['expected_version']:raise APIError(409,'Attendance changed since this request. Reject it and submit a fresh correction.')
            overlap=db.execute('SELECT id FROM attendance WHERE employee_id=? AND id<>? AND requires_correction=0 AND julianday(check_in)<julianday(?) AND (check_out IS NULL OR julianday(check_out)>julianday(?))',(row['employee_id'],source['id'],row['check_out'],row['check_in'])).fetchone()
            if overlap:raise APIError(409,'The correction overlaps another attendance session.')
            db.execute('UPDATE attendance SET work_date=?,check_in=?,check_out=?,break_minutes=?,requires_correction=0,version=version+1 WHERE id=?',(row['check_in'][:10],row['check_in'],row['check_out'],row['break_minutes'],source['id']))
            audit_change(db,user,'Approved correction','attendance',source['id'],dict(source))
        handler.audit(db,user,status,'attendance_corrections',record)
        return 200,{'id':record,'status':status},None
    if path == '/api/holidays' and method == 'POST':
        handler.require_hr(user)
        from localization import COUNTRIES
        country=data.get('country','*')
        if not isinstance(country,str) or country not in ('*',*COUNTRIES):raise APIError(400,'Choose a holiday country or all workers.')
        cursor=db.execute('INSERT INTO holidays(date,name,country) VALUES(?,?,?)',(date_field(data,'date').isoformat(),text_field(data,'name',100),country))
        handler.audit(db,user,'Created','holidays',cursor.lastrowid)
        return 201,{'id':cursor.lastrowid},None
    if path == '/api/leave_allocations' and method == 'POST':
        handler.require_hr(user);employee=handler.owner(data,user);handler.active_employee(db,employee)
        year=integer(data,'year',1900,9998);kind=choice(data,'type',('Annual','Sick','Personal'))
        for key in ('days','carryover'):
            value=data.get(key,0 if key=='carryover' else None)
            if type(value) not in (int,float) or not 0<=value<=366 or value*2!=int(value*2):raise APIError(400,'Allocations must use nonnegative half-day increments up to 366.')
        before=db.execute('SELECT * FROM leave_allocations WHERE employee_id=? AND year=? AND type=?',(employee,year,kind)).fetchone();handler.before_row=dict(before) if before else None
        db.execute('INSERT INTO leave_allocations(employee_id,year,type,days,carryover,reason) VALUES(?,?,?,?,?,?) ON CONFLICT(employee_id,year,type) DO UPDATE SET days=excluded.days,carryover=excluded.carryover,reason=excluded.reason',(employee,year,kind,data['days'],data.get('carryover',0),text_field(data,'reason',500)))
        record=db.execute('SELECT id FROM leave_allocations WHERE employee_id=? AND year=? AND type=?',(employee,year,kind)).fetchone()['id']
        handler.audit(db,user,'Allocation reviewed','leave_allocations',record)
        return 201,{'id':record},None
    if method == 'POST' and path in ('/api/benefit_plans','/api/courses'):
        handler.require_hr(user)
        title = text_field(data, 'title', 200)
        description = text_field(data, 'description', 1000)
        if path.endswith('benefit_plans'):
            opens=date_field(data,'enrollment_opens').isoformat() if data.get('enrollment_opens') else None
            closes=date_field(data,'enrollment_closes').isoformat() if data.get('enrollment_closes') else None
            if opens and closes and closes<opens:raise APIError(400,'Enrollment close must follow enrollment open.')
            cursor = db.execute('INSERT INTO benefit_plans(title,description,monthly_cost_paise,enrollment_opens,enrollment_closes,currency) VALUES(?,?,?,?,?,?)', (title, description, integer(data,'monthly_cost_paise',0,1000000000),opens,closes,choice(data,'currency',__import__('localization').CURRENCIES) if data.get('currency') else user['currency']))
        else:
            url = text_field(data, 'url', 1000, optional=True)
            if url and not re.fullmatch(r'https://[^\s]+', url):
                raise APIError(400, 'Course links must use HTTPS.')
            cursor = db.execute('INSERT INTO courses(title,description,url) VALUES(?,?,?)', (title, description, url))
        handler.audit(db, user, 'Created', path.split('/')[-1], cursor.lastrowid)
        return 201, {'id': cursor.lastrowid}, None
    if method == 'POST' and path in ('/api/benefit_enrollments','/api/course_assignments'):
        employee = handler.owner(data, user)
        handler.active_employee(db, employee)
        if path.endswith('benefit_enrollments'):
            plan = integer(data, 'plan_id', 1, 9223372036854775807)
            benefit=db.execute('SELECT * FROM benefit_plans WHERE id=?',(plan,)).fetchone()
            if not benefit:raise APIError(400,'Choose a benefit plan.')
            from server import IST
            from localization import zone
            owner=db.execute('SELECT * FROM employees WHERE id=?',(employee,)).fetchone()
            if benefit['currency']!=owner['currency']:raise APIError(400,'Choose a benefit plan in this employee’s payroll currency.')
            today=datetime.now(IST).astimezone(zone(owner)).date().isoformat()
            if (benefit['enrollment_opens'] and today<benefit['enrollment_opens']) or (benefit['enrollment_closes'] and today>benefit['enrollment_closes']):raise APIError(400,'Enrollment is outside this plan’s configured window.')
            previous=db.execute('SELECT * FROM benefit_enrollments WHERE employee_id=? AND plan_id=?',(employee,plan)).fetchone()
            if previous:
                if previous['status']=='Active':raise APIError(409,'This employee is already enrolled in this plan.')
                handler.before_row=dict(previous)
                db.execute("UPDATE benefit_enrollments SET status='Active',ended_on=NULL,created_at=? WHERE id=?",(now(),previous['id']))
                handler.audit(db,user,'Re-enrolled','benefit_enrollments',previous['id'])
                return 201,{'id':previous['id']},None
            cursor = db.execute('INSERT INTO benefit_enrollments(employee_id,plan_id,created_at) VALUES(?,?,?)', (employee, plan, now()))
        else:
            handler.require_hr(user)
            course = integer(data, 'course_id', 1, 9223372036854775807)
            if not db.execute('SELECT id FROM courses WHERE id=?', (course,)).fetchone():
                raise APIError(400, 'Choose a course.')
            cursor = db.execute('INSERT INTO course_assignments(employee_id,course_id,due_date) VALUES(?,?,?)', (employee, course, date_field(data,'due_date').isoformat()))
            notify(db, employee, 'A learning course has been assigned to you.')
        handler.audit(db, user, 'Created', path.split('/')[-1], cursor.lastrowid)
        return 201, {'id': cursor.lastrowid}, None
    match=re.fullmatch(r'/api/benefit_enrollments/(\d{1,19})',path)
    if match and method=='PATCH':
        record=integer({'id':int(match[1])},'id',1,9223372036854775807);row=db.execute('SELECT * FROM benefit_enrollments WHERE id=?',(record,)).fetchone()
        if not row:raise APIError(404,'Enrollment not found.')
        if row['employee_id']!=user['id'] and user['role']!='hr':raise APIError(403,'You can only withdraw your own enrollment.')
        if data.get('status')!='Withdrawn':raise APIError(400,'Choose Withdrawn to end an enrollment.')
        if row['status']!='Active':raise APIError(409,'This enrollment is already withdrawn.')
        handler.before_row=dict(row)
        db.execute("UPDATE benefit_enrollments SET status='Withdrawn',ended_on=? WHERE id=?",(now(),record))
        handler.audit(db,user,'Withdrawn','benefit_enrollments',record)
        return 200,{'id':record,'status':'Withdrawn'},None
    match = re.fullmatch(r'/api/(course_assignments|notifications)/(\d{1,19})', path)
    if match and method == 'PATCH':
        table, record = match[1], int(match[2])
        if record > 9223372036854775807:
            raise APIError(400, 'Choose a valid record.')
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (record,)).fetchone()
        if not row:
            raise APIError(404, 'Record not found.')
        if table=='course_assignments' and data.get('action') in ('remind','reassign'):
            handler.require_hr(user);handler.before_row=dict(row)
            if data['action']=='remind':
                if row['status']=='Completed':raise APIError(409,'This course is already completed.')
                notify(db,row['employee_id'],'Reminder: your assigned learning course is due '+row['due_date']+'.')
            else:
                text_field(data,'reason',500)
                db.execute("UPDATE course_assignments SET due_date=?,status='Assigned',completed_at=NULL WHERE id=?",(date_field(data,'due_date').isoformat(),record))
                notify(db,row['employee_id'],'A learning course was reassigned to you.')
            handler.audit(db,user,'Reminder sent' if data['action']=='remind' else 'Reassigned',table,record)
            return 200,{'id':record},None
        if row['employee_id'] != user['id']:
            raise APIError(403, 'You can only update your own records.')
        if table == 'notifications':
            db.execute('UPDATE notifications SET seen=1 WHERE id=?', (record,))
            if not row['seen']:
                set_setting(db,'revision',setting(db,'revision',0)+1)
        else:
            if row['status'] == 'Completed':
                raise APIError(409, 'This course is already completed.')
            db.execute("UPDATE course_assignments SET status='Completed',completed_at=? WHERE id=?", (now(),record))
            handler.audit(db,user,'Completed',table,record)
        return 200, {'id': record}, None
    if path == '/api/pay_runs' and method == 'POST':
        if user['role'] not in ('hr','payroll'):
            raise APIError(403, 'Payroll access is required.')
        from access import entities
        if entities(db,user) is not None:raise APIError(403,'A workspace payroll administrator must create organization-wide pay runs.')
        month = text_field(data,'month',7)
        preview = payroll_preview(db,user,month)
        if not preview['rows']:
            raise APIError(400, 'There are no employees for this period.')
        from pay_periods import legacy_overlap
        if legacy_overlap(db,preview['rows'],month):raise APIError(409,'Dated regular payroll overlaps a worker in this month. Use the existing group or a reviewed adjustment.')
        cursor = db.execute('INSERT INTO pay_runs(month,created_by,created_at) VALUES(?,?,?)', (month,user['id'],now()))
        for row in preview['rows']:
            db.execute('INSERT INTO pay_results(run_id,employee_id,employee_name,department,gross_paise,calculation,currency,country) VALUES(?,?,?,?,?,?,?,?)', (cursor.lastrowid,row['id'],row['name'],row['department'],row['gross_paise'],json.dumps({key:row[key] for key in ('annual_salary','paid_days','calendar_days','unpaid_days','calculation')}),row['currency'],row['country']))
            assignment=db.execute('SELECT * FROM employee_assignments WHERE employee_id=?',(row['id'],)).fetchone()
            if assignment:db.execute('UPDATE pay_results SET legal_entity_id=?,cost_center_id=? WHERE run_id=? AND employee_id=?',(assignment['legal_entity_id'],assignment['cost_center_id'],cursor.lastrowid,row['id']))
        handler.audit(db,user,'Created','pay_runs',cursor.lastrowid)
        return 201, {'id': cursor.lastrowid}, None
    match = re.fullmatch(r'/api/(pay_runs|pay_results)/(\d{1,19})',path)
    if match:
        if user['role'] not in ('hr','payroll'):
            raise APIError(403,'Payroll access is required.')
        table, record = match[1],int(match[2])
        if record > 9223372036854775807:
            raise APIError(400,'Choose a valid record.')
        row = db.execute(f'SELECT * FROM {table} WHERE id=?',(record,)).fetchone()
        if not row:
            raise APIError(404,'Pay record not found.')
        from access import entity_allowed,run_scope
        if table=='pay_results' and not entity_allowed(db,user,row['legal_entity_id']):raise APIError(404,'Pay record not found.')
        if table=='pay_runs' and not any(entity_allowed(db,user,p[0]) for p in db.execute('SELECT legal_entity_id FROM pay_results WHERE run_id=?',(record,))):raise APIError(404,'Pay record not found.')
        if table == 'pay_runs' and method == 'GET':
            edited = db.execute('SELECT 1 FROM pay_run_editors WHERE run_id=? AND employee_id=?', (record, user['id'])).fetchone()
            result_rows = [dict(r) for r in db.execute('SELECT * FROM pay_results WHERE run_id=?', (record,)) if entity_allowed(db,user,r['legal_entity_id'])]
            for result_row in result_rows:
                result_row['can_edit_deductions'] = row['status'] == 'Draft' and result_row['employee_id'] != user['id']
                from payroll import template
                result_row['external_template'] = template(result_row,row['month'],row) if result_row['can_edit_deductions'] else None
            complete=not row['pay_group_id'] or all(r['external_result'] for r in result_rows)
            return 200, {'run':dict(row),'rows':result_rows,'scope_limited':not run_scope(db,user,record),'can_finalize':row['status']=='Draft' and row['created_by']!=user['id'] and not edited and run_scope(db,user,record) and complete},None
        run = row if table == 'pay_runs' else db.execute('SELECT * FROM pay_runs WHERE id=?',(row['run_id'],)).fetchone()
        if method == 'PATCH':
            if run['status'] != 'Draft':
                raise APIError(409,'Finalized payroll snapshots cannot be edited.')
            if table == 'pay_runs':
                if not run_scope(db,user,record):raise APIError(403,'You cannot finalize payroll containing statements outside your employer scope.')
                if run['created_by'] == user['id']:
                    raise APIError(403,'A second HR or payroll reviewer must finalize this run.')
                if db.execute('SELECT 1 FROM pay_run_editors WHERE run_id=? AND employee_id=?', (run['id'], user['id'])).fetchone():
                    raise APIError(403,'A reviewer who has not edited this run must finalize it.')
                if data.get('status') != 'Finalized':
                    raise APIError(400,'Choose Finalized after checking all payroll inputs.')
                if 'expected_version' not in data:
                    raise APIError(428,'Reload and review the current pay run before finalizing it.')
                expected = integer(data,'expected_version',1,9223372036854775807)
                if expected != run['version']:
                    raise APIError(409,'Payroll changed after you opened it. Reload and review all amounts before finalizing.')
                if run['pay_group_id'] and db.execute("SELECT 1 FROM pay_results WHERE run_id=? AND external_result=''",(record,)).fetchone():raise APIError(409,'Every dated statement needs an externally reviewed result before finalization.')
                db.execute("UPDATE pay_runs SET status='Finalized',reviewed_by=?,version=version+1 WHERE id=?",(user['id'],record))
                period_label=f'{run["pay_group_name"]}: {run["period_start"]} to {run["period_end"]}' if run['pay_group_id'] else run['month']
                for employee in db.execute('SELECT employee_id FROM pay_results WHERE run_id=?',(record,)).fetchall():
                    notify(db,employee['employee_id'],f'Your pay statement for {period_label} is available.')
            else:
                if row['employee_id'] == user['id']:
                    raise APIError(403,'Another HR or payroll colleague must edit your pay statement.')
                if 'expected_version' not in data:
                    raise APIError(428,'Reload the current pay run before editing deductions.')
                expected = integer(data,'expected_version',1,9223372036854775807)
                if expected != run['version']:
                    raise APIError(409,'Payroll changed after you opened it. Reload before editing deductions.')
                handler.before_row = dict(row)
                if 'external_result' in data:
                    from payroll import validate_external
                    if set(data) != {'expected_version','external_result'}:
                        raise APIError(400,'Submit an external result and its reviewed version without other payroll fields.')
                    external,totals=validate_external(data['external_result'],row,run['month'],run)
                    external.update(imported_by=user['id'],imported_at=now())
                    calculation=json.dumps({'source':'external','provider':external['provider'],'reference':external['reference']})
                    db.execute('UPDATE pay_results SET gross_paise=?,deductions_paise=?,deduction_note=?,external_result=?,calculation=? WHERE id=?',(totals['earnings'],totals['deductions'],external['review_note'],json.dumps(external),calculation,record))
                else:
                    if row['external_result']:
                        raise APIError(409,'Import a revised externally reviewed result to change this statement and retain its component breakdown.')
                    deduction = integer(data,'deductions_paise',0,row['gross_paise'])
                    note = text_field(data,'deduction_note',500,optional=deduction==0)
                    db.execute('UPDATE pay_results SET deductions_paise=?,deduction_note=? WHERE id=?',(deduction,note,record))
                db.execute('INSERT OR IGNORE INTO pay_run_editors(run_id,employee_id) VALUES(?,?)', (run['id'], user['id']))
                db.execute('UPDATE pay_runs SET version=version+1 WHERE id=?', (run['id'],))
            handler.audit(db,user,'Updated',table,record)
            return 200, {'id':record},None
    return None
