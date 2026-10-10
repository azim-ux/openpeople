import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import { webcrypto } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const directory=path.dirname(fileURLToPath(import.meta.url));
const source=fs.readFileSync(path.resolve(directory,'../public/app.js'),'utf8')+'\n'+fs.readFileSync(path.resolve(directory,'../public/team.js'),'utf8').replace(/\nstart\(\);\s*$/,'');
const root={innerHTML:''},toast={textContent:'',classList:{add(){},remove(){}}};
const modal={open:false,innerHTML:'',showModal(){this.open=true;},close(){this.open=false;}};
const listeners={};let respond;
const context=vm.createContext({
  document:{visibilityState:'visible',activeElement:null,querySelector:selector=>({'#root':root,'#toast':toast,'#modal':modal})[selector],addEventListener:(event,fn)=>{const previous=listeners[event];listeners[event]=previous?async value=>{await previous(value);await fn(value);}:fn;},createElement:()=>({click(){}})},
  window:{addEventListener(){}},location:{hash:'#payruns'},history:{replaceState(){}},crypto:webcrypto,
  setInterval:()=>0,setTimeout:()=>0,clearTimeout(){},fetch:(...args)=>respond(...args),
  Blob:class {},URL:{createObjectURL:()=>'',revokeObjectURL(){}},FormData:class {},
});
vm.runInContext(source,context);
const run=code=>vm.runInContext(code,context);
const state={user:{id:2,name:'Fictional reviewer',role:'payroll'},today:'2026-10-09',employees:[],pay_runs:[{id:1,month:'2026-10',status:'Draft'}],leave:[],attendance:[],tasks:[],goals:[],expenses:[],candidates:[],audit:[]};
const details={viewerId:2,reviewVersion:7,run:{id:1,month:'2026-10',status:'Draft',created_by:1,version:7},can_finalize:true,rows:[{id:10,employee_id:2,employee_name:'Own statement',gross_paise:5000000,deductions_paise:100000,deduction_note:'Deduction',currency:'INR',can_edit_deductions:false},{id:11,employee_id:3,employee_name:'Peer statement',gross_paise:5000000,deductions_paise:100000,deduction_note:'Deduction',currency:'INR',can_edit_deductions:true}]};
run(`state=${JSON.stringify(state)};runDetails=${JSON.stringify(details)}`);
assert.equal(run("teamForm('deduction',10)"),null);
assert.match(run("teamForm('deduction',11).content"),/name="expected_version" value="7"/);
let rendered=run('payRunsPage()');
assert.ok(!rendered.includes('data-team-action="deduction" data-id="10"'));
assert.ok(rendered.includes('data-team-action="deduction" data-id="11"'));
run('runDetails.can_finalize=false');rendered=run('payRunsPage()');
assert.match(rendered,/data-team-action="finalize-run"[^>]*disabled/);

run(`runDetails=${JSON.stringify(details)}`);
respond=async()=>({ok:true,status:200,json:async()=>({...details,run:{...details.run,version:8}})});
await run('refreshTeamDetails()');
assert.equal(run('runDetails.reviewVersion'),null);
assert.match(run('payRunsPage()'),/Payroll changed: reopen this run/);
assert.match(run('payRunsPage()'),/data-team-action="finalize-run"[^>]*disabled/);
let writes=0;
const button={dataset:{teamAction:'finalize-run',id:'1'},disabled:false};
respond=async()=>{writes++;throw new Error('A stale review must not submit');};
await listeners.click({target:{closest:selector=>selector==='[data-team-action]'?button:null}});
assert.equal(writes,0);
assert.match(toast.textContent,/Open the current run and review/);

run(`state=${JSON.stringify(state)};runDetails=${JSON.stringify(details)}`);
const captured=[];
respond=async(url,options)=>{
  if(options.method==='PATCH'){captured.push(JSON.parse(options.body));return {ok:true,status:200,json:async()=>({id:1})};}
  return {ok:true,status:200,json:async()=>url==='/api/state'?state:{...details,can_finalize:false,run:{...details.run,status:'Finalized',version:8}}};
};
await listeners.click({target:{closest:selector=>selector==='[data-team-action]'?button:null}});
assert.deepEqual(captured,[{status:'Finalized',expected_version:7}]);
console.log(JSON.stringify({own_pay_edit_hidden:'passed',editor_finalize_disabled:'passed',deduction_version_submitted:'passed',background_change_requires_reopen:'passed',stale_review_not_submitted:'passed',reviewed_version_finalization:'passed'},null,2));
