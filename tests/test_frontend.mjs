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
const routes = ['overview', 'people', 'leave', 'attendance', 'recruitment', 'onboarding', 'payroll', 'performance', 'expenses', 'reports','organization','benefits','learning','payruns','payslips','notifications','security','settings','backup','audit'];
const rendered = [];
for (const route of routes) {
  context.location.hash = '#' + route;
  run('render()');
  assert.match(root.innerHTML, /<h1>/);
  rendered.push(route);
}
const escaped = run('esc("<img src=x onerror=alert(1)>")');
assert.equal(escaped, '&lt;img src=x onerror=alert(1)&gt;');
run('state.employees[0].name="=2+3"; exportCSV("employees")');
assert.ok(capturedCSV.includes('"\'=2+3"'));
run(`state=${JSON.stringify(fixture)}; state.employees[0].department="__proto__"`);
const prototypeCount = run('departments().length');
run('state.employees[0].department="constructor"');
const constructorCountType = run('typeof departments()[0][1]');
assert.equal(prototypeCount, 1);
assert.equal(constructorCountType, 'number');

run(`state=${JSON.stringify(fixture)}`);
let successfulPosts = 0;
handler = async (url, options) => {
  if (options.method === 'POST') {
    successfulPosts++;
    return { ok: true, status: 201, json: async () => ({ id: successfulPosts }) };
  }
  throw new Error('Synthetic state-refresh connection failure');
};
const submitButton = { disabled: false };
const errorBox = { textContent: '' };
const form = {
  id: 'record-form', dataset: { path: '/api/expenses', method: 'POST' },
  values: { description: 'Synthetic expense', amount: '12.34', category: 'Travel', expense_date: '2026-10-09' },
  querySelector: selector => selector === '.form-error' ? errorBox : selector === 'button[type="submit"]' ? submitButton : null,
  querySelectorAll: () => [],
};
modal.open = true;
await listeners.submit({ target: form, preventDefault() {} });
const first = { committed_posts: successfulPosts, dialog_still_open: modal.open, shown_error: errorBox.textContent };
await listeners.submit({ target: form, preventDefault() {} });
const retry = { committed_posts: successfulPosts, dialog_still_open: modal.open, shown_error: errorBox.textContent };
assert.equal(first.committed_posts, 1);
assert.equal(first.dialog_still_open, false);
assert.equal(first.shown_error, '');
assert.equal(retry.committed_posts, 1);
run('view="payruns"; runDetails={viewerId:1,run:{id:1,month:"2026-10",status:"Draft",created_by:1},rows:[{id:1,employee_name:"Synthetic HR",gross_paise:5000000,deductions_paise:0,deduction_note:""}]}');
handler=async url=>({ok:true,status:200,json:async()=>url==='/api/state'?fixture:{run:{id:1,month:'2026-10',status:'Draft',created_by:1},rows:[{id:1,employee_name:'Synthetic HR',gross_paise:5000000,deductions_paise:125000,deduction_note:'Reviewed deduction'}]}});
context.location.hash='#payruns';
await run('refresh()');
assert.equal(run('runDetails.rows[0].deductions_paise'),125000);
run('runDetails=null;state.revision=1');
const updated={...fixture,revision:2,notifications:[{id:1,message:'Remote teammate update',created_at:'2026-10-09T00:00:00Z',seen:0}]};
handler=async url=>({ok:true,status:200,json:async()=>url==='/api/changes'?{revision:2}:updated});
await poll();
assert.equal(run('state.notifications[0].message'),'Remote teammate update');
const result = {
  routes_rendered_with_empty_records: rendered,
  html_escape_check: 'passed',
  csv_formula_neutralization: 'passed',
  department_reserved_keys: { proto_department_count: prototypeCount, constructor_department_count_type: constructorCountType },
  successful_write_followed_by_failed_refresh: { first_submission: first, user_retry: retry },
  payroll_detail_refresh: 'passed',
  teammate_revision_polling: 'passed',
};
console.log(JSON.stringify(result, null, 2));
