# Deployment review — OpenPeople 0.6.0

Review date: 9 October 2026. **The software is not approved for unrestricted enterprise production or complete automatic statutory payroll.** This release implements and verifies concrete payroll scheduling, launch, monitoring and large-audit recovery improvements. It does not close every previously documented limitation. Fictional-data local use is supported; real-data core HR needs installation and employer-policy acceptance, with payroll calculation/filing/payments kept in a separately accepted system.

## Delivered changes

| Capability | Result and enforcement |
| --- | --- |
| Employer pay groups | Weekly, fortnightly, semimonthly and monthly groups with matching employer/country/currency membership; worker/group version checks reject stale changes and preserve history |
| Dated payroll | Immutable eligible-worker, employer/cost-center, group/version, period/pay-date/kind snapshots; regular/bonus/adjustment runs; regular overlap rejected within groups, per worker across membership transfers and against legacy monthly runs in either creation order |
| Reviewed external results | Version-2 results bind exact period fields/types and worker/country/currency; every dated worker requires a reviewed result before finalization; peer editing, retained maker exclusions and independent finalization remain enforced |
| Production launch | Explicit `--production` refuses the listener on failed schema/database/audit/HTTPS-configuration/HR/MFA/private-file/demo/backup checks; mandatory MFA cannot be disabled while running that profile |
| Operations | Minimal unauthenticated status/version endpoint; private HR readiness using bounded queries and cached backup destination health; read-only online/offline diagnostics |
| Crash restart | One-workspace supervisor with private logs, bounded restarts, no retry on configuration refusal, and shutdown of its own child; no system service or reboot/network/trust settings installed |
| Larger audit recovery | Full startup/offline/restore verification streams retained rows and validates earlier anchors beyond 200,000 events; interactive verification remains bounded; old monthly statements remain compatible |

[Dated payroll](PAY_PERIODS.md), [operations](OPERATIONS.md) and [enterprise controls](ENTERPRISE_CONTROLS.md) describe usage and boundaries. Regular gross values are calendar-prorated estimates, not statutory weekly calculations. Bonus/adjustment estimates start at zero. Group definitions are create-only; automatic calendars, cumulative tax ledgers, retro reconciliation and void/correction workflows remain unavailable. Opaque period identifiers remain only for backward-compatible external JSON; browser labels and notifications show the group/dates.

## Verification and recovery evidence

The tested source candidate SHA-256 is `81f2ca931c9e85e9ff81c47a6336c0e33d3ec70013c1fc09160e67c9acc1244f`. Final documentation packaging is separately smoke-tested and matched against all runtime/test manifest entries in both validation reports. See [final package evidence](validation/v0.6.0-isolation/final-package-smoke.json) for its final hash and equivalence checks. Post-package proof stays beside the source archive and is deliberately excluded from its own ZIP to avoid embedding a stale or self-referential hash.

| Check | Observed result | Evidence |
| --- | --- | --- |
| Backend regression | 123 passed; 91.90% application-backend line coverage | [Coverage](validation/v0.6.0-isolation/backend-coverage.json), [log](validation/v0.6.0-isolation/backend-tests.log) |
| Browser | 71 passed across 20 screens, including new native group/membership/period forms and private operations; stale review, independent approvals and employer boundaries checked | [Full report](validation/v0.6.0-isolation/report.json), [browser log](validation/v0.6.0-isolation/browser-security.log) |
| Frontend | Route rendering, HTML/CSV protections, reserved department names, successful-save/failed-refresh retry safety, payroll cache/review invalidation and teammate polling passed | Same full report and frontend logs |
| Synthetic HTTPS identity | 13 cases passed: PKCE/JWKS, state/nonce/audience/signature/expiry, verified/provisioned users, key rotation, MFA and deactivation/session denial | Same full report |
| Slow clients / HTTPS | Trusted/untrusted TLS, forwarding, Origin and stale edits passed; login/read/write remained available during 100 slow-header and 100 slow-body connections; unfinished requests expired | Same full report |
| Cloud transport failures | Six HTTPS WebDAV methods passed, including deadlines, credential/TLS/collision checks, retry/read-back and recovery with original paths missing; stalled transfer worker stopped while database writes remained possible | Same full report and backend log |
| Large audit recovery | 200,005 fictional events, 49,713,152-byte database; full verification about 1.94 seconds on this test; encrypted restore matched retained anchor; interactive budget preserved | [Large-history log](validation/v0.6.0-isolation/large-audit-recovery.log) |
| Independent services | Nine checks passed with Dex 2.46.0, Headscale 0.29.4/two Tailscale 1.104.1 userspace peers and TLS WsgiDAV 4.3.5; actual local WireGuard peer traffic, authenticated edits and encrypted upload/download/path-loss recovery | [Independent-service report](validation/v0.6.0-isolation/report-services.json) |
| File/network protection | OS sandbox denied outside writes, protected reads and external connections; sentinel and live DB/key/setup fingerprints unchanged; test trees removed | Both validation reports, [safety guide](TESTING_SAFETY.md) |

No personal browser profile/keychain, personal records or external account was used. No system certificate, VPN route, TUN/DNS or OS service was installed. Tests run against archived source and fictional workspaces. Temporary local services were stopped. Coverage is aggregate, not proof that every failure or legal condition is exercised; the large audit drill is not enterprise concurrency/capacity certification. Dependencies are unchanged from 0.5.0; no new current-advisory scan is claimed here.

Final review reproduced a duplicate-payroll path when a worker transferred groups and was included again in the same regular period. Worker-level overlap rejection and an indexed lookup now close that path; a regression verifies rejection plus acceptance of the next nonoverlapping period. [Pre-fix reproduction](validation/v0.6.0-isolation/group-transfer-red.log) records the failure.

An old zero-budget audit-test expectation was corrected to the stricter invalid-input contract. A later browser run exposed a test-driver race that could submit the previous closed statutory dialog while the new dialog was loading. The driver now waits for the newly opened form; the final complete run passed. The first browser attempt used the installed browser and did not start under the protected environment; the complete passing run used the verified portable Chromium with an empty profile, retaining the same restrictions.

## Remaining implementation and acceptance

| Remaining requirement | Current limit and required closure |
| --- | --- |
| Complete statutory payroll | Two partial dated packs remain: ordinary US federal periodic withholding/FICA and UK ordinary Class 1 NI. They exclude significant national/regional/worker/pay-type obligations and lack independent payroll-specialist acceptance. Other countries have guidance/external-results contracts, not complete engines. Implement and maintain applicable rules, independently reviewed fixtures, cumulative/correction/year-end ledgers and reconciliation for each supported jurisdiction. |
| Government submissions and payments | Provider-neutral workpapers/evidence and a restricted SSA annual-file exporter exist. No authenticated online agency transmission, payment execution or bank connector is implemented. Complete authorized adapters, registration/certificates, official/provider sandbox validation, receipts, corrections, reconciliation and production acceptance. Operator-recorded evidence is not government verification. |
| Actual remote deployment | Independent peers worked on this computer. No second network/device, NAT reachability, persistent VPN, real external identity tenant or cloud account exists here. Configure an actual installation and repeat [acceptance](DEPLOYMENT_ACCEPTANCE.md) from a teammate device. Same-host simulation cannot establish those results. |
| Physical-loss recovery | Encrypted local and independently served same-host restores passed. Without a second storage failure domain and separately held recovery passphrase, physical computer/disk loss remains unprotected. Obtain off-device storage, retrieve an archive without the original host, and restore on another authorized device. |
| Enterprise authorization and HR | Fixed roles, payroll employer scopes and fixed approval templates remain; general field/organization permission sets, delegation/escalation, tenant isolation, SAML/SCIM/passkeys, full lifecycle/documents, richer benefits/recruiting/talent and provider integrations require design/implementation/acceptance. |
| Host operation / scale | Live database encryption relies on verified OS disk encryption and private host access. Automatic key rotation, independent/WORM audit custody, monitored platform service/reboot acceptance, incident response, actual workforce load/platform testing, backup format beyond 256 MB, failover and high availability remain outstanding. One SQLite host is one failure domain. |

The production flag is a technical barrier, not an enterprise certification. HTTPS origin configuration does not prove certificate trust, and a successful same-disk backup does not prove an offsite copy. The user confirmed no external account/device is available; this report does not invent a live acceptance result. All-country law and Workday feature parity are not completed or certified. [Country scope](PAYROLL_COUNTRIES.md) and [the capability map](ROADMAP.md) remain authoritative product boundaries.

## Local upgrade and release decision

The existing local server was upgraded from 0.5.0 to **0.6.0** at **http://127.0.0.1:8000**, with schema 7 → 8. **All 33 final live upgrade checks passed**: preserved existing columns/rows, key/setup token and private permissions; new pay-group tables; intact audit chains; current version/liveness and the worker-overlap lookup; private-route and unauthenticated denials; tested assets; and post-upgrade encrypted restore/retained-anchor validation with reusable sessions removed. A disposable consistent-copy migration and verified encrypted rollback archive passed before the old listener was stopped gracefully. No personal files or system settings were changed. See [redacted upgrade evidence](validation/v0.6.0-isolation/local-upgrade.json).

The actual workspace still has **zero employees** and requires first-run setup; the server runs in **local testing mode**, not the production profile. Private rollback evidence/material stays under `data/upgrades/` and is excluded from the source release. Local upgrade archives are not scheduled or off-device backups. Creating an HR account, enrolling MFA and connecting scheduled backups/remote services requires real operator setup; no default credentials or production approval were fabricated.

For a small team, complete real access/MFA/host/backup/policy acceptance before operational core HR use, and retain externally accepted payroll/filings/payments. Enterprise use additionally needs the implementation and assurance requirements above. This release reduces the gap; it does not declare all remaining work finished.
