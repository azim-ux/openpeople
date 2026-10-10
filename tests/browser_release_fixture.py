"""Fictional browser acceptance fixture for the release; no live workspace writes."""
import sys,json,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from server import HRStore
from serving import create_hardened_server
from backup import configure_backup,refresh_destination_health
PASSWORD='SyntheticReleasePassword123!'
with tempfile.TemporaryDirectory(prefix='openpeople-release-browser-') as temporary:
    root=Path(temporary);db=root/'private/workspace.db'
    store=HRStore(db,port=8012);server=create_hardened_server(store,port=8012)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    origin='http://127.0.0.1:8012';admin=requests.Session();admin.trust_env=False
    def post(path,data):
        response=admin.post(origin+path,json=data,headers={'X-CSRF-Token':csrf,'X-Setup-Token':store.bootstrap_token},timeout=5)
        assert response.status_code in (200,201),response.text
        return response.json()
    csrf='';csrf=post('/api/setup',{'name':'Fictional HR A','email':'hr-a@example.org','password':PASSWORD,'include_samples':False})['csrf']
    employees={}
    for email,role,country in [('hr-b@example.org','hr','IN'),('manager@example.org','manager','IN'),('employee@example.org','employee','IN'),('us@example.org','employee','US'),('jp@example.org','employee','JP')]:
        employees[email]=post('/api/employees',{'name':'Fictional '+email.split('@')[0],'email':email,'role':role,'title':'Analyst','department':'Operations','location':'Remote','start_date':'2026-10-01','annual_salary':600000,'country':country,'password':PASSWORD})['id']
    person=employees['employee@example.org'];manager=employees['manager@example.org']
    admin.patch(origin+'/api/employees/'+str(person),json={'manager_id':manager,'expected_version':1},headers={'X-CSRF-Token':csrf},timeout=5).raise_for_status()
    post('/api/policies',{'leave_policy':'manager_then_hr'})
    post('/api/leave',{'employee_id':person,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-03','reason':'Fictional browser vacation'})
    plan=post('/api/benefit_plans',{'title':'Health plan','description':'Fictional employee health plan','monthly_cost_paise':25000})['id']
    post('/api/benefit_enrollments',{'employee_id':person,'plan_id':plan})
    course=post('/api/courses',{'title':'Security training','description':'Fictional mandatory training','url':'https://example.org'})['id']
    post('/api/course_assignments',{'employee_id':person,'course_id':course,'due_date':'2026-10-01'})
    folder=root/'sync';configure_backup(db,folder,'Fictional separately retained recovery phrase!',60)
    folder.rename(root/'detached-sync');refresh_destination_health(db)
    print(json.dumps({'url':origin,'fictional_accounts':list(employees),'fixture_root':str(root)}),flush=True)
    try:
        while True:time.sleep(1)
    except KeyboardInterrupt:pass
    finally:server.task_dispatcher.shutdown();server.close();thread.join(timeout=3)
