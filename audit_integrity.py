"""Append-only audit chains. Keep an exported anchor separately to detect rollback.

These hashes detect corruption, not a database owner's deliberate full rewrite.
An independent retained anchor is essential; no database-local hash is a signature.
"""
import hashlib
import json

TABLES = {'audit': ('id','actor_id','action','entity','entity_id','created_at','details'),
          'security_events': ('id','actor_id','action','address','created_at','details')}
ZERO = '0' * 64


def digest(previous, kind, payload):
    value = ['openpeople.audit-chain.v1',previous,kind,json.loads(payload)]
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def register(db):
    db.create_function('audit_digest',3,digest,deterministic=True)


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS audit_seals(kind TEXT NOT NULL,row_id INTEGER NOT NULL,previous TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(kind,row_id))')
    for kind,columns in TABLES.items():
        # Seal pre-upgrade history only once. Its truth was not previously verified.
        if not db.execute('SELECT 1 FROM audit_seals WHERE kind=? LIMIT 1',(kind,)).fetchone():
            previous=ZERO
            for row in db.execute(f'SELECT * FROM {kind} ORDER BY id'):
                payload=json.dumps({key:row[key] for key in columns})
                current=digest(previous,kind,payload)
                db.execute('INSERT INTO audit_seals VALUES(?,?,?,?)',(kind,row['id'],previous,current))
                previous=current
        fields=','.join("'%s',NEW.%s" % (key,key) for key in columns)
        previous=f"COALESCE((SELECT digest FROM audit_seals WHERE kind='{kind}' ORDER BY row_id DESC LIMIT 1),'{ZERO}')"
        db.execute(f"CREATE TRIGGER IF NOT EXISTS {kind}_seal AFTER INSERT ON {kind} BEGIN INSERT INTO audit_seals VALUES('{kind}',NEW.id,{previous},audit_digest({previous},'{kind}',json_object({fields}))); END")
    for table in (*TABLES,'audit_seals'):
        for operation in ('UPDATE','DELETE'):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_deny_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Audit history is append-only'); END")


def verify(db, anchor=None, maximum=200000):
    if maximum is not None and (type(maximum) is not int or maximum<1):raise ValueError('Use a positive audit budget or None for full offline verification.')
    result={'format':'openpeople.audit-anchor.v1','chains':{},'passed':True,
            'independent_anchor_compared':anchor is not None,'database_owner_tamper_resistant':False}
    if anchor is not None and (not isinstance(anchor,dict) or anchor.get('format')!=result['format'] or not isinstance(anchor.get('chains'),dict)):
        raise ValueError('Use a previously retained OpenPeople audit anchor.')
    for kind,columns in TABLES.items():
        previous=ZERO; count=0; last_id=0; seen_anchor=False
        known=anchor['chains'].get(kind) if anchor is not None else None
        if anchor is not None and (not isinstance(known,dict) or type(known.get('count')) is not int or known['count']<0 or type(known.get('last_id')) is not int or not isinstance(known.get('digest'),str)):
            raise ValueError('The retained audit anchor is incomplete.')
        if known and known['count']==0:seen_anchor=known['last_id']==0 and known['digest']==ZERO
        query=f"SELECT e.*,s.previous AS sealed_previous,s.digest AS sealed_digest FROM {kind} e LEFT JOIN audit_seals s ON s.kind=? AND s.row_id=e.id ORDER BY e.id"
        for row in db.execute(query,(kind,)):
            count+=1
            if maximum is not None and count>maximum:
                result['passed']=False;result['limit_exceeded']=True;break
            current=digest(previous,kind,json.dumps({key:row[key] for key in columns}))
            if row['sealed_previous']!=previous or row['sealed_digest']!=current:result['passed']=False
            previous=current;last_id=row['id']
            if known and count==known['count']:seen_anchor=known['last_id']==last_id and known['digest']==current
        if count!=db.execute('SELECT count(*) FROM audit_seals WHERE kind=?',(kind,)).fetchone()[0]:result['passed']=False
        if anchor is not None and not seen_anchor:result['passed']=False
        result['chains'][kind]={'count':count,'last_id':last_id,'digest':previous}
    return result
