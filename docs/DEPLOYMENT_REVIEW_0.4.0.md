# OpenPeople 0.4.0 — security, recovery and deployment review

9 October 2026. Scope: this application's source release, fictional data, disposable browser profiles and loopback HTTPS services. Personal files, browser profiles, system certificate/network settings and the existing live workspace were excluded from test mutations. Earlier reports remain historical evidence.

## Deployment decision

**Suitable for a controlled fictional-data pilot; not approved for real-data enterprise production or complete multicountry statutory payroll.** The user confirmed that no VPN, cloud provider or identity-provider tenant is configured. No second computer or authority filing account was supplied. Actual-service acceptance cannot be established by services simulated on the same physical computer.

Substantial code was implemented and verified. The outstanding requirements have not been replaced with an automatic production-ready flag. Small-team real-data use still requires actual host/access/MFA, employer-policy and off-device recovery acceptance. Enterprise use additionally requires the missing jurisdiction/workflow/operations capabilities and independent reviews described below.

## Delivered changes

| Area | Implemented behavior | Boundary |
| --- | --- | --- |
| Cloud transport | Encrypted HTTPS WebDAV upload, conditional immutable names, fresh remote read-back/hash, verified atomic non-overwriting download | Dedicated collection/credentials must be configured; local fixture is not a real account |
| Cloud failures | Idle/size/time budgets, absolute 75-second scheduled subprocess timeout, generic redacted status; database/configuration/snapshot locks released before transfer | Standalone transfer commands require operator supervision; storage quota/retention needs provider management |
| Cloud status | Separate local success and remote read-back; cached verification bound to destination/account | Does not certify another-device recovery or future provider availability |
| Dated payroll rules | US 2026 federal periodic withholding and FICA preview, Decimal/cents, strict modern-W-4/applicability checks, explicit year-to-date inputs | Partial pack only; excludes state/local/unemployment, special wages, corrections, filings and payments; not independently payroll-certified |
| Employer metadata | Legal employers/cost centers, country/currency consistency, employee-versioned assignment/removal | Create-only definitions; fixed roles/shared workspace, no employer permission isolation or pay groups |
| Payroll history | Captures original employer/cost center per statement; reassignment does not rewrite old snapshots | Existing unassigned snapshots are not retrospectively attributed |
| Filing workpapers | Finalized externally reviewed payroll becomes immutable canonical JSON/hash with employer totals, independent review and version checks | Provider-neutral format, not an agency filing schema; roster completeness needs reconciliation |
| External evidence | Audited submitted/accepted/rejected external references and retained receipt hashes | Operator records, not authenticated authority acceptance; government endpoints are never contacted |
| Recovery | Schema 6, employer assignments, payroll provenance, filing snapshots/status/review history and audit retained; old sessions revoked | Same-computer synthetic recovery does not prove physical disk-loss survival |

See [cloud setup](CLOUD_WEBDAV.md), [statutory/filing scope](STATUTORY_AND_FILINGS.md) and [country comparison](PAYROLL_COUNTRIES.md).

## Verification evidence

The final complete run passed **100 backend tests** at **91.28% line coverage**, **55 real-browser checks** and **13 synthetic HTTPS identity checks**. Six HTTPS WebDAV test methods and the TLS/slow-input/recovery/package checks also passed. The final code results are recorded in [the protected machine report](validation/v0.4.0-isolation/report.json), [backend coverage](validation/v0.4.0-isolation/backend-coverage.json) and logs in that directory. Final source-package integrity and runtime equivalence are recorded separately in `final-package-smoke.json` after assembling the report.

| Check | Acceptance covered |
| --- | --- |
| Backend regression | Original eight reported issues and earlier deployment/payroll/SSO fixes remain covered, plus cloud/calculation/employer/filing tests |
| Real Chromium browser | All 20 screens; employee ownership, learning/benefits/leave, external components and escaping, employer/cost-center/assignment forms, statutory preview, filing preparation and independent review/evidence |
| Separate HTTPS identity provider | Real discovery, PKCE exchange, JWKS/signature validation and 13 valid/invalid/replay/key-rotation cases; synthetic tenant |
| Separate HTTPS WebDAV provider | Actual credentials/TLS/conditional PUT/GET, retries, redirects, untrusted certificates, ciphertext/hash tampering, collision rejection, redacted errors and source-path-loss restore |
| Stalled cloud provider | Actual child timeout kills the transfer while a concurrent database write commits; local archive remains successful |
| Actual local Caddy HTTPS | Verified certificate and security headers, Secure cookies, origin/forwarding defenses and stale edit handling |
| Slow inputs | 100 slow headers followed by 100 slow bodies; another client signs in, reads and saves; unfinished inputs expire |
| Encrypted host-loss drills | Fictional source server stopped and original paths removed; fresh recovery retains salary/audit/MFA/payroll and new employer/filing records; old sessions and MFA replay fail |
| Isolation | OS sandbox denies personal-home reads, outside writes and external connections; protected sentinel/live-workspace fingerprints unchanged; owned fixtures removed |
| Source ZIP | Allowlisted source/manifest, no live database, keys, tokens, backups or installed dependencies; fresh fictional Japan startup/setup |

Development runs caught obsolete schema/future-schema test expectations and a test that incorrectly expected financial currency-transfer safeguards to permit a change. Those expectations were corrected, preserving the safeguards. New cloud cache binding, corrupted-packet rejection and restore checks were added before the final run. No failed development run is described as successful.

## Remaining deployment blockers

1. **Actual access and recovery:** configure a private VPN/HTTPS endpoint and test from another computer/network; configure a real provider, download an archive there, restore with the original host unavailable and verify independently held passphrase custody. The cloud/identity fixtures prove protocol code, not actual service policy or offsite custody.
2. **Actual identity tenant:** register/configure an issuer/client/callback and accept verified-email mapping, provisioned/unprovisioned users, MFA, signing-key rotation and leaver/session handling. No live tenant is configured. SAML/SCIM/provider-side session revocation remain absent.
3. **Complete statutory payroll and filing:** independently validated dated country/state/province rules, all worker/pay types, accumulation/corrections/year-end, employer registrations, official formats/certificates and authority/provider sandbox acceptance. No live government submission/payment adapter exists. The partial US pack cannot replace these.
4. **Enterprise scope and operations:** employer/field-level permission sets, delegation/configurable approval graphs, separate pay groups/calendars, fuller hiring/benefits/lifecycle integrations, monitored service installation/reboot acceptance, independent audit retention, capacity/high-availability design and incident ownership. The source is a single shared SQLite host, not a distributed enterprise service.
5. **Host/platform acceptance:** verify actual disk encryption/ACLs, backups/retention/quotas, availability during sleep/reboot and Windows/Linux behavior. This turn did not change system trust, VPN interfaces, service registrations or personal cloud folders.

Workday documents native payroll guides for Australia, Canada, France, Ireland, the UK and the US; its broader global offering uses partner integrations. An all-country selector is not equivalent to embedding all applicable laws. Sources: [Workday country guides](https://doc.workday.com/admin-guide/en-us/payroll/payroll.html), [global payroll integration](https://www.workday.com/en-us/products/payroll/global-payroll.html). No proprietary Workday engine or private customer tenant was copied or certified.

## Next operational step

Use the packaged source for a fictional-data pilot, then follow [actual deployment acceptance](DEPLOYMENT_ACCEPTANCE.md). The existing live process was intentionally not restarted or migrated during testing. Installing this source does not update an already running old process: take a private recovery backup, stop the intended server cleanly and start the new release against the deliberately chosen database. Do not use automatic payroll/filing or enter real employee data on the assumption that local fixture tests granted production approval.
