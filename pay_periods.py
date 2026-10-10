"""Employer pay groups and dated externally reviewed payroll snapshots.

Salary amounts are calendar-month prorated estimates, not statutory results.
Every dated run requires external results before independent finalization.
"""
import calendar
from datetime import date,timedelta
from decimal import Decimal,ROUND_HALF_UP
import json
import re

FREQUENCIES=('weekly','fortnightly','semimonthly','monthly')
PERIOD_FIELDS=('run_id','pay_group_id','pay_group_version','period_start','period_end','pay_date','frequency','run_kind','reference','external_review_required')


def schema(db):
    from workspace import execute_schema
    execute_schema(db,'''CREATE TABLE IF NOT EXISTS pay_groups(id INTEGER PRIMARY KEY,legal_entity_id INTEGER NOT NULL REFERENCES legal_entities(id),name TEXT NOT NULL,frequency TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,UNIQUE(legal_entity_id,name));
    CREATE TABLE IF NOT EXISTS pay_group_members(employee_id INTEGER PRIMARY KEY REFERENCES employees(id),pay_group_id INTEGER NOT NULL REFERENCES pay_groups(id));''')
    columns={r['name'] for r in db.execute('PRAGMA table_info(pay_runs)')}
    for name,definition in {'pay_group_id':'INTEGER REFERENCES pay_groups(id)','pay_group_version':'INTEGER','pay_group_name':'TEXT','period_start':'TEXT','period_end':'TEXT','pay_date':'TEXT','frequency':'TEXT','run_kind':'TEXT','reference':'TEXT'}.items():
        if name not in columns:db.execute(f'ALTER TABLE pay_runs ADD COLUMN {name} {definition}')
    db.execute('CREATE INDEX IF NOT EXISTS pay_period_overlap ON pay_runs(pay_group_id,run_kind,period_start,period_end)')
    db.execute('CREATE INDEX IF NOT EXISTS pay_worker_runs ON pay_results(employee_id,run_id)')


def period_contract(run):
    run=dict(run)
    if not run.get('pay_group_id'):return None
    return {key:(run['id'] if key=='run_id' else True if key=='external_review_required' else run[key]) for key in PERIOD_FIELDS}


def state(db,user):
    if user['role'] not in ('hr','payroll'):return {'pay_groups':[],'pay_group_members':[]}
    from access import entity_allowed
    groups=[dict(r) for r in db.execute('SELECT g.*,e.country,e.currency FROM pay_groups g JOIN legal_entities e ON e.id=g.legal_entity_id ORDER BY g.name') if entity_allowed(db,user,r['legal_entity_id'])]
    ids={g['id'] for g in groups}
    return {'pay_groups':groups,'pay_group_members':[dict(r) for r in db.execute('SELECT * FROM pay_group_members') if r['pay_group_id'] in ids]}


def validate_period(data,group):
    from server import APIError,date_field,text_field
    required={'pay_group_id','expected_group_version','period_start','period_end','pay_date','run_kind','reference'}
    if set(data)!=required:raise APIError(400,'Provide the complete dated payroll form and current group version.')
    first,last,paid=(date_field(data,key) for key in ('period_start','period_end','pay_date'))
    if last<first or (last-first).days>365 or paid<first or (paid-last).days>366:raise APIError(400,'Use a period of at most 366 days and a pay date within its supported window.')
    kind=data.get('run_kind')
    if kind not in ('regular','bonus','adjustment'):raise APIError(400,'Choose regular, bonus or adjustment payroll.')
    reference=text_field(data,'reference',64)
    if not re.fullmatch(r'[A-Z0-9_-]{1,64}',reference):raise APIError(400,'Payroll references use uppercase letters, digits, underscore and dash.')
    if kind=='regular':
        length=(last-first).days+1;frequency=group['frequency']
        same_month=(first.year,first.month)==(last.year,last.month)
        if frequency=='weekly':valid=length==7
        elif frequency=='fortnightly':valid=length==14
        elif frequency=='monthly':valid=same_month and first.day==1 and last.day==calendar.monthrange(first.year,first.month)[1]
        else:valid=same_month and ((first.day,last.day)==(1,15) or (first.day,last.day)==(16,calendar.monthrange(first.year,first.month)[1]))
        if not valid:raise APIError(400,'The regular period must match the pay group frequency.')
    return first,last,paid,kind,reference


def legacy_overlap(db,workers,month):
    year,number=map(int,month.split('-'));first=date(year,number,1).isoformat();last=date(year,number,calendar.monthrange(year,number)[1]).isoformat()
    return any(db.execute("SELECT 1 FROM pay_results p JOIN pay_runs r ON r.id=p.run_id WHERE p.employee_id=? AND r.pay_group_id IS NOT NULL AND r.run_kind='regular' AND r.period_start<=? AND r.period_end>=?",(worker['id'],last,first)).fetchone() for worker in workers)


def estimated_gross(db,worker,first,last):
    from workspace import charged_dates,salary_on
    from localization import currency_digits
    start=max(first,date.fromisoformat(worker['start_date']));end=min(last,date.fromisoformat(worker['end_date']) if worker['end_date'] else last)
    unpaid={}
    for leave in db.execute("SELECT * FROM leave WHERE employee_id=? AND type='Unpaid' AND status IN ('Approved','Cancellation pending')",(worker['id'],)):
        days=charged_dates(leave);fraction=Decimal(str(leave['days']))/len(days) if days else Decimal(0)
        for day in days:unpaid[day]=unpaid.get(day,Decimal(0))+fraction
    gross=Decimal(0);factor=10**currency_digits(worker['currency'])
    for offset in range((end-start).days+1):
        day=start+timedelta(days=offset)
        paid=max(Decimal(0),Decimal(1)-unpaid.get(day.isoformat(),Decimal(0)))
        gross+=Decimal(salary_on(db,worker['id'],day.isoformat(),worker['annual_salary']))*factor/12/calendar.monthrange(day.year,day.month)[1]*paid
    return int(gross.quantize(Decimal(1),rounding=ROUND_HALF_UP))


def api(handler,db,path,data,user):
    if path not in ('/api/pay_groups','/api/pay_group_members','/api/pay_period_runs'):return None
    from server import APIError,integer,text_field,now
    from access import entity_allowed
    if user['role'] not in ('hr','payroll'):raise APIError(403,'Payroll access is required.')
    if path=='/api/pay_groups' and handler.command=='GET':return 200,{'rows':state(db,user)['pay_groups']},None
    if handler.command!='POST':return None
    if path=='/api/pay_groups':
        handler.require_hr(user)
        if set(data)!={'legal_entity_id','name','frequency'} or data.get('frequency') not in FREQUENCIES:raise APIError(400,'Provide the employer, name and supported pay frequency.')
        employer=integer(data,'legal_entity_id',1,9223372036854775807)
        if not db.execute('SELECT 1 FROM legal_entities WHERE id=?',(employer,)).fetchone():raise APIError(400,'Choose an existing employer.')
        cursor=db.execute('INSERT INTO pay_groups(legal_entity_id,name,frequency) VALUES(?,?,?)',(employer,text_field(data,'name',100),data['frequency']))
        handler.audit(db,user,'Created','pay_groups',cursor.lastrowid)
        return 201,{'id':cursor.lastrowid},None
    group_id=integer(data,'pay_group_id',1,9223372036854775807)
    group=db.execute('SELECT g.*,e.country,e.currency FROM pay_groups g JOIN legal_entities e ON e.id=g.legal_entity_id WHERE g.id=?',(group_id,)).fetchone()
    if not group or not entity_allowed(db,user,group['legal_entity_id']):raise APIError(404,'Pay group not found.')
    expected=integer(data,'expected_group_version',1,9223372036854775807)
    if expected!=group['version']:raise APIError(409,'The pay group changed. Reload its roster before continuing.')
    if path=='/api/pay_group_members':
        handler.require_hr(user)
        if set(data)!={'employee_id','pay_group_id','expected_employee_version','expected_group_version'}:raise APIError(400,'Provide the worker, group and both current versions.')
        worker_id=integer(data,'employee_id',1,9223372036854775807)
        worker=db.execute('SELECT * FROM employees WHERE id=? AND is_sample=0',(worker_id,)).fetchone()
        assignment=db.execute('SELECT * FROM employee_assignments WHERE employee_id=?',(worker_id,)).fetchone()
        if not worker or not assignment or assignment['legal_entity_id']!=group['legal_entity_id'] or (worker['country'],worker['currency'])!=(group['country'],group['currency']):raise APIError(400,'Assign the worker to the same employer, country and currency first.')
        if integer(data,'expected_employee_version',1,9223372036854775807)!=worker['version']:raise APIError(409,'The worker changed. Reload before changing payroll membership.')
        old=db.execute('SELECT * FROM pay_group_members WHERE employee_id=?',(worker_id,)).fetchone()
        handler.before_row=dict(old) if old else None
        db.execute('INSERT INTO pay_group_members VALUES(?,?) ON CONFLICT(employee_id) DO UPDATE SET pay_group_id=excluded.pay_group_id',(worker_id,group_id))
        for identifier in {group_id,old['pay_group_id'] if old else group_id}:db.execute('UPDATE pay_groups SET version=version+1 WHERE id=?',(identifier,))
        db.execute('UPDATE employees SET version=version+1 WHERE id=?',(worker_id,))
        handler.audit(db,user,'Membership changed','pay_group_members',worker_id)
        return 200,{'employee_id':worker_id,'pay_group_id':group_id},None
    first,last,paid,kind,reference=validate_period(data,group)
    if kind=='regular' and db.execute("SELECT 1 FROM pay_runs WHERE pay_group_id=? AND run_kind='regular' AND period_start<=? AND period_end>=?",(group_id,last.isoformat(),first.isoformat())).fetchone():raise APIError(409,'This group already has overlapping regular payroll.')
    workers=db.execute('SELECT e.*,a.cost_center_id,a.legal_entity_id FROM pay_group_members m JOIN employees e ON e.id=m.employee_id LEFT JOIN employee_assignments a ON a.employee_id=e.id WHERE m.pay_group_id=? AND e.is_sample=0 AND e.start_date<=? AND (e.end_date IS NULL OR e.end_date>=?) ORDER BY e.id',(group_id,last.isoformat(),first.isoformat())).fetchall()
    if not workers:raise APIError(400,'No eligible workers belong to this pay group in the selected period.')
    if any(w['legal_entity_id']!=group['legal_entity_id'] or (w['country'],w['currency'])!=(group['country'],group['currency']) or w['status']=='Inactive' and not w['end_date'] for w in workers):raise APIError(409,'Review stale employer assignments and employment end dates before preparing this group.')
    if kind=='regular':
        # Monthly legacy snapshots remain protected from double payment too.
        for worker in workers:
            if db.execute("SELECT 1 FROM pay_results p JOIN pay_runs r ON r.id=p.run_id WHERE p.employee_id=? AND r.pay_group_id IS NOT NULL AND r.run_kind='regular' AND r.period_start<=? AND r.period_end>=? LIMIT 1",(worker['id'],last.isoformat(),first.isoformat())).fetchone():raise APIError(409,'This worker already has overlapping regular payroll in another group. Use the original run or a reviewed adjustment.')
            legacy=db.execute('SELECT r.month FROM pay_results p JOIN pay_runs r ON r.id=p.run_id WHERE p.employee_id=? AND r.pay_group_id IS NULL',(worker['id'],)).fetchall()
            for row in legacy:
                year,month=map(int,row['month'].split('-'));start=date(year,month,1);end=date(year,month,calendar.monthrange(year,month)[1])
                if start<=last and end>=first:raise APIError(409,'A legacy monthly run overlaps this worker. Use a reviewed adjustment or another period.')
    key=f'G{group_id}:{first.isoformat()}:{last.isoformat()}:{kind}:{reference}'
    cursor=db.execute('INSERT INTO pay_runs(month,created_by,created_at,pay_group_id,pay_group_version,pay_group_name,period_start,period_end,pay_date,frequency,run_kind,reference) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,user['id'],now(),group_id,group['version'],group['name'],first.isoformat(),last.isoformat(),paid.isoformat(),group['frequency'],kind,reference))
    for worker in workers:
        gross=estimated_gross(db,worker,first,last) if kind=='regular' else 0
        calculation=json.dumps({'source':'period-estimate','basis':'calendar-month salary proration; external review required','period_start':first.isoformat(),'period_end':last.isoformat(),'run_kind':kind})
        db.execute('INSERT INTO pay_results(run_id,employee_id,employee_name,department,gross_paise,calculation,currency,country,legal_entity_id,cost_center_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(cursor.lastrowid,worker['id'],worker['name'],worker['department'],gross,calculation,worker['currency'],worker['country'],worker['legal_entity_id'],worker['cost_center_id']))
    handler.audit(db,user,'Created dated payroll','pay_runs',cursor.lastrowid)
    return 201,{'id':cursor.lastrowid},None
