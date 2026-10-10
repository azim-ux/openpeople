# OpenPeople 0.3.0 — deployment repairs, security and recovery report

Date: **9 October 2026**. Scope: the eight original vulnerabilities, follow-up [deployment backlog](audit/2026-10-09-v0.2.0/PATCH_BACKLOG.md), HR correctness, one shared local server, provider-independent encrypted backups and multi-country operating profiles. Historical audit files were preserved. A subsequent [protected local re-test](TESTING_SAFETY.md) passed the 76-test/frontend/TLS/recovery gates while blocking outside writes and confirming that the live workspace was unchanged; its separate evidence also documents the corrected coverage harness.

## Decision

**The reproduced application blockers have been patched and their regression gates pass. The release is suitable for a controlled local pilot. Unconditional production approval has not been established.** Country-specific statutory payroll remains manual, and the actual offsite installation still needs its own acceptance test.

No second computer, VPN or cloud account was available. Instead, the assessment used real local TLS, independent HTTP clients, actual cross-process configuration, delayed/failing storage and a restored workspace after stopping the source server and removing its original database path. This proves the tested application mechanisms. It does not prove provider upload, internet reachability or survival of physical loss of this computer.

The actual default workspace was preserved, privately copied before migration, upgraded from schema 2 to 3 and restarted at **http://127.0.0.1:8000**. It remains unconfigured with **zero employee accounts**, integrity `ok`, private database/key/setup-token files at Unix mode `0600`, and sample data off by default. The owner must create the first administrator using the existing private setup token. No real employee data or external credentials were entered. [Startup evidence](validation/v0.3.0/local-startup.json).

## Deployment backlog disposition

| Finding | Change and verified result | Status |
| --- | --- | --- |
| S1: slow connections exhaust capacity | Waitress deadlines and pending budgets evict unfinished input. The complete Caddy configuration bounds headers/body input and uses small request buffering plus HTTP/1 full duplex. With 100 unfinished headers, then 100 unfinished bodies, fresh login/read/save all succeeded; unfinished requests expired. | Reproduced case fixed; broader capacity testing remains |
| S2: manual backup blocks writes | Authenticated request queues a job; snapshot/encryption/destination I/O runs outside the API write transaction. Delayed backup storage did not block an independent HR save. Short completion/failure updates are audited. | Fixed |
| S3: completed old backup restores old settings | Separate cross-process configuration/run locks and generation checks prevent stale completion from replacing newer settings. A real configure CLI raced a delayed backup; a subsequent archive restored using the new phrase. | Fixed |
| S4: polling defeats inactivity expiry | Read polling does not renew sessions. Explicit trusted browser interaction sends bounded activity renewal; 30-minute idle and eight-hour absolute limits remain. Expiry clears private browser caches. | Fixed |
| S5: stale employee form overwrites a raise | Required record versions return 428 when missing and 409 when stale. Forms send intentional changes, load latest values for review, and require reconciliation. Browser/API salary-location race preserved the raise. | Fixed |
| S6: policy/security history is insufficient | Sanitized before/after policies, access denials, protected exports and privileged backup outcomes are recorded. HR/auditor exports have bounded date/page filters. Audit history survived recovery. | Fixed for tested events; external tamper-resistant logging remains |
| S7: missing backup folder looks successful | Destination marker/device/inode checks reject missing or replaced folders without recreating them. Persisted failure, last success, availability and cached check time appear in the UI. Slow destination checks run in the background. | Fixed |
| Demo records enter production totals | New setup requires explicit sample opt-in. Sample workers are excluded from operational payroll and workforce totals. Existing records are preserved. | Fixed; review unflagged legacy imported/demo records |
| Actual remote/cloud deployment acceptance | Application-side TLS/shared-edit/recovery tests passed. No actual VPN route, provider account or second device was available. | Installation gate remains open |

Caddy's full-duplex option is experimental and must be checked when upgrading. The actual tested version was **2.11.7**. The failure reproduction showed why a bare proxy or deadline-only configuration was insufficient; use the complete [Caddyfile](../deploy/Caddyfile). Caddy documents timeout/full-duplex behavior in its [global options](https://caddyserver.com/docs/caddyfile/options) and bounded request buffering in its [reverse-proxy reference](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

Waitress uses eight workers, a 100-connection cap and pending budgets of 48 total/16 per backend peer. Caddy upstreams share the loopback peer budget; this is not a per-VPN-client connection quota. These probes establish availability under the reproduced bounded load, not unlimited denial-of-service protection or enterprise-scale throughput.

## Original security findings retained as regression gates

| Original issue | Current protection |
| --- | --- |
| Unfinished unauthenticated body holds write lock | Request parsing occurs before database writes; unfinished input is bounded by the serving/proxy controls. |
| First visitor claims administrator | Private one-time setup token, local Host boundary and bootstrap throttles; no default password. |
| Deactivated user's old session revives | Lifecycle changes revoke sessions; reactivation requires a fresh login. |
| Successful save followed by failed refresh duplicates data | Saved forms close on committed success; retries use idempotency. Frontend check kept the committed row count at one. |
| Account-existence timing difference | Known/unknown login paths perform the expensive password verification. Functional regression checks pass; this does not establish absence of every statistical side channel. |
| HR approves own request | Server ownership checks require independent review, including staged approvals/corrections/cancellation. |
| Bad identifiers or Unicode trigger server errors | Bounded type, identifier and input validation rejects tested malformed requests without HTTP 500. |
| Reserved department names corrupt totals | Safe grouping handles names such as `__proto__` and `constructor`; escaped exports neutralize spreadsheet formulas. |

Additional tests cover persistent account-based throttling across source changes, session inventory without secret disclosure, revocation of another own session, CSRF/Origin and forwarded-address spoofing, MFA requirements/replay, signed OIDC validation, future/current compensation interaction, stale attendance corrections, non-finite values and export-query whitelists. No known advisories were returned for the 11 pinned third-party dependencies on this date. That lookup is not proof that dependencies are vulnerability-free.

Backups use authenticated encryption; protected authenticator secrets use a local encryption key. The **live SQLite database is not fully encrypted by the application**. Host administrators can alter local data/audits, so disk encryption, private OS access and external append-only audit storage remain important deployment controls. Their configuration was not verified here.

## HR workflow improvements

- **People and compensation:** auditable identity/start/end corrections; stable SSO identity binding; required edit versions; effective-dated salary history; corrected intentional current raises even when a future raise exists.
- **Payroll:** calendar-day proration for employment start/end and effective salary changes; approved unpaid leave; immutable reviewed snapshots; correct currency minor units and separate totals. No automatic foreign exchange, tax filings or bank payments.
- **Leave:** company allocations/carryover, annual/monthly accrual, partial days, country/global holidays and worker workweeks; entitlement and overlap checks; amendment restarts review; approved cancellation needs independent review before refunding balance.
- **Attendance:** overnight checkout, split sessions, breaks and independent correction proposals. Changed source records reject stale correction approval; ambiguous daylight-saving times require an explicit offset.
- **Benefits:** enrollment windows, currency matching, named HR roster/export, withdrawal/re-enrollment and effective audit history. Provider enrollment, eligibility/dependents and payroll deductions remain separate work.
- **Learning:** overdue status, HR reminders and reasoned reassignment with a new due date. Course delivery, quizzes and certification renewals remain separate work.
- **Expenses:** company limits and receipt-reference thresholds per native currency; pending amendment/cancellation; independent cancellation of approved requests; a reference for externally reconciled payments. Receipt file storage and payment processing are not implemented.
- **Administration:** correct manager-stage “awaiting HR” messages, bounded exports, sample separation, active-session controls and policy/security details.

These are company-configurable policies, not automatically compliant national defaults. Annual salary proration is the implemented calculation convention and must be reviewed against employment agreements. All worker, leave, attendance and payroll inputs need employer validation before real payroll use.

## Countries and the Workday comparison

The offline catalog offers **251 country/region choices**, with operating currency, zero/two/three-decimal precision, IANA timezone, country holiday scope and custom working weekdays. It includes territories and exceptional regions; it does not represent 251 sovereign countries. Unicode metadata provenance and fingerprints are retained in [countries.json](../countries.json), with its required [license](../UNICODE-LICENSE.txt). Regions without a default operating currency require an explicit choice.

Browser acceptance confirmed Japan's JPY/Asia-Tokyo profile, saved a Friday-off/Saturday-working calendar, and rendered separate INR/JPY/USD payroll totals with country and paid-day columns. API tests cover currency precision, timezones, country-scoped holidays and workweeks.

Country selection does **not** activate national tax/statutory payroll. Workday's own public [payroll overview](https://www.workday.com/en-us/products/payroll/overview.html) describes native and partner payroll offerings with different geographic coverage. OpenPeople does not reproduce those integrations or claim their certifications. Detailed legal-entity structures, full statutory rules, benefits providers, recruitment/onboarding templates, advanced talent, configurable permissions/routing and the broader financial/planning suite remain in the [capability map](ROADMAP.md).

## Security, collaboration and recovery evidence

**76 backend tests passed**, preserving the original 36-test baseline. Combined backend line coverage was **89.87% (1,713/1,906 lines)**. Frontend checks passed for 20 routes and eight follow-up assertions. Python/JavaScript/launcher syntax checks passed. Browser checks used actual rendered controls and fictional accounts. [Validation index](VALIDATION.md), [test log](validation/v0.3.0/backend-tests.log), [coverage](validation/v0.3.0/backend-coverage.json), [browser observations](validation/v0.3.0/browser-observations.json), [dependency audit](validation/v0.3.0/dependency-audit.json).

The final actual Caddy TLS probe recorded:

| Scenario | Observed result |
| --- | --- |
| TLS trust, cookie and origin boundaries | Untrusted CA rejected; explicitly trusted CA accepted; Secure cookie and HSTS present; spoofed client forwarding ignored; cross-origin write rejected. |
| 100 unfinished headers | Login 200, read 200, write 201; normal activity 0.177 seconds; zero unfinished sockets after the deadline; probe 4.15 seconds. |
| 100 unfinished bodies | Login 200, read 200, write 201; normal activity 0.158 seconds; zero unfinished sockets after the deadline; probe 6.11 seconds. |
| Two-client editing | One client changed salary; stale second-client edit rejected with 409. |
| Source-host loss simulation | Source server stopped and original database path removed; restore used only the copied encrypted archive and separately retained phrase. |
| Fresh recovered workspace | Two workers, zero reusable sessions, five business audit records and nine security events restored; salary 720000 retained. Verify-plus-restore took 0.181 seconds for this tiny fixture. |
| Recovery authentication | Old cookie rejected; MFA still required; replay rejected; a fresh valid login succeeded. |

Archive copy/download SHA-256 was `4d9298c29d3890e8d31142ad6bd58ffcedd9cc59ce740d939a31e5d850a05df7`. Exact machine-readable observations are in [HTTPS/recovery evidence](validation/v0.3.0/https-recovery.json). Times are local fixture measurements, not production recovery objectives. Recovery ran on a fresh database/listener on the same computer; copying bytes simulated a provider, not a cloud service.

Additional backup tests delayed destinations while saving, raced a real configure process, detached/replaced folders, injected disk-full/permission failures, restarted interrupted jobs, checked catch-up scheduling, corrupted read-back and enforced generation-scoped retention without deleting unrelated archives. Wrong phrases/tampered ciphertext/unsafe destinations fail before restoration creates a workspace. API status uses cached health so filesystem stalls do not occupy HTTP workers. A successful local write is explicitly **not** reported as verified cloud upload.

## Remaining deployment gates and improvement priorities

1. **Actual offsite acceptance:** install the private VPN and complete Caddy configuration, establish trusted HTTPS and individual MFA accounts, then verify shared edits and role denials from another network/device. No public listener was opened here.
2. **Actual cloud protection:** configure the owner's chosen sync client, confirm upload from another device, download that copy, restore on another computer and retain the passphrase separately. A paused sync client may leave local success visible without offsite protection.
3. **Payroll/domain acceptance:** implement and independently verify each required country/state's statutory rules before using automated payroll for real obligations. Current calculations require manual review; no payments/submissions occur.
4. **Host operations:** verify disk encryption/ACLs, autostart/restart, sleep/power behavior, patching, storage quota and backup monitoring. One powered-off host makes the shared app unavailable. Current snapshots support databases up to 256 MB; older configuration generations require manual retention/quota management.
5. **Further security/product work:** external append-only audit/alerts, recovery codes/passkeys, provider lifecycle, custom organization/field scopes, advanced workflows and independent platform/capacity/security review. No Windows/Linux installation or external OIDC tenant was tested.

The cloud client may upload only encrypted `.opbackup` archives. Do not synchronize the live SQLite database or run two authoritative copies expecting automatic merge. The selected collaboration model supports remote browsers connecting to one local server; independent offline multi-host edits are not implemented. No hosted application-server fee is required, but existing hardware, power, connectivity, provider quota and any relay have their own constraints.

The final source package includes a per-file SHA-256 manifest and excludes the live database, keys, tokens, backup configurations and virtual environment. Extraction, all included source hashes and a fresh fictional Japan workspace startup/setup passed using this interpreter's installed dependencies. Installed dependency compatibility also passed. This is not a clean Windows/Linux installation test. [Package smoke evidence](validation/v0.3.0/release-smoke.json) and [code/test fingerprints](validation/v0.3.0/code-fingerprints.json) tie this report to the validated implementation. Follow the [deployment/recovery guide](LOCAL_TEAM_AND_BACKUP.md) for setup and repeat the installation-specific checks before relying on real employee data and offsite recovery.
