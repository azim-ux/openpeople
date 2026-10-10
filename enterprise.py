"""Employer/cost-center snapshots and independently reviewed filing workpapers.

Packets use a provider-neutral format, not a government submission schema.
Receipt tracking records operator evidence, never authority verification.
"""
import hashlib
import json
import re


def schema(db):
    from workspace import execute_schema
    execute_schema(db, '''
    CREATE TABLE IF NOT EXISTS legal_entities(id INTEGER PRIMARY KEY,code TEXT NOT NULL UNIQUE,name TEXT NOT NULL,country TEXT NOT NULL,currency TEXT NOT NULL,employer_reference TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cost_centers(id INTEGER PRIMARY KEY,legal_entity_id INTEGER NOT NULL REFERENCES legal_entities(id),code TEXT NOT NULL,name TEXT NOT NULL,UNIQUE(legal_entity_id,code));
    CREATE TABLE IF NOT EXISTS employee_assignments(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL UNIQUE REFERENCES employees(id),legal_entity_id INTEGER NOT NULL REFERENCES legal_entities(id),cost_center_id INTEGER NOT NULL REFERENCES cost_centers(id));
    CREATE TABLE IF NOT EXISTS filing_packets(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES pay_runs(id),legal_entity_id INTEGER NOT NULL REFERENCES legal_entities(id),status TEXT NOT NULL DEFAULT 'Prepared',payload TEXT NOT NULL,sha256 TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES employees(id),reviewed_by INTEGER REFERENCES employees(id),created_at TEXT NOT NULL,review_note TEXT NOT NULL DEFAULT '',external_reference TEXT NOT NULL DEFAULT '',receipt_sha256 TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,UNIQUE(run_id,legal_entity_id));
    ''')
    columns={row['name'] for row in db.execute('PRAGMA table_info(pay_results)')}
    for name,definition in {'legal_entity_id':'INTEGER REFERENCES legal_entities(id)','cost_center_id':'INTEGER REFERENCES cost_centers(id)'}.items():
        if name not in columns:db.execute(f'ALTER TABLE pay_results ADD COLUMN {name} {definition}')


def metadata(row,user,db):
    result={key:value for key,value in dict(row).items() if key!='payload'}
    maker=db.execute('SELECT 1 FROM pay_run_editors WHERE run_id=? AND employee_id=?',(row['run_id'],user['id'])).fetchone()
    creator=db.execute('SELECT created_by FROM pay_runs WHERE id=?',(row['run_id'],)).fetchone()[0]
    result.update(authority_verified=False,can_review=row['status']=='Prepared' and user['id'] not in (row['created_by'],creator) and not maker)
    return result


def state(db,user):
    if user['role'] not in ('hr','payroll'):
        return {'legal_entities':[],'cost_centers':[],'employee_assignments':[],'filing_packets':[]}
    from access import entity_allowed
    return {'legal_entities':[dict(r) for r in db.execute('SELECT * FROM legal_entities ORDER BY code') if entity_allowed(db,user,r['id'])],
            'cost_centers':[dict(r) for r in db.execute('SELECT * FROM cost_centers ORDER BY code') if entity_allowed(db,user,r['legal_entity_id'])],
            'employee_assignments':[dict(r) for r in db.execute('SELECT * FROM employee_assignments') if entity_allowed(db,user,r['legal_entity_id'])],
            'filing_packets':[metadata(r,user,db) for r in db.execute('SELECT * FROM filing_packets ORDER BY id DESC LIMIT 100') if entity_allowed(db,user,r['legal_entity_id'])]}


def api(handler,db,path,data,user):
    from server import APIError, integer, text_field, now
    from localization import COUNTRIES, CURRENCIES
    from workspace import security_event
    method=handler.command
    if not path.startswith(('/api/legal_entities','/api/cost_centers','/api/employee_assignments','/api/filing_packets','/api/statutory')):
        return None
    if not user or user['role'] not in ('hr','payroll'):
        raise APIError(403,'HR or payroll access is required.')
    if path=='/api/statutory' and method=='GET':
        from statutory import catalog, input_template
        from statutory_uk import template
        return 200,{**catalog(),'input_template':input_template(),'input_templates':{'US':input_template(),'GB':template()}},None
    if path=='/api/statutory/preview' and method=='POST':
        from statutory import calculate
        try:result=calculate(data)
        except ValueError as error:raise APIError(400,str(error)) from None
        return 200,result,None
    if path in ('/api/legal_entities','/api/cost_centers','/api/employee_assignments') and method=='POST':
        handler.require_hr(user)
        if path=='/api/legal_entities':
            if set(data)!={'code','name','country','currency','employer_reference'}:raise APIError(400,'Provide the complete employer form.')
            code=text_field(data,'code',40);name=text_field(data,'name',100)
            country=data.get('country');currency=data.get('currency')
            if not isinstance(country,str) or country not in COUNTRIES or not isinstance(currency,str) or currency not in CURRENCIES:raise APIError(400,'Choose a supported country and currency.')
            if not re.fullmatch('[A-Z0-9_-]{1,40}',code):raise APIError(400,'Employer codes use uppercase letters, digits, underscore and dash.')
            cursor=db.execute('INSERT INTO legal_entities(code,name,country,currency,employer_reference,created_at) VALUES(?,?,?,?,?,?)',(code,name,country,currency,text_field(data,'employer_reference',100),now()))
            entity='legal_entities'
        elif path=='/api/cost_centers':
            if set(data)!={'legal_entity_id','code','name'}:raise APIError(400,'Provide the complete cost-center form.')
            parent=integer(data,'legal_entity_id',1,9223372036854775807)
            if not db.execute('SELECT 1 FROM legal_entities WHERE id=?',(parent,)).fetchone():raise APIError(400,'Choose an existing employer.')
            cursor=db.execute('INSERT INTO cost_centers(legal_entity_id,code,name) VALUES(?,?,?)',(parent,text_field(data,'code',40),text_field(data,'name',100)))
            entity='cost_centers'
        else:
            if set(data)!={'employee_id','legal_entity_id','cost_center_id','expected_version'}:raise APIError(400,'Provide the complete assignment and current employee version.')
            employee=integer(data,'employee_id',1,9223372036854775807)
            parent=integer(data,'legal_entity_id',1,9223372036854775807)
            center=integer(data,'cost_center_id',1,9223372036854775807)
            worker=db.execute('SELECT * FROM employees WHERE id=? AND is_sample=0',(employee,)).fetchone()
            employer=db.execute('SELECT * FROM legal_entities WHERE id=?',(parent,)).fetchone()
            if not worker or not employer or not db.execute('SELECT 1 FROM cost_centers WHERE id=? AND legal_entity_id=?',(center,parent)).fetchone():raise APIError(400,'Choose a real worker and a cost center belonging to this employer.')
            if (worker['country'],worker['currency'])!=(employer['country'],employer['currency']):raise APIError(400,'Worker and employer country and currency must agree before assignment.')
            if integer(data,'expected_version',1,9223372036854775807)!=worker['version']:raise APIError(409,'This employee changed. Reload before assigning an employer.')
            prior=db.execute('SELECT * FROM employee_assignments WHERE employee_id=?',(employee,)).fetchone()
            handler.before_row=dict(prior) if prior else None
            db.execute('INSERT INTO employee_assignments(employee_id,legal_entity_id,cost_center_id) VALUES(?,?,?) ON CONFLICT(employee_id) DO UPDATE SET legal_entity_id=excluded.legal_entity_id,cost_center_id=excluded.cost_center_id',(employee,parent,center))
            record=db.execute('SELECT id FROM employee_assignments WHERE employee_id=?',(employee,)).fetchone()[0]
            db.execute('UPDATE employees SET version=version+1 WHERE id=?',(employee,))
            handler.audit(db,user,'Assigned','employee_assignments',record)
            return 200,{'id':record},None
        handler.audit(db,user,'Created',entity,cursor.lastrowid)
        return 201,{'id':cursor.lastrowid},None
    assignment_match=re.fullmatch(r'/api/employee_assignments/(\d{1,19})',path)
    if assignment_match and method=='PATCH':
        handler.require_hr(user)
        record=int(assignment_match[1])
        if record>9223372036854775807:raise APIError(400,'Choose a valid assignment.')
        row=db.execute('SELECT * FROM employee_assignments WHERE id=?',(record,)).fetchone()
        if not row:raise APIError(404,'Assignment not found.')
        if set(data)!={'expected_version','remove'} or data.get('remove') is not True:raise APIError(400,'Provide the current employee version and explicit removal.')
        worker=db.execute('SELECT version FROM employees WHERE id=?',(row['employee_id'],)).fetchone()
        if integer(data,'expected_version',1,9223372036854775807)!=worker['version']:raise APIError(409,'The employee changed. Reload before removing an assignment.')
        handler.before_row=dict(row)
        db.execute('DELETE FROM employee_assignments WHERE id=?',(record,))
        db.execute('UPDATE employees SET version=version+1 WHERE id=?',(row['employee_id'],))
        handler.audit(db,user,'Removed','employee_assignments',record)
        return 200,{'id':record},None
    if path=='/api/filing_packets' and method=='POST':
        if set(data)!={'run_id','legal_entity_id','expected_version'}:raise APIError(400,'Choose a reviewed payroll version and employer.')
        run_id=integer(data,'run_id',1,9223372036854775807);parent=integer(data,'legal_entity_id',1,9223372036854775807)
        run=db.execute('SELECT * FROM pay_runs WHERE id=?',(run_id,)).fetchone()
        employer=db.execute('SELECT * FROM legal_entities WHERE id=?',(parent,)).fetchone()
        from access import entity_allowed
        if not entity_allowed(db,user,parent):raise APIError(404,'Payroll or employer not found.')
        if not run or not employer:raise APIError(404,'Payroll or employer not found.')
        if run['status']!='Finalized':raise APIError(409,'Finalize payroll with independent review before preparing a filing packet.')
        if integer(data,'expected_version',1,9223372036854775807)!=run['version']:raise APIError(409,'Review the current payroll version before preparing a packet.')
        rows=[dict(r) for r in db.execute('SELECT * FROM pay_results WHERE run_id=? AND legal_entity_id=? ORDER BY employee_id',(run_id,parent))]
        if not rows or any(not r['external_result'] for r in rows):raise APIError(409,'This employer needs externally reviewed payroll results for every included worker. Assign employers before creating payroll.')
        if any((r['country'],r['currency'])!=(employer['country'],employer['currency']) for r in rows):raise APIError(409,'Snapshot countries or currencies do not match this employer.')
        from payroll import COUNTRY_REQUIREMENTS
        payload={'format':'openpeople.filing-workpaper.v1','agency_submission_format':False,'government_submission_supported':False,'employer':dict(employer),'month':run['month'],'pay_run_id':run_id,'pay_run_version':run['version'],'country_requirements':COUNTRY_REQUIREMENTS.get(employer['country'],{'topics':['External jurisdiction review required']}),'statements':rows,'totals':{'gross_minor':sum(r['gross_paise'] for r in rows),'deductions_minor':sum(r['deductions_paise'] for r in rows),'currency':employer['currency']}}
        from pay_periods import period_contract
        if period_contract(run):payload['period']=period_contract(run)
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True)
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        cursor=db.execute('INSERT INTO filing_packets(run_id,legal_entity_id,payload,sha256,created_by,created_at) VALUES(?,?,?,?,?,?)',(run_id,parent,encoded,digest,user['id'],now()))
        handler.audit(db,user,'Prepared','filing_packets',cursor.lastrowid)
        return 201,{'id':cursor.lastrowid,'sha256':digest,'authority_verified':False},None
    match=re.fullmatch(r'/api/filing_packets/(\d{1,19})(/export)?',path)
    if match:
        record=int(match[1])
        if record>9223372036854775807:raise APIError(400,'Choose a valid packet identifier.')
        row=db.execute('SELECT * FROM filing_packets WHERE id=?',(record,)).fetchone()
        if not row:raise APIError(404,'Filing packet not found.')
        from access import entity_allowed
        if not entity_allowed(db,user,row['legal_entity_id']):raise APIError(404,'Filing packet not found.')
        if method=='GET':
            if match[2]:
                if hashlib.sha256(row['payload'].encode()).hexdigest()!=row['sha256']:raise APIError(409,'The packet failed its integrity check.')
                # Read-only export; no network transmission or status transition.
                return 200,{'packet':json.loads(row['payload']),'sha256':row['sha256'],'authority_verified':False},None
            return 200,metadata(row,user,db),None
        if method=='PATCH' and not match[2]:
            if hashlib.sha256(row['payload'].encode()).hexdigest()!=row['sha256']:raise APIError(409,'The packet failed its integrity check.')
            if 'expected_version' not in data:raise APIError(428,'Review the current packet version first.')
            if integer(data,'expected_version',1,9223372036854775807)!=row['version']:raise APIError(409,'The filing packet changed; reload before continuing.')
            handler.before_row=dict(row)
            target=data.get('status')
            if row['status']=='Prepared' and target=='Reviewed':
                if set(data)!={'expected_version','status','review_note'}:raise APIError(400,'Provide only the version, Reviewed status and review note.')
                if not metadata(row,user,db)['can_review']:raise APIError(403,'An independent colleague must review this packet and underlying payroll.')
                db.execute('UPDATE filing_packets SET status=?,reviewed_by=?,review_note=?,version=version+1 WHERE id=?',(target,user['id'],text_field(data,'review_note',500),record))
            elif (row['status'],target) in (('Reviewed','Submitted externally'),('Submitted externally','Accepted externally'),('Submitted externally','Rejected externally')):
                if set(data)!={'expected_version','status','external_reference','receipt_sha256'}:raise APIError(400,'Record the external reference and SHA-256 of your retained receipt.')
                receipt=data.get('receipt_sha256')
                if not isinstance(receipt,str) or not re.fullmatch('[0-9a-f]{64}',receipt):raise APIError(400,'Provide a SHA-256 digest of the externally obtained receipt.')
                reference=text_field(data,'external_reference',200)
                db.execute('UPDATE filing_packets SET status=?,external_reference=?,receipt_sha256=?,version=version+1 WHERE id=?',(target,reference,receipt,record))
            else:raise APIError(409,'This filing transition is unavailable. Submitted and accepted statuses record external evidence only.')
            handler.audit(db,user,'Status recorded','filing_packets',record)
            security_event(db,'External filing evidence recorded' if target!='Reviewed' else 'Filing packet reviewed',user['id'],handler.client_address[0],{'packet_id':record,'status':target,'authority_verified':False})
            return 200,metadata(db.execute('SELECT * FROM filing_packets WHERE id=?',(record,)).fetchone(),user,db),None
    return None
