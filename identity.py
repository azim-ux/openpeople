"""Authenticator MFA and optional OIDC authorization-code sign-in with PKCE."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode

import jwt
import requests


def totp(secret, at=None):
    counter = int((time.time() if at is None else at)//30)
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack('>Q',counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack('>I',digest[offset:offset+4])[0] & 0x7fffffff)%1000000).zfill(6)


def check_totp(secret, code, last_counter=-1):
    if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):
        return None
    current = int(time.time()//30)
    for counter in (current,current-1,current+1):
        if counter > last_counter and hmac.compare_digest(totp(secret,counter*30),code):
            return counter
    return None


def verify_login_factor(db, server, employee, code, recovery_code=None, keep_session=None):
    from server import APIError
    if recovery_code:
        if code or not employee['totp_secret'] or not isinstance(recovery_code,str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{8}){3}',recovery_code):
            raise APIError(401,'Enter one valid authenticator code or unused recovery code.')
        digest=hashlib.sha256(recovery_code.encode()).hexdigest()
        if db.execute('DELETE FROM mfa_recovery_codes WHERE employee_id=? AND digest=?',(employee['id'],digest)).rowcount!=1:
            raise APIError(401,'The recovery code is invalid or already used.')
        if keep_session:
            db.execute('DELETE FROM sessions WHERE employee_id=? AND token<>?',(employee['id'],keep_session))
        else:db.execute('DELETE FROM sessions WHERE employee_id=?',(employee['id'],))
        from workspace import security_event
        security_event(db,'MFA recovery code used',employee['id'])
        return
    if employee['totp_secret']:
        secret = server.vault.decrypt(employee['totp_secret'].encode()).decode()
        counter = check_totp(secret,code,employee['totp_counter'])
        if counter is None:
            raise APIError(401,'Enter a current authenticator code that has not already been used.')
        db.execute('UPDATE employees SET totp_counter=? WHERE id=?',(counter,employee['id']))


def oidc_config(server):
    from server import APIError
    issuer = os.environ.get('OPENPEOPLE_OIDC_ISSUER','')
    client = os.environ.get('OPENPEOPLE_OIDC_CLIENT_ID','')
    if not issuer.startswith('https://') or not client:
        raise APIError(400,'Configure a trusted HTTPS OpenID Connect issuer and client on the server.')
    origin = server.public_origin or f'http://127.0.0.1:{server.server_port}'
    return issuer,client,origin+'/api/sso/callback'


def metadata_for(issuer):
    from server import APIError
    response=requests.get(issuer.rstrip('/')+'/.well-known/openid-configuration',timeout=8,allow_redirects=False)
    response.raise_for_status()
    metadata=response.json()
    if metadata.get('issuer') != issuer or any(not str(metadata.get(key,'')).startswith('https://') for key in ('authorization_endpoint','token_endpoint','jwks_uri')):
        raise APIError(400,'The identity provider metadata does not match the configured HTTPS issuer.')
    return metadata


def identity_api(handler,db,path,query,data,user):
    from server import APIError, password_matches, password_hash, password_field
    from workspace import security_event, setting
    method=handler.command
    if path=='/api/sessions' and method=='GET':
        rows=[{'id':row['public_id'],'signed_in_at':row['auth_time'],'last_activity':row['last_seen'],'expires_at':row['expires'],'current':row['token']==user['token']} for row in db.execute('SELECT * FROM sessions WHERE employee_id=? AND expires>? AND last_seen>? ORDER BY auth_time DESC',(user['id'],time.time(),time.time()-1800))]
        return 200,{'rows':rows},None
    if path.startswith('/api/sessions/') and method=='PATCH':
        identifier=path.rsplit('/',1)[-1]
        if not re.fullmatch(r'[0-9a-f]{32}',identifier) or data.get('revoke') is not True:raise APIError(400,'Choose a session to revoke.')
        row=db.execute('SELECT * FROM sessions WHERE public_id=? AND employee_id=?',(identifier,user['id'])).fetchone()
        if not row:raise APIError(404,'Session not found.')
        if row['token']==user['token']:raise APIError(400,'Use Sign out to end your current session.')
        db.execute('DELETE FROM sessions WHERE public_id=?',(identifier,))
        security_event(db,'Session revoked',user['id'],handler.client_address[0],{'session_id':identifier})
        return 200,{'ok':True},None
    if path == '/api/security' and method == 'GET':
        return 200,{'mfa_enabled':bool(user['totp_secret']),'mfa_required':setting(db,'require_mfa',False),'sso_enabled':bool(os.environ.get('OPENPEOPLE_OIDC_ISSUER')),'idle_timeout_minutes':30,'absolute_timeout_hours':8,'recovery_codes_remaining':db.execute('SELECT count(*) FROM mfa_recovery_codes WHERE employee_id=?',(user['id'],)).fetchone()[0]},None
    if path=='/api/mfa/recovery-codes' and method=='POST':
        if not user['totp_secret'] or not user['mfa_verified'] or time.time()-user['auth_time']>300:
            raise APIError(403,'Sign in with your authenticator again before generating recovery codes.')
        verify_login_factor(db,handler.server,user,data.get('otp',''))
        codes=['-'.join(value[i:i+8] for i in range(0,32,8)) for value in (secrets.token_hex(16) for _ in range(10))]
        db.execute('DELETE FROM mfa_recovery_codes WHERE employee_id=?',(user['id'],))
        db.executemany('INSERT INTO mfa_recovery_codes VALUES(?,?)',[(user['id'],hashlib.sha256(code.encode()).hexdigest()) for code in codes])
        security_event(db,'MFA recovery codes replaced',user['id'],handler.client_address[0],{'count':len(codes)})
        return 201,{'codes':codes},None
    if path == '/api/mfa/begin' and method == 'POST':
        if time.time()-user['auth_time'] > 300:
            raise APIError(403,'Sign out and sign in again before setting up your authenticator.')
        if user['totp_secret']:
            raise APIError(409,'An authenticator is already enabled.')
        secret=base64.b32encode(secrets.token_bytes(20)).decode()
        db.execute('UPDATE employees SET totp_pending=? WHERE id=?',(handler.server.vault.encrypt(secret.encode()).decode(),user['id']))
        uri='otpauth://totp/'+requests.utils.quote('OpenPeople:'+user['email'],safe='')+'?'+urlencode({'secret':secret,'issuer':'OpenPeople','algorithm':'SHA1','digits':6,'period':30})
        return 200,{'secret':secret,'uri':uri},None
    if path == '/api/mfa/confirm' and method == 'POST':
        if not user['totp_pending'] or time.time()-user['auth_time'] > 300:
            raise APIError(400,'Start a new authenticator setup after signing in.')
        secret=handler.server.vault.decrypt(user['totp_pending'].encode()).decode()
        counter=check_totp(secret,data.get('otp',''))
        if counter is None:
            raise APIError(400,'Enter a valid six-digit authenticator code.')
        db.execute('UPDATE employees SET totp_secret=totp_pending,totp_pending=NULL,totp_counter=? WHERE id=?',(counter,user['id']))
        db.execute('DELETE FROM sessions WHERE employee_id=? AND token<>?',(user['id'],user['token']))
        db.execute('UPDATE sessions SET mfa_verified=1 WHERE token=?',(user['token'],))
        security_event(db,'Authenticator enabled',user['id'],handler.client_address[0])
        return 200,{'ok':True},None
    if path == '/api/mfa/verify' and method == 'POST':
        if not user['totp_secret']:
            raise APIError(400,'Enroll an authenticator first.')
        verify_login_factor(db,handler.server,user,data.get('otp',''),data.get('recovery_code'),user['token'])
        db.execute('UPDATE sessions SET mfa_verified=1 WHERE token=?',(user['token'],))
        security_event(db,'SSO authenticator verified',user['id'],handler.client_address[0])
        return 200,{'ok':True},None
    if path == '/api/password' and method == 'POST':
        current=password_field({'password':data.get('current_password')})
        new=password_field({'password':data.get('new_password')})
        if not user['password'] or not password_matches(current,user['password']):
            raise APIError(403,'The current local password is incorrect.')
        if len(new)<12:
            raise APIError(400,'Use at least 12 characters for your new password.')
        db.execute('UPDATE employees SET password=? WHERE id=?',(password_hash(new),user['id']))
        db.execute('DELETE FROM mfa_recovery_codes WHERE employee_id=?',(user['id'],))
        db.execute('DELETE FROM sessions WHERE employee_id=?',(user['id'],))
        csrf,cookie=handler.new_session(db,user['id'],bool(user['mfa_verified']))
        security_event(db,'Password changed',user['id'],handler.client_address[0])
        return 200,{'csrf':csrf},cookie
    if path == '/api/sso/start' and method == 'GET':
        try:
            issuer,client,callback=oidc_config(handler.server)
            metadata=metadata_for(issuer)
        except requests.RequestException as error:
            raise APIError(503,'The identity provider is unavailable.') from error
        state,nonce,verifier=secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        db.execute('DELETE FROM oidc_states WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO oidc_states VALUES(?,?,?,?)',(hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,time.time()+300))
        url=metadata['authorization_endpoint']+'?'+urlencode({'client_id':client,'redirect_uri':callback,'response_type':'code','scope':'openid email profile','state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'})
        cookie=f'openpeople_sso={state}; HttpOnly; SameSite=Lax; Path=/api/sso; Max-Age=300'+('; Secure' if handler.server.public_origin else '')
        return 200,{'url':url},cookie
    if path == '/api/sso/callback' and method == 'GET':
        try:
            issuer,client,callback=oidc_config(handler.server)
            state=query.get('state',[''])[0]
            cookie=SimpleCookie();cookie.load(handler.headers.get('Cookie',''))
            cookie_state=cookie['openpeople_sso'].value if 'openpeople_sso' in cookie else ''
            if not re.fullmatch(r'[A-Za-z0-9_-]{40,100}',state) or not hmac.compare_digest(state,cookie_state):
                raise APIError(401,'The sign-in request could not be verified.')
            digest=hashlib.sha256(state.encode()).hexdigest()
            pending=db.execute('SELECT * FROM oidc_states WHERE state=? AND expires>?',(digest,time.time())).fetchone()
            if not pending:
                raise APIError(401,'This sign-in request expired or was already used.')
            metadata=metadata_for(issuer)
            code=query.get('code',[''])[0]
            if not code or len(code)>2048:
                raise APIError(401,'The identity provider did not return a valid authorization code.')
            payload={'grant_type':'authorization_code','code':code,'redirect_uri':callback,'client_id':client,'code_verifier':pending['verifier']}
            secret=os.environ.get('OPENPEOPLE_OIDC_CLIENT_SECRET')
            token_response=requests.post(metadata['token_endpoint'],data=payload,auth=(client,secret) if secret else None,timeout=8,allow_redirects=False)
            token_response.raise_for_status()
            token=token_response.json().get('id_token','')
            if not isinstance(token,str) or len(token)>32768:
                raise APIError(401,'The identity token is invalid.')
            header=jwt.get_unverified_header(token)
            if header.get('alg') not in ('RS256','ES256'):
                raise APIError(401,'The identity token uses an unsupported signature algorithm.')
            key_response=requests.get(metadata['jwks_uri'],timeout=8,allow_redirects=False)
            key_response.raise_for_status()
            keys=[key for key in key_response.json().get('keys',[]) if key.get('kid')==header.get('kid') and key.get('use','sig')=='sig' and key.get('alg',header['alg'])==header['alg']]
            if len(keys)!=1:
                raise APIError(401,'The identity signing key is not recognized.')
            key=jwt.PyJWK.from_dict(keys[0],algorithm=header['alg']).key
            claims=jwt.decode(token,key,algorithms=[header['alg']],audience=client,issuer=issuer,options={'require':['exp','iat','iss','aud','sub','nonce']},leeway=15)
            if not isinstance(claims['nonce'],str) or not hmac.compare_digest(claims['nonce'],pending['nonce']) or claims.get('email_verified') is not True:
                raise APIError(401,'The identity provider must verify this email and sign-in request.')
            if (isinstance(claims['aud'],list) and len(claims['aud'])>1 and claims.get('azp')!=client) or (claims.get('azp') and claims['azp']!=client):
                raise APIError(401,'This token was issued to another client.')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('DELETE FROM oidc_states WHERE state=? AND expires>?',(digest,time.time())).rowcount!=1:
                raise APIError(401,'This sign-in request expired or was already used.')
            link=db.execute('SELECT employee_id FROM oidc_links WHERE issuer=? AND subject=?',(issuer,claims['sub'])).fetchone()
            employee=db.execute('SELECT * FROM employees WHERE id=? AND status=?',(link['employee_id'],'Active')).fetchone() if link else db.execute('SELECT * FROM employees WHERE email=? COLLATE NOCASE AND status=?',(claims.get('email',''),'Active')).fetchone()
            if not employee:
                raise APIError(403,'Ask HR to provision your account before signing in.')
            if not link:
                other=db.execute('SELECT subject FROM oidc_links WHERE issuer=? AND employee_id=?',(issuer,employee['id'])).fetchone()
                if other:
                    raise APIError(403,'This employee is linked to a different provider identity.')
                db.execute('INSERT INTO oidc_links VALUES(?,?,?)',(issuer,claims['sub'],employee['id']))
            needs_factor=bool(employee['totp_secret'] or setting(db,'require_mfa',False))
            csrf,session_cookie=handler.new_session(db,employee['id'],not needs_factor)
            security_event(db,'SSO login succeeded',employee['id'],handler.client_address[0])
            return 303,{'redirect':'/'},session_cookie
        except (requests.RequestException,jwt.PyJWTError,ValueError,KeyError,TypeError) as error:
            raise APIError(401,'The identity provider response could not be verified.') from error
    return None
