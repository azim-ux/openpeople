"""Create private self-hosted Dex/client configuration; no service installation.

Requires operator-selected HTTPS addresses, certificates and provisioned users.
Existing files and the currently running HR instance are never changed.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID
from datetime import datetime,timezone


def configure_identity(target,origin,issuer,certificate,key,ca,users):
    origins=[]
    for value in (origin,issuer):
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(ord(c)<33 for c in value):raise ValueError('Choose trusted HTTPS addresses without credentials, fragments or query strings.')
        origins.append(parsed)
    if origins[0].path or issuer.endswith('/'):raise ValueError('Use the exact HR origin and canonical issuer without a trailing slash.')
    paths=[Path(path).resolve(strict=True) for path in (certificate,key,ca)]
    if any(not p.is_file() for p in paths):raise ValueError('Choose existing ordinary certificate, key and CA files.')
    if os.name=='posix' and paths[1].stat().st_mode & 0o077:raise ValueError('The TLS private key must have private permissions (0600).')
    cert=x509.load_pem_x509_certificate(paths[0].read_bytes())
    private=serialization.load_pem_private_key(paths[1].read_bytes(),password=None)
    public=lambda item:item.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(cert.public_key())!=public(private.public_key()):raise ValueError('The certificate does not match the private key.')
    current=datetime.now(timezone.utc)
    if not cert.not_valid_before_utc<=current<cert.not_valid_after_utc:raise ValueError('The identity certificate is expired or not yet valid.')
    try:san=cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    except x509.ExtensionNotFound:raise ValueError('The identity certificate must name the issuer host in its SAN.') from None
    host=origins[1].hostname
    try:matched=ipaddress.ip_address(host) in san.get_values_for_type(x509.IPAddress)
    except ValueError:matched=host.lower() in [name.lower() for name in san.get_values_for_type(x509.DNSName)]
    if not matched:raise ValueError('The certificate must explicitly name the issuer host. Wildcard matching is not supported by this generator.')
    if not isinstance(users,list) or not 1<=len(users)<=10000:raise ValueError('Supply provisioned identity users; no public registration is enabled.')
    clean=[];emails=set();subjects=set()
    for user in users:
        if not isinstance(user,dict) or set(user)!={'email','username','userID','hash','emailVerified'}:raise ValueError('Supply complete reviewed Dex identity records.')
        email=user['email'];subject=user['userID'];password=user['hash']
        if not isinstance(email,str) or not re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,189}',email) or email.lower() in emails:raise ValueError('Identity emails must be valid and unique.')
        if not isinstance(subject,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',subject) or subject in subjects:raise ValueError('Identity subjects must be stable and unique.')
        if not isinstance(user['username'],str) or not 1<=len(user['username'])<=100 or any(ord(c)<32 for c in user['username']) or user['emailVerified'] is not True:raise ValueError('Review names and email ownership before provisioning.')
        if not isinstance(password,str) or not re.fullmatch(r'\$2[aby]\$(?:1[2-6])\$[./A-Za-z0-9]{53}',password):raise ValueError('Provide a bcrypt hash with work factor 12 to 16, never a plaintext password.')
        emails.add(email.lower());subjects.add(subject);clean.append(dict(user))
    target=Path(target)
    if target.exists() or target.is_symlink():raise ValueError('Choose a new private service directory; existing configuration is never replaced.')
    target.mkdir(mode=0o700)
    client_secret=secrets.token_urlsafe(48)
    config={'issuer':issuer,'storage':{'type':'sqlite3','config':{'file':str(target.resolve()/'dex.db')}},
            'web':{'https':'127.0.0.1:'+str(origins[1].port or 5556),'tlsCert':str(paths[0]),'tlsKey':str(paths[1])},
            'enablePasswordDB':True,'oauth2':{'skipApprovalScreen':False},
            'staticClients':[{'id':'openpeople','name':'OpenPeople HR','secret':client_secret,'redirectURIs':[origin+'/api/sso/callback']}],
            'staticPasswords':clean}
    environment={'OPENPEOPLE_OIDC_ISSUER':issuer,'OPENPEOPLE_OIDC_CLIENT_ID':'openpeople','OPENPEOPLE_OIDC_CLIENT_SECRET':client_secret,'REQUESTS_CA_BUNDLE':str(paths[2])}
    for name,value in (('dex.json',config),('app-env.json',environment)):
        fd=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as output:json.dump(value,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    return {'configured':True,'directory':str(target),'identity_users':len(clean),'issuer':issuer,'callback':origin+'/api/sso/callback',
            'service_started':False,'production_acceptance_passed':False}


def load_environment(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>65536:raise ValueError('Choose the ordinary private generated application environment file.')
    if os.name=='posix' and (path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077):raise ValueError('Keep service credentials in a private file and directory (0600/0700).')
    value=json.loads(path.read_text())
    allowed={'OPENPEOPLE_OIDC_ISSUER','OPENPEOPLE_OIDC_CLIENT_ID','OPENPEOPLE_OIDC_CLIENT_SECRET','REQUESTS_CA_BUNDLE'}
    if not isinstance(value,dict) or set(value)!=allowed or any(not isinstance(v,str) or not v or len(v)>16384 or '\0' in v for v in value.values()):raise ValueError('Use the complete generated identity environment; other environment variables are not accepted.')
    return value
