// Pure frontend logic checks using a DOM stub, not browser automation.
// This audit probe leaves production source untouched.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import { webcrypto } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(dir, '../public/app.js'), 'utf8')+'\n'+fs.readFileSync(path.resolve(dir,'../public/team.js'),'utf8').replace(/\nstart\(\);\s*$/, '');
const listeners = {};
const root = { innerHTML: '' };
const modal = { open: false, innerHTML: '', showModal() { this.open = true; }, close() { this.open = false; } };
const toast = { textContent: '', classList: { add() {}, remove() {} } };
let capturedCSV = '', handler, poll;
const context = vm.createContext({
  document: {
    visibilityState: 'visible', activeElement: null,
    querySelector: key => ({ '#root': root, '#modal': modal, '#toast': toast })[key],
    addEventListener: (name, fn) => { const previous=listeners[name];listeners[name]=previous?async event=>{await previous(event);await fn(event);}:fn; },
    createElement: () => ({ click() {} }),
  },
  window: { addEventListener() {} },
  location: { hash: '#overview' },
  history: { replaceState() {} },
  crypto: webcrypto,
  setInterval: fn => {poll=fn;return 0;},
  setTimeout: () => 0, clearTimeout() {},
  fetch: (...args) => handler(...args),
  Blob: class { constructor(parts) { capturedCSV = parts.join(''); } },
  URL: { createObjectURL: () => 'blob:audit', revokeObjectURL() {} },
  FormData: class { constructor(form) { this.data = form.values; } [Symbol.iterator]() { return Object.entries(this.data)[Symbol.iterator](); } },
});
vm.runInContext(source, context);
const run = code => vm.runInContext(code, context);
const fixture = {
  user: { id: 1, name: 'Synthetic HR', email: 'hr@example.org', role: 'hr', department: 'People' },
  today: '2026-10-09',
  employees: [{ id: 1, name: 'Synthetic HR', email: 'hr@example.org', role: 'hr', title: 'HR Administrator', department: 'People', location: 'Mumbai', annual_salary: 600000, start_date: '2026-10-01', status: 'Active', is_sample: 0 }],
  leave: [], attendance: [], tasks: [], goals: [], expenses: [], candidates: [], audit: [],
};
run(`state=${JSON.stringify(fixture)}`);

const managerFixture={...fixture,user:{id:3,name:'Manager',role:'manager'},leave:[{id:1,employee_id:4,employee_name:'Person',type:'Annual',start_date:'2026-11-02',end_date:'2026-11-03',days:2,reason:'Leave',status:'Pending',approval_policy:'manager_then_hr',manager_id:3,manager_reviewed_by:null}]};
run(`state=${JSON.stringify(managerFixture)}`);context.location.hash='#leave';
handler=async (url,options)=>({ok:true,status:200,json:async()=>options.method==='PATCH'?{id:1,status:'Pending',manager_reviewed_by:3}:{...managerFixture,leave:[{...managerFixture.leave[0],manager_reviewed_by:3}]}});
const approvalButton={dataset:{action:'approve',entity:'leave',id:'1'},disabled:false};
await listeners.click({target:{closest:selector=>selector==='[data-action]'?approvalButton:null}});
assert.match(toast.textContent,/awaiting HR/i);
const benefitsFixture={...fixture,employees:[...fixture.employees,{id:4,name:'Distinct Employee Enrollment'}],benefit_plans:[{id:1,title:'Health',description:'Health plan',monthly_cost_paise:25000}],benefit_enrollments:[{id:1,employee_id:4,plan_id:1,status:'Active'}]};
run(`state=${JSON.stringify(benefitsFixture)}`);context.location.hash='#benefits';run('render()');
assert.ok(root.innerHTML.includes('Distinct Employee Enrollment'));
run(`state=${JSON.stringify({...fixture,backup:{configured:true,destination_available:false,interval_minutes:60,last_error:'Missing folder',last_success:'2026-10-08T10:00:00Z',provider_upload_verified:false}})}`);context.location.hash='#backup';run('render()');
assert.match(root.innerHTML,/missing|unavailable|changed/i);
run(`state=${JSON.stringify({...fixture,employees:[{...fixture.employees[0],version:7}]})}`);run('openForm("employee",1)');
assert.match(modal.innerHTML,/name="expected_version"[^>]*value="7"/);
assert.match(modal.innerHTML,/name="email"/);
assert.match(modal.innerHTML,/name="start_date"/);
run('payroll={rows:[{annual_salary:999999}]};runDetails={viewerId:1,rows:[{gross_paise:999999}]}');
handler=async url=>url==='/api/session'?{ok:true,status:200,json:async()=>({setup_required:false,user:null,csrf:null})}:{ok:false,status:401,json:async()=>({error:'Sign in.'})};
await run('api("/api/state").catch(()=>{})');
assert.ok(run('state===null&&payroll===null&&runDetails===null'));
assert.equal(modal.innerHTML,'');
console.log(JSON.stringify({manager_stage_confirmation:'passed',benefit_roster:'passed',missing_destination_warning:'passed',employee_conflict_precondition:'passed',identity_correction_fields:'passed',expired_private_caches_cleared:'passed'},null,2));

run(`countryCatalog={countries:[{code:'JP',name:'Japan',currency:'JPY',timezone:'Asia/Tokyo'}],currencies:['INR','JPY','BHD'],currency_digits:{INR:2,JPY:0,BHD:3}};state=${JSON.stringify({...fixture,country:'JP',currency:'JPY',timezone:'Asia/Tokyo'})}`);
assert.equal(run("currencyFactor('JPY')"),1);assert.equal(run("currencyFactor('BHD')"),1000);
run('openForm("expense")');assert.match(modal.innerHTML,/step="1"/);
console.log(JSON.stringify({zero_and_three_decimal_currencies:'passed',expense_currency_step:'passed'}));
