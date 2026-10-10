# OpenPeople 0.3.1 security and deployment review

Date: **9 October 2026**. Assessment performed against this project's archived 0.3.0 release and the patched 0.3.1 source, using fictional accounts on disposable loopback servers. The [0.3.0 report](DEPLOYMENT_REVIEW_0.3.0.md) remains historical evidence.

## Decision

**The new security fixes are implemented. This is not yet an enterprise production release or approval to enter real employee data.** The local regression/security/recovery evidence below supports further fictional-data acceptance testing. Installation-specific remote access, actual off-device backup restoration, external identity-provider acceptance and applicable HR/payroll rules remain gates. Installed Chrome's full acceptance workflow was blocked by the required personal-file sandbox; it is recorded as unverified, not passed.

The running pre-existing local workspace was not migrated, restarted or used for testing. Source and a new source-only 0.3.1 package are provided. An existing server process must be deliberately restarted with the new release after preserving its private database/key and verifying recovery. Editing source files does not update a running Python process.

## New confirmed findings and fixes

All three findings below were reproduced against the archived original source. None required access to personal files. The SSO finding uses bounded provider-delay fault injection, not a live identity-provider attack. Severity is **Medium** for the tested preconditions; no critical unauthenticated account takeover or remote code execution was established by this assessment.

| ID | Preconditions and effect in 0.3.0 | Verification before fix | Fix and verification in 0.3.1 |
| --- | --- | --- | --- |
| A1: payroll editor could approve its own changes | A valid HR/payroll account, a draft created by another account, and access to that account's own statement. The reviewer could remove its own deductions and finalize that modification without a separate reviewer. | Own deduction update **200**; finalization by the same actor **200**; fictional INR deduction changed from **100,000 minor units (₹1,000)** to **0**. The creator's direct finalization still returned **403**, demonstrating the narrower bypass. No bank payment occurred. | Editing one's own deductions returns **403**. Every draft editor is retained in `pay_run_editors`; the creator and every editor are barred from final approval. A later edit by someone else does not erase previous participation. Existing draft editors are migrated from business-audit history. An independent untouched reviewer can finalize; finalized statements remain immutable. |
| A2: stale payroll review could approve changed amounts | A legitimate reviewer opens a draft; another authorized actor changes deductions before finalization. The API did not require the reviewed version. | The reviewer saw deduction **0**; another actor changed it to **200,000 minor units**; finalization using the old view still returned **200**. | A pay-run revision increments for each deduction edit and finalization. Both editing and approval require `expected_version`: missing preconditions return **428**, stale ones **409**. Checks run inside the same SQLite write transaction. A fresh reread/review succeeds. Background UI refresh invalidates the opened review version and disables finalization until the user explicitly reopens the run. |
| A3: slow SSO provider occupied every HTTP worker | SSO is configured and its trusted provider is slow. Unauthenticated complete sign-in-start requests invoke blocking provider discovery on the shared HTTP pool. No attacker control of the provider configuration is required, but provider slowness is a necessary condition. | **Eight** bounded complete requests occupied all **eight** default workers. An unrelated session request exceeded its **0.75-second** probe timeout; baseline was **0.0077 seconds**. It recovered after the fictional delay was released. | Shared, nonblocking admission limits SSO starts and callbacks to **two** workers. Excess requests receive **503** before acquiring a database connection. The same delayed eight-request scenario occupied only two workers; the unrelated read succeeded in **0.0159 seconds** and a normal authenticated save returned **201**. Slots release on success and errors. Smaller configured pools reserve at least one worker for other traffic; a one-worker hardened server is rejected. |

A1 and A2 affect the integrity of this application's manual payroll snapshots. They are not evidence of an actual bank transfer, tax filing or stolen funds. A3's fix preserves application capacity; sign-in through an unavailable identity provider can still fail. Provider caching/circuit breaking and broader capacity testing remain useful enterprise improvements.

### Code and evidence

- Payroll boundaries, version checks and migration: [workspace.py](../workspace.py); [regressions](../tests/test_security_adversarial.py).
- SSO admission/release: [server.py](../server.py), [worker configuration](../serving.py). The original provider timeout/issuer validation remains in [identity.py](../identity.py).
- Payroll UI and reviewed-version handling: [team.js](../public/team.js); [frontend security checks](../tests/test_frontend_security.mjs).
- [Before-fix evidence](audit/2026-10-09-v0.3.0-adversarial/evidence-before.json), [after-fix evidence](audit/2026-10-09-v0.3.0-adversarial/evidence-after.json), and [bounded isolated verifier](audit/2026-10-09-v0.3.0-adversarial/verify.py). Each evidence file records tested product hashes and whether the actual workspace changed.

## Security and recovery validation

The final protected run is complete and recorded in [the 0.3.1 validation evidence](validation/v0.3.1-isolation/report.json). Backend, frontend logic, local HTTPS, encrypted recovery and packaging checks passed. Full browser acceptance is explicitly blocked/unverified. These are separate outcomes, not an all-green production gate.

- **Backend:** **81 passed**, including the previous 76 regressions and five new payroll/migration/SSO isolation tests, with **90.11% combined line coverage (1,750/1,942 lines)**.
- **Focused adversarial controls:** unauthenticated employee-state read **401**; ordinary employee payroll read **403**; employee role escalation **403**; missing CSRF **403**; private database static request **404**; HR self-leave approval **403**. These controls also passed after the fixes.
- **Frontend:** existing route/rendering and workflow checks plus six new checks for own-pay controls, editor approval restrictions, deduction preconditions, changed-review invalidation, stale submission prevention and the reviewed version sent with approval. These are Node/DOM-stub tests, not a substitute for full browser acceptance.
- **Actual browser attempt:** existing headless Chrome was launched with an empty disposable profile and mock keychain under the same mandatory sandbox. Chrome attempted crash-report/process-singleton operations outside the allowed temporary tree. The OS denied them before the workflow could run. No unrestricted browser or personal-profile fallback was used. This gate remains **unverified**.
- **Local HTTPS:** real Caddy proxy and temporary CA, explicit trust only within test clients, Secure session cookies, HTTPS/origin checks and rejection of a spoofed forwarded client address. No system certificate was installed.
- **Slow-input regression:** **100 slow-header** connections and **100 slow-body** connections; fresh login **200**, normal state read **200** and save **201** during both cases; **0** unfinished requests after the deadlines. Normal activity took **0.167/0.169 seconds** respectively in the final run.
- **Recovery simulation:** encrypted archive copied to separate simulated-provider/download folders; source server stopped and original fictional database path made unavailable; archive verified and restored to a fresh private workspace in **0.179 seconds** for this small fixture. Corrected salary, audit, MFA, payroll snapshot and pay-run revision **2** survived. Old sessions and used MFA codes were rejected; fresh MFA login succeeded; the draft editor still could not finalize after restoration (**403**). The fixture is two fictional employees, not an enterprise-scale restore benchmark.
- **Privacy controls:** mandatory sandbox negative checks for outside writes, protected reads and external connections; unchanged protected sentinel; live database/key/setup-file fingerprint comparison; temporary-folder cleanup. Discarded standard I/O to `/dev/null` is the only write allowance outside the disposable tree.
- **Packaging:** candidate archive integrity and **129** file-manifest hashes verified; private database/key/token/backup files absent; fresh fictional Japan setup **201**, root page **200**, **251** country options. The final package adds completed documentation/evidence; [runtime fingerprints](validation/v0.3.1-isolation/runtime-fingerprints.json) identify the tested code and establish runtime equivalence.

No real VPN, external provider, cloud account, other computer, physical power failure or physical disk failure was tested. The cloud portion models encrypted byte transfer locally; it does not prove upload completion, quota, retention or provider availability. Restoring successfully on this computer does not prove recovery after losing this computer.

## Upgrade and operation changes

The release is **0.3.1**, with database schema **4**. First startup migrates schemas 2/3 and seeds editor exclusions for existing draft payroll from retained audit rows. Older application code rejects a schema-4 workspace; do not overwrite it with an older binary. Keep a separately retained, verified pre-upgrade backup and use the matching release when restoring it. Backup verification accepts schemas 2, 3 and 4; current encrypted recovery was rechecked.

Payroll API clients must supply the pay run's current `version` as `expected_version` for deduction edits and finalization. A conflict requires a reread and human review, not blind resubmission with a guessed new version. The bundled UI handles these rules.

For a small team, one person can create/edit a draft and an untouched colleague can finalize it. If both people edit, a third independent reviewer is necessary. An account cannot edit its own deductions; use a peer. Fixed roles remain broad HR/payroll roles, not customizable enterprise permission sets. No automated payments or statutory calculations are introduced by this patch.

Only one local server is authoritative. Remote teammates use individual browser sessions over the configured private VPN/HTTPS origin. Independent offline databases, automatic multi-master merging, high availability and failover are not implemented. Keep the host awake and monitor the backup client. Zero hosted-server fees do not guarantee unlimited free cloud storage or reliable connectivity.

## Remaining gates for real data

| Gate | Small organization acceptance | Additional enterprise acceptance |
| --- | --- | --- |
| Identity and permissions | Individual users; MFA; least-privilege roles; joiner/leaver and recovery drills; browser acceptance | Test real OIDC; provider deprovisioning/SCIM as needed; custom organization/field scopes; delegates; device and risk controls |
| Remote access | A different authorized computer reaches the private VPN HTTPS origin; trusted certificate; backend inaccessible directly | Network segmentation, approved access inventory, external penetration test and capacity/concurrent-user testing |
| Backup and loss recovery | Real sync upload confirmed; encrypted archive downloaded on another machine; fresh restore tested; passphrase held separately | Stated RPO/RTO; monitored jobs; retention/legal holds; offline/immutable copies where required; disaster exercises |
| Host and operations | Verify disk encryption/permissions; patch OS; service restart; storage quota; safe upgrades; operator named | Key lifecycle; central monitoring/alerts; external append-only security logs; retention policy; maintenance/incident procedures; redundancy if required |
| HR and payroll | Validate actual employer policies; choose required jurisdictions; use reviewed external payroll until a statutory engine is implemented | Legal entities, compliance/privacy assessment, tested statutory country/state engines, filings, bank/accounting reconciliation and integrations |
| Product workflows | Accept actual leave/attendance/benefits/learning workflows and exports with fictional records | Configurable workflows/escalation, imports/documents/e-signature, deeper benefits/recruiting/performance/learning and finance modules |

The [capability map](ROADMAP.md) records the remaining functionality. Selecting one of 251 country/region profiles configures currency/timezone/workweek preferences; it does not implement that jurisdiction's tax or labor rules. No claim of full Workday parity, regulatory compliance, independent security certification or absence of all vulnerabilities is made.

## Reproduce safely on this computer

```sh
# Current packaged release, mandatory isolation; no personal-file fallback.
.venv/bin/python scripts/test_isolated.py

# Archived pre-fix baseline, then patched-source focused checks.
.venv/bin/python docs/audit/2026-10-09-v0.3.0-adversarial/verify.py
.venv/bin/python docs/audit/2026-10-09-v0.3.0-adversarial/verify.py --expect-fixed
```

These commands need the existing project Python/Node and the previously verified portable Caddy binary. Nothing is installed. See [testing safety](TESTING_SAFETY.md). Do not run ordinary test commands against production data or copy the live SQLite database into a cloud-synced folder. Only encrypted `.opbackup` archives belong in the chosen synced folder.
