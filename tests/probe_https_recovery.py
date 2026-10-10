"""Actual local TLS, two-client collaboration and simulated offsite recovery.

Requires the checksum-verified portable Caddy binary; never opens the real DB.
Simulation deliberately does not claim a real VPN or cloud-provider test.
"""
import hashlib,json,socket,ssl,subprocess,tempfile,threading,time,shutil,sys
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from server import HRStore
from serving import create_hardened_server
from backup import configure_backup,run_configured_backup,restore_backup,verify_backup
from identity import totp
from scripts.deployment_check import check_endpoint

PASSWORD='SyntheticSecurePassword123!'
PHRASE='Separately retained synthetic recovery phrase!'
BINARY=Path('/tmp/openpeople-caddy-audit/caddy')

def call(client,origin,ca,path,method='GET',data=None,headers=None):
    response=client.request(method,origin+path,json=data,headers=headers,verify=str(ca),timeout=8)
    return response

def main():
    assert BINARY.is_file(),'Provide the verified official portable Caddy binary at the documented path.'
    results={'real_vpn_test':False,'real_provider_test':False,'simulation':True}
    with tempfile.TemporaryDirectory(prefix='openpeople-release-drill-') as temporary:
        root=Path(temporary)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));tls_port=sock.getsockname()[1]
        origin=f'https://127.0.0.1:{tls_port}'
        store=HRStore(root/'host-a/workspace.db',public_origin=origin,port=0)
        server=create_hardened_server(store,port=0);backend_port=int(server.effective_port)
        server_thread=threading.Thread(target=server.run,daemon=True);server_thread.start()
        config=Path(__file__).resolve().parents[1]/'deploy/Caddyfile'
        body=config.read_text().replace('https://10.7.0.1',origin).replace('bind 10.7.0.1','bind 127.0.0.1').replace('127.0.0.1:8000',f'127.0.0.1:{backend_port}')
        body=body.replace('    admin off','    admin off\n    skip_install_trust\n    persist_config off\n    storage file_system {\n        root '+str(root/'tls-storage')+'\n    }')
        temporary_config=root/'Caddyfile';temporary_config.write_text(body)
        validation=subprocess.run([str(BINARY),'adapt','--config',str(temporary_config),'--validate'],capture_output=True,text=True,timeout=10)
        assert validation.returncode==0,validation.stderr
        results['caddy_config_valid']=True
        store.allowed_hosts={f'127.0.0.1:{tls_port}'}
        ca=root/'tls-storage/pki/authorities/local/root.crt'
        first=requests.Session();first.trust_env=False
        second=requests.Session();second.trust_env=False
        log=(root/'tls.log').open('w');proxy=subprocess.Popen([str(BINARY),'run','--config',str(temporary_config)],stdout=log,stderr=log)
        connections=[]
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                try:
                    if ca.exists() and call(first,origin,ca,'/api/session').status_code==200:break
                except requests.RequestException:pass
                time.sleep(.1)
            else:raise TimeoutError('TLS fixture did not become ready')
            try:first.get(origin+'/api/session',timeout=2);results['untrusted_certificate_rejected']=False
            except requests.exceptions.SSLError:results['untrusted_certificate_rejected']=True
            denied=call(first,origin,ca,'/api/setup','POST',{'name':'Attacker','email':'attacker@example.org','password':PASSWORD})
            assert denied.status_code==403
            setup=call(first,origin,ca,'/api/setup','POST',{'name':'Fictional HR A','email':'hr-a@example.org','password':PASSWORD,'include_samples':False},headers={'X-Setup-Token':store.bootstrap_token,'Origin':origin})
            assert setup.status_code==201,setup.text
            csrf=setup.json()['csrf'];write_headers={'X-CSRF-Token':csrf,'Origin':origin}
            results['secure_cookie']='; Secure' in setup.headers.get('Set-Cookie','')
            results['hsts']=setup.headers.get('Strict-Transport-Security')
            results['deployment_endpoint']=check_endpoint(origin,str(ca))
            assert results['deployment_endpoint']['passed'],results['deployment_endpoint']
            employee=call(first,origin,ca,'/api/employees','POST',{'name':'Fictional HR B','email':'hr-b@example.org','title':'Reviewer','department':'People','location':'Remote','annual_salary':600000,'start_date':'2026-10-01','role':'hr','password':PASSWORD},write_headers)
            assert employee.status_code==201,employee.text
            employee_id=employee.json()['id']
            login=call(second,origin,ca,'/api/login','POST',{'email':'hr-b@example.org','password':PASSWORD},headers={'Origin':origin,'X-Forwarded-For':'203.0.113.77'})
            assert login.status_code==200;second_headers={'X-CSRF-Token':login.json()['csrf'],'Origin':origin}
            with closing(store.connect()) as db:addresses=[row[0] for row in db.execute('SELECT address FROM security_events')]
            results['spoofed_forwarded_address_rejected']='203.0.113.77' not in addresses
            stale=next(row for row in call(second,origin,ca,'/api/state').json()['employees'] if row['id']==employee_id)
            salary=call(first,origin,ca,f'/api/employees/{employee_id}','PATCH',{'annual_salary':720000,'expected_version':stale['version']},write_headers)
            assert salary.status_code==200
            conflict=call(second,origin,ca,f'/api/employees/{employee_id}','PATCH',{'location':'Another location','annual_salary':600000,'expected_version':stale['version']},second_headers)
            assert conflict.status_code==409;results['tls_stale_edit_rejected']=True
            evil=call(first,origin,ca,'/api/goals','POST',{'title':'Bad origin','due_date':'2026-12-31'},headers={'X-CSRF-Token':csrf,'Origin':'https://evil.example'})
            assert evil.status_code==403
            results['cross_origin_write_rejected']=True
            tls_context=ssl.create_default_context(cafile=str(ca));attacks=[]
            for mode,seconds in [('headers',3),('body',5)]:
                sockets=[];started=time.monotonic()
                for _ in range(100):
                    channel=tls_context.wrap_socket(socket.create_connection(('127.0.0.1',tls_port),timeout=2),server_hostname='127.0.0.1')
                    payload=f'POST /api/policies HTTP/1.1\r\nHost: 127.0.0.1:{tls_port}\r\n'+('Content-Length: 1000\r\n\r\n{' if mode=='body' else 'X-Slow: ')
                    try:channel.sendall(payload.encode())
                    except OSError:pass
                    sockets.append(channel);connections.append(channel)
                activity_started=time.monotonic()
                signing_in=requests.Session();signing_in.trust_env=False
                held_login=call(signing_in,origin,ca,'/api/login','POST',{'email':'hr-b@example.org','password':PASSWORD},headers={'Origin':origin})
                assert held_login.status_code==200,(mode,held_login.status_code,held_login.text)
                held_read=call(second,origin,ca,'/api/state');held_write=call(first,origin,ca,'/api/goals','POST',{'title':'Team edit during slow '+mode,'due_date':'2026-12-31'},write_headers)
                assert held_read.status_code==200 and held_write.status_code==201,(held_read.status_code,held_write.status_code)
                activity_elapsed=round(time.monotonic()-activity_started,3)
                until=time.monotonic()+seconds+.6
                while time.monotonic()<until:
                    for channel in sockets:
                        try:channel.sendall(b' ')
                        except OSError:pass
                    time.sleep(.1)
                open_count=0
                for channel in sockets:
                    channel.settimeout(.1)
                    try:
                        # Reading the final response/EOF proves it did not remain awaiting input.
                        output=channel.recv(1024)
                        if not output:continue
                        if not output.startswith(b'HTTP/'):open_count+=1
                    except socket.timeout:open_count+=1
                    except (ssl.SSLError,OSError):pass
                    finally:channel.close()
                after=call(second,origin,ca,'/api/state');assert after.status_code==200
                attacks.append({'kind':mode,'connections':100,'during_login':held_login.status_code,'normal_activity_seconds':activity_elapsed,'during_read':held_read.status_code,'during_write':held_write.status_code,'after_read':after.status_code,'unfinished_after_deadline':open_count,'elapsed_seconds':round(time.monotonic()-started,2)})
                if open_count:
                    print(json.dumps(attacks[-1]),file=sys.stderr)
                    print(validation.stdout[:1000],file=sys.stderr)
                    print((root/'tls.log').read_text()[-3000:],file=sys.stderr)
                assert open_count==0,(mode,open_count)
            results['slow_request_tests']=attacks
            payrun=call(first,origin,ca,'/api/pay_runs','POST',{'month':'2026-10'},write_headers)
            assert payrun.status_code==201
            run_id=payrun.json()['id']
            draft=call(second,origin,ca,f'/api/pay_runs/{run_id}').json()
            other_pay=next(row for row in draft['rows'] if row['employee_id']!=employee_id)
            external={**other_pay['external_template'],'provider':'Fictional recovery provider','reference':'RECOVERY-2026-10','rules_effective_date':'2026-10-01','review_note':'Fictional externally reviewed result','earnings':[{'label':'Reviewed gross','amount_minor':100000}],'deductions':[{'label':'Reviewed tax','amount_minor':20000}],'employer_contributions':[{'label':'Reviewed employer contribution','amount_minor':5000}],'net_minor':80000}
            changed_pay=call(second,origin,ca,f'/api/pay_results/{other_pay["id"]}','PATCH',{'external_result':external,'expected_version':draft['run']['version']},second_headers)
            assert changed_pay.status_code==200,changed_pay.text
            draft=call(first,origin,ca,f'/api/pay_runs/{run_id}').json()
            saved_run_version=draft['run']['version']
            assert call(second,origin,ca,f'/api/pay_runs/{run_id}','PATCH',{'status':'Finalized','expected_version':saved_run_version},second_headers).status_code==403
            results['tls_payroll_editor_finalize_rejected']=True
            enrollment=call(first,origin,ca,'/api/mfa/begin','POST',{},write_headers);assert enrollment.status_code==200
            secret=enrollment.json()['secret'];code=totp(secret)
            enabled=call(first,origin,ca,'/api/mfa/confirm','POST',{'otp':code},write_headers);assert enabled.status_code==200
            results['tls_mfa_enabled']=True
            export=call(first,origin,ca,'/api/audit/export?limit=500');assert export.status_code==200
            assert secret not in json.dumps(export.json()) and PASSWORD not in json.dumps(export.json())
            results['sanitized_audit_export']=True
            folder=root/'sync-source';configure_backup(store.db_path,folder,PHRASE,60)
            archive=run_configured_backup(store.db_path);local_bytes=archive.read_bytes()
            assert b'hr-a@example.org' not in local_bytes and b'SQLite format' not in local_bytes
            # Separate provider/download directories model pause, upload completion and new-host retrieval.
            cloud=root/'simulated-provider';cloud.mkdir()
            downloaded=root/'host-b-download';downloaded.mkdir()
            assert not list(cloud.iterdir())
            shutil.copy2(archive,cloud/archive.name);shutil.copy2(cloud/archive.name,downloaded/archive.name)
            copied=downloaded/archive.name;assert hashlib.sha256(copied.read_bytes()).digest()==hashlib.sha256(local_bytes).digest()
            server.task_dispatcher.shutdown();server.close();server_thread.join(timeout=3)
            Path(store.db_path).parent.rename(root/'simulated-lost-host')
            assert not Path(store.db_path).exists()
            drill_started=time.monotonic();restored=restore_backup(copied,root/'host-b-restored',PHRASE)
            verifier=verify_backup(copied,PHRASE)
            results['recovery']={'download_sha256':hashlib.sha256(copied.read_bytes()).hexdigest(),'verified':verifier['verified'],'restored_counts':verifier['restored_counts'],'restoration_seconds':round(time.monotonic()-drill_started,3),'source_host_db_required':False,'source_host_stopped_and_original_path_missing':True,'provider':'simulated local copy only'}
            restored_store=HRStore(restored,port=0);restored_server=create_hardened_server(restored_store,port=0)
            restored_port=int(restored_server.effective_port);restored_store.allowed_hosts={f'127.0.0.1:{restored_port}'}
            restored_thread=threading.Thread(target=restored_server.run,daemon=True);restored_thread.start()
            try:
                recovered=requests.Session();recovered.trust_env=False;address=f'http://127.0.0.1:{restored_port}'
                old_cookie=first.cookies.get('openpeople_session')
                old=recovered.get(address+'/api/state',cookies={'openpeople_session':old_cookie},timeout=5);assert old.status_code==401
                no_factor=recovered.post(address+'/api/login',json={'email':'hr-a@example.org','password':PASSWORD},timeout=5);assert no_factor.status_code==401
                replay=recovered.post(address+'/api/login',json={'email':'hr-a@example.org','password':PASSWORD,'otp':code},timeout=5);assert replay.status_code==401
                fresh=recovered.post(address+'/api/login',json={'email':'hr-a@example.org','password':PASSWORD,'otp':totp(secret,(int(time.time()//30)+1)*30)},timeout=5);assert fresh.status_code==200,fresh.text
                recovered_state=recovered.get(address+'/api/state',timeout=5);assert recovered_state.status_code==200
                saved=next(e for e in recovered_state.json()['employees'] if e['id']==employee_id)
                assert saved['annual_salary']==720000
                results['recovery'].update(old_session_rejected=True,mfa_required_after_restore=True,mfa_replay_rejected=True,fresh_login=True,salary_preserved=720000,audit_survived=bool(recovered_state.json()['audit']))
                restored_run=recovered.get(address+f'/api/pay_runs/{run_id}',timeout=5)
                assert restored_run.status_code==200
                restored_run=restored_run.json()
                assert restored_run['run']['version']==saved_run_version and restored_run['run']['status']=='Draft'
                saved_result=next(row for row in restored_run['rows'] if row['id']==other_pay['id'])
                assert saved_result['gross_paise']==100000 and saved_result['deductions_paise']==20000
                provenance=json.loads(saved_result['external_result'])
                assert provenance['reference']=='RECOVERY-2026-10' and provenance['employer_contributions'][0]['amount_minor']==5000
                results['recovery']['external_payroll_provenance_preserved']=True
                restored_editor=requests.Session();restored_editor.trust_env=False
                editor_login=restored_editor.post(address+'/api/login',json={'email':'hr-b@example.org','password':PASSWORD},timeout=5)
                assert editor_login.status_code==200
                editor_finalize=restored_editor.patch(address+f'/api/pay_runs/{run_id}',json={'status':'Finalized','expected_version':saved_run_version},headers={'X-CSRF-Token':editor_login.json()['csrf']},timeout=5)
                assert editor_finalize.status_code==403
                results['recovery'].update(payroll_snapshot_preserved=True,payroll_revision_preserved=saved_run_version,payroll_editor_boundary_survived=True)
            finally:restored_server.task_dispatcher.shutdown();restored_server.close();restored_thread.join(timeout=3)
        finally:
            for channel in connections:channel.close()
            proxy.terminate();proxy.wait(timeout=5);log.close()
            server.task_dispatcher.shutdown();server.close();server_thread.join(timeout=3)
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
