"""Real headless Chrome payroll acceptance using an empty disposable profile.

Run through scripts/test_isolated.py. No existing browser profile, keychain,
certificate store or production database is used. External network is blocked
by the enclosing mandatory macOS sandbox.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import HRStore
from serving import create_hardened_server

CHROME = Path(os.environ.get('OPENPEOPLE_BROWSER_BINARY', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
PASSWORD = 'FictionalBrowserPassword123!'

DRIVER = r'''
let browserAuditStage='initial';
(async()=>{
 const checks={};
 const until=async(fn)=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,40));}throw new Error('Browser fixture condition timed out');};
 const check=(key,value)=>{if(!value)throw new Error(key);checks[key]=true;};
 const login=async(email)=>{browserAuditStage='login form '+email;await until(()=>document.querySelector('#auth-form'));const form=document.querySelector('#auth-form');form.elements.email.value=email;form.elements.password.value='FictionalBrowserPassword123!';form.requestSubmit();browserAuditStage='login response '+email;await until(()=>state?.user?.email===email);if(navigationAllowed('payruns')){location.hash='payruns';await until(()=>document.querySelector('[data-team-action="view-run"]'));}else{location.hash='overview';await until(()=>document.querySelector('#main-content'));}};
 const signout=async()=>{await api('/api/logout','POST',{});clearPrivateState();await start();};
 const page=async(name)=>{location.hash=name;await until(()=>view===name&&document.querySelector('#main-content h1'));};
 const save=async(kind,values,condition)=>{browserAuditStage='submit '+kind;document.querySelector('[data-action="form"][data-form="'+kind+'"]').click();await until(()=>document.querySelector('#record-form'));const form=document.querySelector('#record-form');for(const [key,value] of Object.entries(values)){form.elements[key].value=value;form.elements[key].dispatchEvent(new Event('change',{bubbles:true}));}check(kind+'_native_form_valid',form.checkValidity());form.requestSubmit();await until(()=>!document.querySelector('#modal').open&&condition());};
 const open=async()=>{browserAuditStage='open current run';document.querySelector('[data-team-action="view-run"]').click();await until(()=>runDetails?.reviewVersion===runDetails?.run?.version&&runDetails?.reviewVersion!=null);};
 await login('creator@example.org');
 for(const [name] of NAV){await page(name);check('screen_'+name,Boolean(document.querySelector('#main-content h1')));}
 await page('learning');
 await save('course',{title:'Browser acceptance course',description:'Fictional training resource',url:''},()=>state.courses.some(c=>c.title==='Browser acceptance course'));
 const workerId=state.employees.find(e=>e.email==='employee@example.org').id;
 await page('organization');
 await save('legal-entity',{code:'BROWSER-IN',name:'Browser employer <script>',country:'IN',currency:'INR',employer_reference:'Fictional registration'},()=>state.legal_entities.some(e=>e.code==='BROWSER-IN'));
 const browserEmployer=state.legal_entities.find(e=>e.code==='BROWSER-IN').id;
 await save('cost-center',{legal_entity_id:String(browserEmployer),code:'QA',name:'Browser cost center'},()=>state.cost_centers.some(c=>c.code==='QA'));
 const browserCenter=state.cost_centers.find(c=>c.code==='QA').id;
 await save('employer-assignment',{employee_id:String(workerId),legal_entity_id:String(browserEmployer),cost_center_id:String(browserCenter)},()=>state.employee_assignments.some(a=>a.employee_id===workerId&&a.legal_entity_id===browserEmployer));
 check('employer_html_escaped',document.body.textContent.includes('Browser employer <script>')&&!document.querySelector('#main-content script'));
 await page('learning');
 const courseId=state.courses.find(c=>c.title==='Browser acceptance course').id;
 await save('assignment',{employee_id:String(workerId),course_id:String(courseId),due_date:'2026-12-31'},()=>state.course_assignments.some(c=>c.course_id===courseId&&c.employee_id===workerId));
 await page('benefits');await save('benefit',{title:'Browser acceptance benefit',description:'Fictional enrollment only',currency:'INR',cost_rupees:'0'},()=>state.benefit_plans.some(p=>p.title==='Browser acceptance benefit'));
 await page('payruns');check('six_country_guides_visible',countryCatalog.payroll_capabilities.countries.length===6&&document.body.textContent.includes('Ireland'));
 browserAuditStage='statutory calculator';document.querySelector('[data-team-action=statutory-preview]').click();await until(()=>document.querySelector('#team-statutory'));document.querySelector('#team-statutory').requestSubmit();await until(()=>document.querySelector('#statutory-output').textContent.includes('41833'));check('statutory_partial_result_visible',document.querySelector('#statutory-output').textContent.includes('US-FEDERAL-PERIODIC-2026.1'));modal.close();
 const statutoryForm=document.querySelector('#team-statutory');
 browserAuditStage='new UK statutory dialog';document.querySelector('[data-team-action=statutory-preview]').click();await until(()=>modal.open&&document.querySelector('#team-statutory')!==statutoryForm);
 const ukForm=document.querySelector('#team-statutory');ukForm.elements.rule_country.value='GB';ukForm.elements.rule_country.dispatchEvent(new Event('change',{bubbles:true}));
 check('uk_rule_template_selected',JSON.parse(ukForm.elements.inputs.value).currency==='GBP');ukForm.requestSubmit();await until(()=>document.querySelector('#statutory-output').textContent.includes('GB-CLASS1-NI-2026-27.1'));
 check('uk_component_preview_correct',JSON.parse(document.querySelector('#statutory-output').textContent).deductions[0].amount_minor===26750);modal.close();
 await signout();
 await login('reviewer@example.org');await open();
 const own=runDetails.rows.find(row=>row.employee_id===state.user.id);
 check('own_deduction_control_hidden',!document.querySelector('[data-team-action="deduction"][data-id="'+own.id+'"]'));
 check('independent_reviewer_can_finalize',!document.querySelector('[data-team-action="finalize-run"]').disabled);
 const before=runDetails.run.version;
 const changed=await fetch('/fixture/change-payroll',{method:'POST'});check('concurrent_fixture_edit_saved',changed.status===200);
 await refresh();
 check('background_change_invalidates_review',runDetails.run.version>before&&runDetails.reviewVersion===null);
 check('stale_finalize_control_disabled',document.querySelector('[data-team-action="finalize-run"]').disabled);
 check('changed_payroll_explanation_visible',document.body.textContent.includes('Payroll changed: reopen'));
 await open();
 browserAuditStage='edit peer deduction';const peer=runDetails.rows.find(row=>row.employee_name==='employee');const edit=document.querySelector('[data-team-action="deduction"][data-id="'+peer.id+'"]');edit.click();await until(()=>document.querySelector('#record-form'));
 const form=document.querySelector('#record-form');check('edit_includes_loaded_version',Number(form.elements.expected_version.value)===runDetails.run.version);
 form.elements.deduction_rupees.value='3000';form.elements.deduction_note.value='Fictional browser reviewed deduction';check('deduction_form_valid',form.checkValidity());const prior=runDetails.run.version;form.requestSubmit();browserAuditStage='deduction save response';
 await until(()=>runDetails?.run?.version>prior&&!document.querySelector('#modal').open);
 check('editor_cannot_finalize_in_browser',runDetails.can_finalize===false&&document.querySelector('[data-team-action="finalize-run"]').disabled);
 browserAuditStage='import external payroll';await open();const externalRow=runDetails.rows.find(row=>row.employee_id===workerId);document.querySelector('[data-team-action="external-payroll"][data-id="'+externalRow.id+'"]').click();await until(()=>document.querySelector('#record-form'));
 const imported={...externalRow.external_template,provider:'Fictional browser provider',reference:'BROWSER-2026-10',rules_effective_date:'2026-10-01',review_note:'Independently checked fictional calculation',earnings:[{label:'<img src=x onerror=alert(1)>',amount_minor:5000000}],deductions:[{label:'Reviewed tax',amount_minor:300000}],employer_contributions:[{label:'Employer contribution',amount_minor:100000}],net_minor:4700000};
 const importForm=document.querySelector('#record-form');const importVersion=runDetails.run.version;importForm.elements.external_result_json.value=JSON.stringify(imported);importForm.requestSubmit();await until(()=>runDetails?.run?.version>importVersion&&!document.querySelector('#modal').open);
 check('external_result_import_saved',JSON.parse(runDetails.rows.find(row=>row.employee_id===workerId).external_result).reference==='BROWSER-2026-10');
 check('external_component_html_escaped',document.body.textContent.includes('<img src=x onerror=alert(1)>')&&!document.querySelector('#main-content img[src="x"]'));
 await signout();
 await login('independent@example.org');await open();
 check('fresh_independent_reviewer_can_finalize',!document.querySelector('[data-team-action="finalize-run"]').disabled);
 browserAuditStage='independent finalization';document.querySelector('[data-team-action="finalize-run"]').click();await until(()=>runDetails?.run?.status==='Finalized');
 check('reviewed_run_finalized',runDetails.run.status==='Finalized');
 check('finalized_edit_controls_removed',!document.querySelector('[data-team-action="deduction"]'));
 check('finalized_import_controls_removed',!document.querySelector('[data-team-action="external-payroll"]'));
 await signout();await login('creator@example.org');await page('payruns');
 const filingEmployer=state.legal_entities.find(e=>e.code==='FICT-IN').id;
 await save('filing-packet',{legal_entity_id:String(filingEmployer)},()=>state.filing_packets.length===1);
 const packetId=state.filing_packets[0].id;
 check('creator_cannot_review_packet',!document.querySelector('[data-team-action=filing-review]'));
 const exported=await api('/api/filing_packets/'+packetId+'/export');check('filing_snapshot_preserves_original_employer',exported.packet.employer.id===filingEmployer&&exported.packet.statements.length===1);
 await signout();await login('independent@example.org');await page('payruns');
 browserAuditStage='filing review';document.querySelector('[data-team-action=filing-review]').click();await until(()=>document.querySelector('#record-form'));const reviewForm=document.querySelector('#record-form');reviewForm.elements.review_note.value='Independently reconciled fictional workpaper';reviewForm.requestSubmit();await until(()=>state.filing_packets[0].status==='Reviewed'&&!modal.open);check('filing_independent_review_saved',state.filing_packets[0].reviewed_by===state.user.id);
 browserAuditStage='external filing evidence';document.querySelector('[data-team-action=filing-evidence]').click();await until(()=>document.querySelector('#record-form'));const evidenceForm=document.querySelector('#record-form');evidenceForm.elements.external_reference.value='Fictional provider receipt';evidenceForm.elements.receipt_sha256.value='a'.repeat(64);evidenceForm.requestSubmit();await until(()=>state.filing_packets[0].status==='Submitted externally'&&!modal.open);check('external_evidence_is_not_authority_verification',state.filing_packets[0].authority_verified===false);
 await signout();await login('employee@example.org');await page('payslips');
 check('employee_only_own_statement',state.payslips.length===1&&state.payslips[0].employee_id===state.user.id&&document.body.textContent.includes('BROWSER-2026-10'));
 check('employee_privileged_navigation_hidden',!document.querySelector('nav a[href="#payruns"]')&&!document.querySelector('nav a[href="#settings"]'));
 await page('benefits');document.querySelector('[data-team-action="enroll"]').click();await until(()=>state.benefit_enrollments.some(e=>e.employee_id===workerId&&e.status==='Active'));check('employee_benefit_enrollment_saved',true);
 await page('learning');document.querySelector('[data-team-action="complete-course"]').click();await until(()=>state.course_assignments.some(c=>c.course_id===courseId&&c.status==='Completed'));check('employee_course_completion_saved',true);
 await page('leave');await save('leave',{type:'Annual',start_date:'2026-11-02',end_date:'2026-11-02',reason:'Fictional browser acceptance leave'},()=>state.leave.some(l=>l.reason==='Fictional browser acceptance leave'));
 check('employee_cannot_approve_own_leave',!document.querySelector('[data-action="approve"]'));
 await signout();await login('creator@example.org');await page('audit');
 check('audit_anchor_control_available',Boolean(document.querySelector('[data-team-action=verify-audit]')));
 check('browser_audit_chains_verify',(await api('/api/audit/verify')).passed===true);
 await page('backup');check('operations_control_available',Boolean(document.querySelector('[data-team-action=operations-check]')));
 document.querySelector('[data-team-action=operations-check]').click();await until(()=>modal.open&&modal.textContent.includes('Technical production checks'));check('operations_pending_checks_visible',modal.textContent.includes('Needs attention'));modal.close();
 await page('organization');await save('pay-group',{legal_entity_id:String(browserEmployer),name:'Browser weekly group',frequency:'weekly'},()=>state.pay_groups.some(g=>g.name==='Browser weekly group'));
 const browserGroup=state.pay_groups.find(g=>g.name==='Browser weekly group').id;
 await save('pay-group-member',{pay_group_id:String(browserGroup),employee_id:String(workerId)},()=>state.pay_group_members.some(m=>m.employee_id===workerId&&m.pay_group_id===browserGroup));
 check('browser_group_versions_advance',state.pay_groups.find(g=>g.id===browserGroup).version===2);
 await page('payruns');await save('pay-period',{pay_group_id:String(browserGroup),period_start:'2026-11-01',period_end:'2026-11-07',pay_date:'2026-11-09',run_kind:'regular',reference:'BROWSER-W1'},()=>state.pay_runs.some(r=>r.reference==='BROWSER-W1'));
 const datedRun=state.pay_runs.find(r=>r.reference==='BROWSER-W1');const datedDetails=await api('/api/pay_runs/'+datedRun.id);
 check('browser_period_contract_bound',datedDetails.rows[0].external_template.period.period_end==='2026-11-07');check('browser_unreviewed_period_not_finalizable',datedDetails.can_finalize===false);
 await page('organization');const scopedMember=state.payroll_access.find(m=>m.name==='independent');
 browserAuditStage='payroll scope form';document.querySelector('[data-team-action=payroll-access][data-id="'+scopedMember.employee_id+'"]').click();await until(()=>document.querySelector('#team-access'));
 const accessForm=document.querySelector('#team-access');accessForm.elements.mode.value='restricted';accessForm.querySelector('[name=entity_ids][value="'+filingEmployer+'"]').checked=true;accessForm.requestSubmit();
 await until(()=>!modal.open&&state.payroll_access.find(m=>m.employee_id===scopedMember.employee_id).mode==='restricted');
 check('payroll_scope_form_saved',true);await signout();await login('independent@example.org');await open();
 check('restricted_browser_historical_rows',runDetails.rows.length===1&&runDetails.rows[0].employee_id===workerId);
 check('restricted_browser_finalization_disabled',runDetails.can_finalize===false);
 check('restricted_browser_current_salary_hidden',!('annual_salary' in state.employees.find(e=>e.id===workerId)));
 await page('security');browserAuditStage='authenticator enrollment';document.querySelector('[data-team-action=begin-mfa]').click();await until(()=>modal.open&&document.querySelector('#team-factor-confirm'));
 const confirmation=document.querySelector('#team-factor-confirm');confirmation.elements.otp.value=(await (await fetch('/fixture/authenticator-code')).json()).otp;confirmation.requestSubmit();await until(()=>!modal.open&&state.security.mfa_enabled);
 check('browser_authenticator_enrollment_saved',state.security.mfa_enabled);
 browserAuditStage='recovery code generation';await until(()=>document.querySelector('[data-team-action=recovery-codes]'));document.querySelector('[data-team-action=recovery-codes]').click();await until(()=>modal.open&&document.querySelector('#team-recovery-codes'));
 const recoveryForm=document.querySelector('#team-recovery-codes');recoveryForm.elements.otp.value=(await (await fetch('/fixture/authenticator-code')).json()).otp;check('browser_recovery_form_valid',recoveryForm.checkValidity());recoveryForm.requestSubmit();await until(()=>document.querySelector('#recovery-code-output'));
 await until(()=>state.security.recovery_codes_remaining===10);const recoveredCodes=document.querySelector('#recovery-code-output').textContent.trim().split('\n');check('browser_recovery_codes_shown_once',recoveredCodes.length===10&&state.security.recovery_codes_remaining===10);
 document.querySelector('[data-team-action=dismiss-recovery-codes]').click();await until(()=>!modal.open);check('browser_recovery_material_cleared',!document.querySelector('#recovery-code-output'));
 await signout();browserAuditStage='recovery code sign-in';await until(()=>document.querySelector('#auth-form'));const recoveredLogin=document.querySelector('#auth-form');recoveredLogin.elements.email.value='independent@example.org';recoveredLogin.elements.password.value='FictionalBrowserPassword123!';recoveredLogin.elements.recovery_code.value=recoveredCodes[0];check('browser_recovery_login_form_valid',recoveredLogin.checkValidity());recoveredLogin.requestSubmit();await until(()=>state?.user?.email==='independent@example.org');check('browser_recovery_sign_in',state.security.recovery_codes_remaining===9);
 document.title='OPENPEOPLE_BROWSER_PASS';const result=document.createElement('pre');result.id='browser-result';result.textContent=JSON.stringify({passed:true,checks});document.body.append(result);
})().catch(error=>{document.title='OPENPEOPLE_BROWSER_FAIL';const result=document.createElement('pre');result.id='browser-result';result.textContent=JSON.stringify({passed:false,error:error.message,stage:browserAuditStage,toast:document.querySelector('#toast')?.textContent,form_error:document.querySelector('.form-error')?.textContent});document.body.append(result);});
'''

CORE_DRIVER = r"""
let browserAuditStage='core initial';
(async()=>{
 const checks={};
 const until=async(fn)=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,40));}throw new Error('Core HR browser condition timed out');};
 const check=(key,value)=>{if(!value)throw new Error(key);checks[key]=true;};
 const login=async(email)=>{await until(()=>document.querySelector('#auth-form'));const form=document.querySelector('#auth-form');form.elements.email.value=email;form.elements.password.value='FictionalBrowserPassword123!';form.requestSubmit();await until(()=>state?.user?.email===email&&document.querySelector('#main-content'));};
 const page=async(name)=>{browserAuditStage='core '+name;location.hash=name;await until(()=>view===name&&document.querySelector('#main-content h1'));};
 await until(()=>document.querySelector('#auth-form'));
 check('core_login_story',!document.querySelector('.auth-story').textContent.includes('Benefits & pay'));
 await login('creator@example.org');
 check('core_contract',state.product.profile==='core-hr');
 for(const name of state.product.pages){await page(name);check('core_screen_'+name,true);}
 check('disabled_state_hidden',state.pay_runs.length===0&&state.legal_entities.length===0);
 await page('people');
 document.querySelector('[data-form=employee]').click();await until(()=>document.querySelector('#record-form'));
 const form=document.querySelector('#record-form');
 check('core_role_options',!form.elements.role.querySelector('[value=payroll]'));
 for(const [key,value] of Object.entries({name:'Core browser joiner',email:'joiner@example.org',title:'Analyst',department:'Core team',location:'Remote',annual_salary:'600000',start_date:'2026-10-01'}))form.elements[key].value=value;
 form.requestSubmit();await until(()=>!modal.open&&state.employees.some(e=>e.email==='joiner@example.org'));
 check('core_employee_created',true);
 await page('settings');const policy=document.querySelector('#team-policies');check('core_policy_fields',!policy.elements.expenses_policy);
 policy.elements.leave_policy.value='hr_only';policy.requestSubmit();await until(()=>state.policies.leave_policy==='hr_only');
 check('core_policy_saved',true);
 await page('leave');document.querySelector('[data-form=leave]').click();await until(()=>document.querySelector('#record-form'));
 const leave=document.querySelector('#record-form');leave.elements.start_date.value='2026-11-03';leave.elements.end_date.value='2026-11-03';leave.elements.reason.value='Fictional core acceptance';leave.requestSubmit();
 await until(()=>!modal.open&&state.leave.some(r=>r.reason==='Fictional core acceptance'));
 const request=state.leave.find(r=>r.reason==='Fictional core acceptance');check('core_leave_created',true);
 check('core_own_approval_hidden',!document.querySelector('[data-action=approve][data-id="'+request.id+'"]'));
 try{await api('/api/leave/'+request.id,'PATCH',{status:'Approved'});check('core_own_approval_denied',false);}catch(error){check('core_own_approval_denied',error.status===403);}
 await page('onboarding');check('core_onboarding_created',state.tasks.some(t=>t.employee_id===state.employees.find(e=>e.email==='joiner@example.org').id));
 location.hash='payruns';await until(()=>view==='overview');check('core_deep_link_rejected',!document.querySelector('a[href="#payruns"]'));
 await api('/api/logout','POST',{});clearPrivateState();await start();await login('employee@example.org');
 check('core_employee_salary_hidden',state.employees.every(e=>!('annual_salary' in e)));
 check('core_employee_admin_navigation_hidden',!document.querySelector('a[href="#settings"]')&&!document.querySelector('a[href="#audit"]'));
 document.title='OPENPEOPLE_BROWSER_PASS';const result=document.createElement('pre');result.id='browser-result';result.textContent=JSON.stringify({passed:true,checks});document.body.append(result);
})().catch(error=>{document.title='OPENPEOPLE_BROWSER_FAIL';const result=document.createElement('pre');result.id='browser-result';result.textContent=JSON.stringify({passed:false,error:error.message,stage:browserAuditStage,toast:document.querySelector('#toast')?.textContent,form_error:document.querySelector('.form-error')?.textContent});document.body.append(result);});
"""


def main():
    if not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-') or os.environ.get('PYTHONDONTWRITEBYTECODE') != '1':
        raise SystemExit('Use the enforced isolation runner for the browser probe.')
    if not CHROME.is_file():
        raise SystemExit('The existing Chrome binary is required; this probe installs nothing.')
    with tempfile.TemporaryDirectory(prefix='openpeople-private-browser-') as folder:
        temporary = Path(folder)
        store = HRStore(temporary / 'private/workspace.db', port=0)
        server = create_hardened_server(store, port=0)
        backend = int(server.effective_port)
        store.server_port = backend
        store.allowed_hosts = {f'127.0.0.1:{backend}'}
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        cookie = ''
        csrf = ''
        def call(path, data, method='POST'):
            nonlocal cookie, csrf
            connection = http.client.HTTPConnection('127.0.0.1', backend, timeout=5)
            try:
                connection.request(method, path, json.dumps(data), {'Content-Type': 'application/json', 'Connection': 'close', 'Cookie': cookie, 'X-CSRF-Token': csrf, 'X-Setup-Token': store.bootstrap_token})
                response = connection.getresponse()
                body = json.loads(response.read())
                if response.getheader('Set-Cookie'):
                    cookie = response.getheader('Set-Cookie').split(';')[0]
                if body.get('csrf'):
                    csrf = body['csrf']
                assert response.status in (200, 201), body
                return body
            finally:
                connection.close()
        proxy = None
        try:
            call('/api/setup', {'name': 'Fictional Creator', 'email': 'creator@example.org', 'password': PASSWORD, 'include_samples': False})
            ids = {}
            for email, role in (('reviewer@example.org', 'payroll'), ('independent@example.org', 'payroll'), ('employee@example.org', 'employee')):
                ids[email] = call('/api/employees', {'name': email.split('@')[0], 'email': email, 'title': 'Fictional reviewer', 'department': 'Finance', 'location': 'Remote', 'annual_salary': 600000, 'start_date': '2026-10-01', 'role': role, 'password': PASSWORD})['id']
            employer=call('/api/legal_entities',{'code':'FICT-IN','name':'Fictional snapshot employer','country':'IN','currency':'INR','employer_reference':'Fictional registration'})['id']
            center=call('/api/cost_centers',{'legal_entity_id':employer,'code':'FIN','name':'Finance'})['id']
            call('/api/employee_assignments',{'employee_id':ids['employee@example.org'],'legal_entity_id':employer,'cost_center_id':center,'expected_version':1})
            run = call('/api/pay_runs', {'month': '2026-10'})['id']
            connection = store.connect()
            try:
                target = connection.execute('SELECT id FROM pay_results WHERE run_id=? AND employee_id=?', (run, ids['employee@example.org'])).fetchone()[0]
            finally:
                connection.close()
            call('/api/pay_results/' + str(target), {'deductions_paise': 100000, 'deduction_note': 'Fictional initial amount', 'expected_version': 1}, 'PATCH')

            if '--core' in sys.argv:store.product_profile='core-hr'

            class Fixture(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    self.dispatch()

                def do_POST(self):
                    self.dispatch()

                def do_PATCH(self):
                    self.dispatch()

                def dispatch(self):
                    if self.path.startswith('/api/'):
                        upstream = http.client.HTTPConnection('127.0.0.1', backend, timeout=5)
                        try:
                            length = int(self.headers.get('Content-Length', '0'))
                            headers = {key: value for key, value in self.headers.items() if key.lower() not in ('connection', 'accept-encoding')}
                            headers['Connection'] = 'close'
                            upstream.request(self.command, self.path, self.rfile.read(length), headers)
                            response = upstream.getresponse()
                            body = response.read()
                            self.send_response(response.status)
                            for key, value in response.getheaders():
                                if key.lower() not in ('connection', 'server', 'date', 'content-length'):
                                    self.send_header(key, value)
                        finally:
                            upstream.close()
                    else:
                        if self.path == '/fixture/authenticator-code' and self.command == 'GET':
                            from identity import totp
                            db=store.connect()
                            try:
                                row=db.execute("SELECT totp_pending,totp_secret,totp_counter FROM employees WHERE email='independent@example.org'").fetchone()
                                secret=store.vault.decrypt((row['totp_pending'] or row['totp_secret']).encode()).decode()
                                counter=max(int(time.time()//30),row['totp_counter']+1)
                                body=json.dumps({'otp':totp(secret,counter*30)}).encode()
                            finally:db.close()
                            self.send_response(200);self.send_header('Content-Type','application/json')
                        elif self.path == '/fixture/change-payroll' and self.command == 'POST':
                            db = store.connect()
                            try:
                                version = db.execute('SELECT version FROM pay_runs WHERE id=?', (run,)).fetchone()[0]
                            finally:
                                db.close()
                            call('/api/pay_results/' + str(target), {'deductions_paise': 200000, 'deduction_note': 'Fictional concurrent edit', 'expected_version': version}, 'PATCH')
                            body = b'{}'
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/json')
                        elif self.path == '/driver.js':
                            body = (CORE_DRIVER if '--core' in sys.argv else DRIVER).encode()
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/javascript')
                        elif self.path in ('/app.js', '/team.js', '/styles.css', '/favicon.svg'):
                            body = (ROOT / 'public' / self.path[1:]).read_bytes()
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/css' if self.path.endswith('.css') else 'image/svg+xml' if self.path.endswith('.svg') else 'text/javascript')
                        elif self.path == '/':
                            body = (ROOT / 'public/index.html').read_bytes().replace(b'</body>',b'<script src="/driver.js"></script></body>')
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/html')
                        else:
                            body = b''
                            self.send_response(404)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            proxy = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
            store.allowed_hosts.add(f'127.0.0.1:{proxy.server_port}')
            proxy_worker = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_worker.start()
            environment = os.environ.copy()
            profile=temporary / 'empty-chrome-profile'
            command = [str(CHROME), '--headless=new', '--no-sandbox', '--use-mock-keychain', '--password-store=basic', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--disable-breakpad', '--disable-crash-reporter', '--disable-crashpad', '--crash-dumps-dir=' + str(temporary / 'crashes'), '--disable-sync', '--disable-extensions', '--disable-gpu', '--disable-dev-shm-usage', '--user-data-dir=' + str(profile), '--disk-cache-dir=' + str(temporary / 'browser-cache'), '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', 'about:blank']
            with (temporary / 'browser.log').open('w') as log:
                browser=subprocess.Popen(command,stdout=log,stderr=log,env=environment)
                try:
                    active=profile / 'DevToolsActivePort'
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline and browser.poll() is None and not active.exists():time.sleep(0.05)
                    if not active.exists():raise RuntimeError('Disposable browser did not start: '+(temporary / 'browser.log').read_text()[-1200:])
                    lines=active.read_text().splitlines()
                    endpoint='ws://127.0.0.1:'+lines[0]+lines[1]
                    completed=subprocess.run([shutil.which('node'),str(ROOT / 'tests/browser_cdp.mjs'),endpoint,f'http://127.0.0.1:{proxy.server_port}/'],capture_output=True,text=True,env=environment,timeout=50)
                    if completed.returncode:raise RuntimeError('Browser protocol harness failed: '+completed.stderr[-1800:])
                    result=json.loads(completed.stdout)
                finally:
                    if browser.poll() is None:browser.terminate()
                    try:browser.wait(timeout=4)
                    except subprocess.TimeoutExpired:browser.kill();browser.wait()
            assert result['passed'], result
            result.update({'browser': 'Isolated Chromium engine, empty disposable profile', 'standalone_test_binary': CHROME.name == 'chrome-headless-shell', 'existing_browser_profile_used': False, 'personal_keychain_used': False, 'fictional_data_only': True})
            print(json.dumps(result, indent=2))
        finally:
            if proxy:
                proxy.shutdown()
                proxy.server_close()
                proxy_worker.join(timeout=3)
            server.task_dispatcher.shutdown()
            server.close()
            worker.join(timeout=3)


if __name__ == '__main__':
    main()
