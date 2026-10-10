"""Employer-scoped payroll access; HR remains the workspace administrator.

Legacy payroll members keep their previous workspace access until HR explicitly
restricts them. Restrictions apply to historical snapshot employers, not the
worker's current assignment, and revoke sessions on policy changes.
"""
import json
import re
import time


def schema(db):
    from workspace import execute_schema
    execute_schema(db, '''
    CREATE TABLE IF NOT EXISTS payroll_access(employee_id INTEGER PRIMARY KEY REFERENCES employees(id),mode TEXT NOT NULL CHECK(mode IN ('all','restricted')),version INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS payroll_access_entities(employee_id INTEGER NOT NULL REFERENCES payroll_access(employee_id),legal_entity_id INTEGER NOT NULL REFERENCES legal_entities(id),PRIMARY KEY(employee_id,legal_entity_id));
    ''')


def entities(db,user):
    if user['role']!='payroll':return None
    row=db.execute('SELECT mode FROM payroll_access WHERE employee_id=?',(user['id'],)).fetchone()
    if not row or row['mode']=='all':return None
    return {r[0] for r in db.execute('SELECT legal_entity_id FROM payroll_access_entities WHERE employee_id=?',(user['id'],))}


def entity_allowed(db,user,entity_id):
    allowed=entities(db,user)
    return allowed is None or entity_id in allowed


def run_scope(db,user,run_id):
    allowed=entities(db,user)
    rows=db.execute('SELECT legal_entity_id FROM pay_results WHERE run_id=?',(run_id,)).fetchall()
    return allowed is None or bool(rows) and all(r[0] in allowed for r in rows)


def permissions(db):
    result=[]
    for row in db.execute("SELECT id,name FROM employees WHERE role='payroll' AND is_sample=0 ORDER BY name"):
        current=db.execute('SELECT * FROM payroll_access WHERE employee_id=?',(row['id'],)).fetchone()
        result.append({'employee_id':row['id'],'name':row['name'],'mode':current['mode'] if current else 'all','version':current['version'] if current else 0,'entity_ids':[r[0] for r in db.execute('SELECT legal_entity_id FROM payroll_access_entities WHERE employee_id=?',(row['id'],))]})
    return result


def api(handler,db,path,data,user):
    from server import APIError, integer, now
    from workspace import security_event, set_setting, setting
    if path=='/api/payroll_access' and handler.command=='GET':
        handler.require_hr(user)
        return 200,{'members':permissions(db)},None
    match=re.fullmatch(r'/api/payroll_access/(\d{1,19})',path)
    if not match or handler.command!='POST':return None
    handler.require_hr(user)
    if time.time()-user['auth_time']>300:raise APIError(403,'Sign in again before changing payroll access.')
    record=int(match[1])
    if record>9223372036854775807:raise APIError(400,'Choose a valid payroll member.')
    worker=db.execute("SELECT id FROM employees WHERE id=? AND role='payroll' AND is_sample=0 AND status='Active'",(record,)).fetchone()
    if not worker:raise APIError(400,'Choose an active payroll member.')
    if set(data)!={'mode','entity_ids','expected_version'} or data.get('mode') not in ('all','restricted'):
        raise APIError(400,'Provide the complete payroll access form.')
    ids=data['entity_ids']
    if not isinstance(ids,list) or len(ids)>1000 or any(type(item) is not int or not 1<=item<=9223372036854775807 for item in ids) or len(set(ids))!=len(ids):raise APIError(400,'Choose distinct valid employer identifiers.')
    if data['mode']=='all' and ids:raise APIError(400,'Workspace access must not contain employer restrictions.')
    for entity in ids:
        if not db.execute('SELECT 1 FROM legal_entities WHERE id=?',(entity,)).fetchone():raise APIError(400,'An employer no longer exists.')
    old=db.execute('SELECT * FROM payroll_access WHERE employee_id=?',(record,)).fetchone()
    expected=integer(data,'expected_version',0,9223372036854775807)
    if expected!=(old['version'] if old else 0):raise APIError(409,'Payroll access changed. Reload before saving.')
    before=next(r for r in permissions(db) if r['employee_id']==record)
    db.execute('INSERT INTO payroll_access(employee_id,mode,version) VALUES(?,?,?) ON CONFLICT(employee_id) DO UPDATE SET mode=excluded.mode,version=excluded.version',(record,data['mode'],expected+1))
    db.execute('DELETE FROM payroll_access_entities WHERE employee_id=?',(record,))
    db.executemany('INSERT INTO payroll_access_entities VALUES(?,?)',[(record,entity) for entity in ids])
    db.execute('DELETE FROM sessions WHERE employee_id=?',(record,))
    after={'employee_id':record,'mode':data['mode'],'entity_ids':ids,'version':expected+1}
    db.execute('INSERT INTO audit(actor_id,action,entity,entity_id,created_at,details) VALUES(?,?,?,?,?,?)',(user['id'],'Payroll access changed','payroll_access',record,now(),json.dumps({'before':before,'after':after})))
    security_event(db,'Payroll access changed and sessions revoked',user['id'],handler.client_address[0],{'employee_id':record,'mode':data['mode']})
    set_setting(db,'revision',setting(db,'revision',0)+1)
    return 200,after,None
