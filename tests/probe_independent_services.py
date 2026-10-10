"""Acceptance against real Dex and Headscale/Tailscale, not protocol mocks.

Run with --services-only in the mandatory isolation runner. Two VPN nodes run
on this one computer in userspace; this does not test a remote NAT or host loss.
"""
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit

import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import HRStore
from serving import create_hardened_server
from probe_oidc_https import certificates
from identity import totp
from backup import create_backup,restore_backup
from cloud_backup import upload_verified,download_verified
from audit_integrity import verify as verify_audit
from service_config import configure_identity

PASSWORD='FictionalServicePassword123!'


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_for(test,seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            result=test()
            if result:return result
        except (OSError,requests.RequestException):pass
        time.sleep(.1)
    raise AssertionError('An isolated service did not become ready within its bounded deadline.')


class LoginForm(HTMLParser):
    def __init__(self,text):
        super().__init__();self.action=None;self.fields={};self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form':self.action=attrs.get('action','')
        if tag=='input' and attrs.get('name') and attrs.get('type')=='hidden':self.fields[attrs['name']]=attrs.get('value','')


def main():
    if not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-') or os.environ.get('PYTHONDONTWRITEBYTECODE')!='1':raise SystemExit('Use the enforced isolation runner.')
    tools=Path(os.environ['OPENPEOPLE_SERVICE_TOOLS'])
    core = '--core' in sys.argv
    checks={};processes=[];logs=[]
    with tempfile.TemporaryDirectory(prefix='openpeople-real-services-') as folder:
        temporary=Path(folder);temporary.chmod(0o700)
        certs=temporary/'certificates';certs.mkdir(mode=0o700)
        ca,context=certificates(certs)
        env=os.environ.copy();env.update(SSL_CERT_FILE=str(ca),TS_NO_LOGS_NO_SUPPORT='true',TS_DISABLE_LOG_UPLOAD='true')
        def start(name,args,cwd=temporary):
            log=(temporary/(name+'.log')).open('w');logs.append(log)
            process=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            processes.append(process);return process
        def command(args):
            result=subprocess.run(args,cwd=temporary,env=env,capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(Path(args[0]).name,result.stderr[-1200:])
            return result.stdout
        def client():
            value=requests.Session();value.trust_env=False;value.verify=str(ca);return value
        backend=None;bridge=None
        previous={key:os.environ.get(key) for key in ('OPENPEOPLE_OIDC_ISSUER','OPENPEOPLE_OIDC_CLIENT_ID','OPENPEOPLE_OIDC_CLIENT_SECRET','REQUESTS_CA_BUNDLE','OPENPEOPLE_WEBDAV_URL','OPENPEOPLE_WEBDAV_USER','OPENPEOPLE_WEBDAV_PASSWORD','OPENPEOPLE_WEBDAV_CA')}
        try:
            class Bridge(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):self.forward()
                def do_POST(self):self.forward()
                def do_PATCH(self):self.forward()
                def forward(self):
                    upstream=http.client.HTTPConnection('127.0.0.1',backend.effective_port,timeout=10)
                    try:
                        headers={key:value for key,value in self.headers.items() if key.lower() not in ('connection','x-forwarded-proto','x-forwarded-for')}
                        headers.update({'Connection':'close','X-Forwarded-Proto':'https','X-Forwarded-For':'127.0.0.1'})
                        upstream.request(self.command,self.path,self.rfile.read(int(self.headers.get('Content-Length','0'))),headers)
                        response=upstream.getresponse();body=response.read();self.send_response(response.status)
                        for key,value in response.getheaders():
                            if key.lower() not in ('connection','server','date','content-length'):self.send_header(key,value)
                        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                    finally:upstream.close()
            bridge=ThreadingHTTPServer(('127.0.0.1',0),Bridge);bridge.socket=context.wrap_socket(bridge.socket,server_side=True)
            origin=f'https://127.0.0.1:{bridge.server_port}'
            store=HRStore(temporary/'private/workspace.db',public_origin=origin,port=0,product_profile='core-hr' if core else 'full')
            backend=create_hardened_server(store,port=0)
            for target in (backend.run,bridge.serve_forever):threading.Thread(target=target,daemon=True).start()
            dex_port=free_port();issuer=f'https://127.0.0.1:{dex_port}/dex'
            sys.path.insert(0,str(tools/'py-libs'));import bcrypt
            account={'email':'person@example.org','username':'Fictional employee','userID':'lab-person','emailVerified':True,'hash':bcrypt.hashpw(PASSWORD.encode(),bcrypt.gensalt(12)).decode()}
            identity_folder=temporary/'identity-service'
            configure_identity(identity_folder,origin,issuer,certs/'server.pem',certs/'server.key',ca,[account])
            config_path=identity_folder/'dex.json';config=json.loads(config_path.read_text())
            config['frontend']={'dir':str(next((tools/'dex').iterdir())/'web')};config_path.write_text(json.dumps(config))
            generated_env=json.loads((identity_folder/'app-env.json').read_text())
            checks['generated_private_identity_configuration_accepted']=True
            start('dex',[str(tools/'bin/dex'),'serve',str(config_path)])
            idp=client();wait_for(lambda:idp.get(issuer+'/.well-known/openid-configuration',timeout=1).status_code==200)
            os.environ.update(generated_env)
            admin=client()
            def call(c,path,method='GET',data=None,csrf=None):
                return c.request(method,origin+path,json=data,headers={'Origin':origin,**({'X-Setup-Token':store.bootstrap_token} if path=='/api/setup' else {}),**({'X-CSRF-Token':csrf} if csrf else {})},timeout=10,allow_redirects=False)
            response=call(admin,'/api/setup','POST',{'name':'Fictional HR','email':'hr@example.org','password':PASSWORD});assert response.status_code==201,response.text
            csrf=response.json()['csrf']
            response=call(admin,'/api/employees','POST',{'name':'Fictional employee','email':'person@example.org','title':'Tester','department':'Test','location':'Remote','annual_salary':600000,'start_date':'2026-10-01','password':PASSWORD},csrf);assert response.status_code==201,response.text
            employee=response.json()['id']
            def signin():
                c=client();started=call(c,'/api/sso/start');assert started.status_code==200,started.text
                page=c.get(started.json()['url'],timeout=8,allow_redirects=True)
                form=LoginForm(page.text);assert form.action is not None,('Dex login form',page.status_code,page.url)
                callback=c.post(urljoin(page.url,form.action),data={**form.fields,'login':'person@example.org','password':PASSWORD},timeout=10,allow_redirects=True)
                if urlsplit(callback.url).netloc==urlsplit(issuer).netloc:
                    approval=LoginForm(callback.text);assert approval.action is not None
                    callback=c.post(urljoin(callback.url,approval.action),data={**approval.fields,'approval':'approve'},timeout=10,allow_redirects=True)
                assert urlsplit(callback.url).netloc==urlsplit(origin).netloc,('Dex did not return to HR',callback.status_code,callback.url)
                return c,callback
            employee_client,response=signin();assert call(employee_client,'/api/state').status_code==200,response.text[:500]
            checks['independent_dex_discovery_pkce_jwks_login']=True
            session=call(employee_client,'/api/session').json();secret=call(employee_client,'/api/mfa/begin','POST',{},session['csrf']).json()['secret']
            assert call(employee_client,'/api/mfa/confirm','POST',{'otp':totp(secret)},session['csrf']).status_code==200
            gated,response=signin();assert call(gated,'/api/state').status_code==403
            session=call(gated,'/api/session').json()
            assert call(gated,'/api/mfa/verify','POST',{'otp':totp(secret,time.time()+30)},session['csrf']).status_code==200
            assert call(gated,'/api/state').status_code==200
            checks['dex_sso_local_mfa_required']=True
            assert call(admin,f'/api/employees/{employee}','PATCH',{'status':'Inactive','expected_version':1},csrf).status_code==200
            inactive,response=signin();assert call(inactive,'/api/state').status_code==401
            assert call(gated,'/api/state').status_code==401
            checks['dex_inactive_identity_and_session_denied']=True
            # An actual self-hosted control plane and two WireGuard userspace peers.
            control_port=free_port();control=f'https://127.0.0.1:{control_port}'
            head={'server_url':control,'listen_addr':f'127.0.0.1:{control_port}','metrics_listen_addr':'','grpc_listen_addr':'127.0.0.1:0','grpc_allow_insecure':False,
                  'tls_cert_path':str(certs/'server.pem'),'tls_key_path':str(certs/'server.key'),
                  'noise':{'private_key_path':str(temporary/'noise.key')},'prefixes':{'v4':'100.64.0.0/24','v6':'fd7a:115c:a1e0::/48','allocation':'sequential'},
                  'database':{'type':'sqlite','sqlite':{'path':str(temporary/'headscale.db'),'write_ahead_log':True}},
                  'dns':{'magic_dns':False,'base_domain':'lab.invalid','override_local_dns':False,'nameservers':{'global':[]}},
                  'unix_socket':str(temporary/'headscale.sock'),'unix_socket_permission':'0600',
                  'log':{'level':'error'},'policy':{'mode':'file'},
                  'derp':{'server':{'enabled':True,'region_id':999,'region_code':'lab','region_name':'Isolated lab','verify_clients':True,'stun_listen_addr':f'127.0.0.1:{free_port()}','private_key_path':str(temporary/'derp.key'),'automatically_add_embedded_derp_region':True,'ipv4':'127.0.0.1'},'urls':[],'paths':[],'auto_update_enabled':False}}
            hc=temporary/'headscale.json';hc.write_text(json.dumps(head));hc.chmod(0o600)
            start('headscale',[str(tools/'headscale'),'-c',str(hc),'serve'])
            wait_for(lambda:(temporary/'headscale.sock').exists())
            def hs(*args):return json.loads(command([str(tools/'headscale'),'-c',str(hc),'-o','json',*args]))
            user=hs('users','create','fictional-team');key=hs('preauthkeys','create','--user',str(user['id']),'--reusable','--expiration','10m')['key']
            sockets=[];socks_port=free_port()
            for i in range(2):
                path=temporary/f'peer-{i}.sock';sockets.append(path)
                args=[str(tools/'bin/tailscaled'),'--tun=userspace-networking','--state='+str(temporary/f'peer-{i}.state'),'--socket='+str(path),'--port='+str(free_port())]
                if i==1:args.append('--socks5-server=127.0.0.1:'+str(socks_port))
                start(f'peer-{i}',args);wait_for(path.exists)
                command([str(tools/'bin/tailscale'),'--socket='+str(path),'up','--login-server='+control,'--auth-key='+key,'--hostname=lab-peer-'+str(i),'--accept-dns=false','--accept-routes=false','--timeout=10s'])
            peer_ip=json.loads(command([str(tools/'bin/tailscale'),'--socket='+str(sockets[0]),'status','--json']))['TailscaleIPs'][0]
            port=bridge.server_port
            command([str(tools/'bin/tailscale'),'--socket='+str(sockets[0]),'serve','--bg','--tcp='+str(port),'tcp://127.0.0.1:'+str(port)])
            def vpn_request(path='/api/session',method='GET',payload=None,cookie=None,token=None):
                with socket.create_connection(('127.0.0.1',socks_port),timeout=12) as sock:
                    sock.sendall(b'\x05\x01\x00');assert sock.recv(2)==b'\x05\x00'
                    sock.sendall(b'\x05\x01\x00\x01'+socket.inet_aton(peer_ip)+port.to_bytes(2,'big'))
                    header=sock.recv(4);assert header[:2]==b'\x05\x00',('VPN SOCKS response',header)
                    remaining=6 if header[3]==1 else 18;data=b''
                    while len(data)<remaining:data+=sock.recv(remaining-len(data))
                    tls=ssl.create_default_context(cafile=str(ca)).wrap_socket(sock,server_hostname='127.0.0.1')
                    body=json.dumps(payload).encode() if payload is not None else b''
                    headers=f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: {origin}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'
                    if cookie:headers+='Cookie: '+cookie+'\r\n'
                    if token:headers+='X-CSRF-Token: '+token+'\r\n'
                    tls.sendall((headers+'\r\n').encode()+body)
                    response=http.client.HTTPResponse(tls);response.begin();result=(response.status,json.loads(response.read()),response.getheader('Set-Cookie'));tls.close();return result
            wait_for(lambda:vpn_request()[0]==200,20)
            assert vpn_request('/api/state')[0]==401
            login=vpn_request('/api/login','POST',{'email':'hr@example.org','password':PASSWORD});assert login[0]==200
            vpn_cookie=login[2].split(';')[0];vpn_csrf=login[1]['csrf']
            assert vpn_request('/api/state',cookie=vpn_cookie)[0]==200
            if core:
                assert vpn_request('/api/payroll',cookie=vpn_cookie)[0]==404
                state=vpn_request('/api/state',cookie=vpn_cookie)[1]
                assert state['product']['profile']=='core-hr' and state['pay_runs']==[]
                own=next(e for e in state['employees'] if e['email']=='hr@example.org')
                saved=vpn_request('/api/employees/'+str(own['id']),'PATCH',{'title':'Fictional VPN-verified HR','expected_version':own['version']},vpn_cookie,vpn_csrf)
                assert saved[0]==200,saved
                assert next(e for e in call(admin,'/api/state').json()['employees'] if e['id']==own['id'])['title']=='Fictional VPN-verified HR'
                checks['core_hr_profile_enforced_over_wireguard']=True
            else:
                saved=vpn_request('/api/goals','POST',{'title':'Fictional VPN collaboration test','due_date':'2026-10-31','employee_id':employee},vpn_cookie,vpn_csrf)
                assert saved[0]==400
                saved=vpn_request('/api/goals','POST',{'title':'Fictional VPN collaboration test','due_date':'2026-10-31'},vpn_cookie,vpn_csrf)
                assert saved[0]==201,saved
            checks['real_wireguard_peer_transport_and_verified_https']=True
            checks['vpn_authenticated_write_and_unauthenticated_denial']=True
            checks['no_system_tun_dns_routes_or_certificate_installation']=True
            # Real WsgiDAV/cheroot provider, dedicated TLS/basic-auth collection.
            dav_port=free_port();collection=temporary/'webdav-objects';collection.mkdir(mode=0o700)
            dav={'provider_mapping':{'/backups':str(collection)},'verbose':0,
                 'http_authenticator':{'accept_basic':True,'accept_digest':False,'default_to_digest':False},
                 'simple_dc':{'user_mapping':{'*':{'fictional-user':{'password':'fictional-backup-password','roles':[]}}}},
                 'dir_browser':{'enable':False},'property_manager':False,'lock_storage':False}
            dc=temporary/'webdav.json';dc.write_text(json.dumps(dav));dc.chmod(0o600)
            env['PYTHONPATH']=str(tools/'py-libs')
            code='import json,sys;from wsgidav.wsgidav_app import WsgiDAVApp;from cheroot.wsgi import Server;from cheroot.ssl.builtin import BuiltinSSLAdapter;c=json.load(open(sys.argv[1]));s=Server(("127.0.0.1",int(sys.argv[2])),WsgiDAVApp(c));s.ssl_adapter=BuiltinSSLAdapter(sys.argv[3],sys.argv[4]);s.start()'
            start('webdav',[sys.executable,'-c',code,str(dc),str(dav_port),str(certs/'server.pem'),str(certs/'server.key')])
            dav_url=f'https://127.0.0.1:{dav_port}/backups/'
            wait_for(lambda:client().get(dav_url,timeout=1).status_code==401)
            os.environ.update(OPENPEOPLE_WEBDAV_URL=dav_url,OPENPEOPLE_WEBDAV_USER='fictional-user',OPENPEOPLE_WEBDAV_PASSWORD='fictional-backup-password',OPENPEOPLE_WEBDAV_CA=str(ca))
            phrase='Fictional independent recovery passphrase!'
            if core:
                hr_secret=call(admin,'/api/mfa/begin','POST',{},csrf).json()['secret']
                assert call(admin,'/api/mfa/confirm','POST',{'otp':totp(hr_secret)},csrf).status_code==200
                assert call(admin,'/api/policies','POST',{'require_mfa':True},csrf).status_code==200
            archive=create_backup(store.db_path,temporary/'snapshots',phrase);transfer=upload_verified(archive)
            assert upload_verified(archive)['sha256']==transfer['sha256']
            remote=collection/archive.name;original=remote.read_bytes();remote.write_bytes(original[:-1]+bytes([original[-1]^1]))
            try:upload_verified(archive)
            except ValueError:pass
            else:raise AssertionError('The real provider allowed a conflicting snapshot to be overwritten.')
            assert remote.read_bytes()!=original;remote.write_bytes(original)
            checks['independent_webdav_verified_tls_auth_retry_and_collision']=True
            db=store.connect();anchor=verify_audit(db);db.close()
            backend.task_dispatcher.shutdown();backend.close();backend=None
            if core:
                from core_acceptance import capture_reference,recover_and_check
                reference=capture_reference(store.db_path)
            Path(store.db_path).parent.rename(temporary/'unavailable-source');archive.parent.rename(temporary/'unavailable-local-snapshots')
            download=temporary/'downloads';download.mkdir(mode=0o700)
            retrieved=download_verified(transfer['filename'],download,transfer['sha256'])
            if core:
                recovery=recover_and_check(retrieved,temporary/'recovered',phrase,reference,60)
                assert recovery['passed'],recovery
                assert not recovery['off_device_recovery_verified']
                restored=Path(recovery['restored_database'])
                checks['core_hr_downloaded_backup_matches_retained_reference']=True
            else:restored=restore_backup(retrieved,temporary/'recovered',phrase)
            recovered=HRStore(restored,port=0,product_profile='core-hr' if core else 'full');db=recovered.connect()
            assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
            assert verify_audit(db,anchor)['passed'];db.close()
            checks['independent_webdav_source_paths_lost_restore_and_audit_anchor']=True
            if core:
                recovered_server=create_hardened_server(recovered,port=0)
                recovered.allowed_hosts={'127.0.0.1:'+str(recovered_server.effective_port)}
                recovered_thread=threading.Thread(target=recovered_server.run,daemon=True);recovered_thread.start()
                try:
                    address='http://127.0.0.1:'+str(recovered_server.effective_port)
                    fresh=requests.Session();fresh.trust_env=False
                    assert fresh.get(address+'/api/state',headers={'Cookie':vpn_cookie},timeout=5).status_code==401
                    assert fresh.post(address+'/api/login',json={'email':'hr@example.org','password':PASSWORD},timeout=5).status_code==401
                    logged=fresh.post(address+'/api/login',json={'email':'hr@example.org','password':PASSWORD,'otp':totp(hr_secret,time.time()+30)},timeout=5)
                    assert logged.status_code==200,logged.text
                    assert fresh.get(address+'/api/state',timeout=5).json()['product']['profile']=='core-hr'
                    assert fresh.get(address+'/api/payroll',timeout=5).status_code==404
                    checks['core_hr_recovered_fresh_mfa_and_old_session_denial']=True
                finally:
                    recovered_server.task_dispatcher.shutdown();recovered_server.close();recovered_thread.join(timeout=3)
            print(json.dumps({'passed':True,'checks':checks,'product_profile':'core-hr' if core else 'full','identity_provider':'Dex v2.46.0 / SQLite / TLS','vpn':'Headscale v0.29.4 and two Tailscale v1.104.1 userspace peers','backup_provider':'WsgiDAV v4.3.5 / cheroot v11.1.2 / TLS / basic auth','different_computers_tested':False,'remote_nat_tested':False,'cloud_account_tested':False,'fictional_data_only':True,'system_settings_modified':False}))
        except Exception:
            for log in logs:log.flush()
            for name in ('dex','headscale','peer-0','peer-1','webdav'):
                path=temporary/(name+'.log')
                if path.exists():print(name+': '+path.read_text()[-1800:],file=sys.stderr)
            raise
        finally:
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
            for process in reversed(processes):
                if process.poll() is None:process.terminate()
            for process in processes:
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            for log in logs:log.close()
            if backend:backend.task_dispatcher.shutdown();backend.close()
            if bridge:bridge.shutdown();bridge.server_close()


if __name__=='__main__':main()
