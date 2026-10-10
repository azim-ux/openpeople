# OpenPeople 0.3.2 — verification and deployment report

9 October 2026. Scope: the local OpenPeople source release, fictional accounts and isolated data on this computer. This report supersedes 0.3.1's browser limitation. The historical reports remain evidence of their own releases.

## Deployment decision

**The tested release is ready for a controlled fictional-data pilot. It is not approved for enterprise production or automatic multicountry statutory payroll.** Small-team use with real records still requires acceptance of the actual host, access controls and off-device recovery described in [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md). No actual VPN-connected second computer, cloud account or external identity-provider tenant was available.

Code/security regression checks, real browser acceptance of the tested workflows, real loopback HTTPS collaboration and simulated loss recovery pass. These results do not establish physical disk-loss recovery, real provider configuration, jurisdiction compliance, capacity for an enterprise workforce or full Workday parity. The existing default local listener/database was left untouched by testing; a running older process must be safely upgraded before it serves this code.

## Changes delivered

- Added an external payroll result workflow: earnings, employee deductions, separate employer contributions, net pay, provider/reference/jurisdiction, rules effective date and review note. Server validation enforces exact format, integer currency minor units, totals, employee/month/country/currency and amount limits.
- Imports use the existing stale-version, peer-only own-pay edit and independent finalization controls. Every editor remains excluded from approval. Mixed manual/import payloads, stale imports, changes to imported breakdowns through the manual deduction endpoint, and finalized edits are rejected. Audit history records before/after provenance. Source calculations are labeled external after import.
- Added browser import/template download and component/provenance display in reviewed statements. Imported text is escaped. Employees receive only their own finalized records. No third party is contacted by this workflow.
- Added guidance for all six countries in Workday's current native-payroll overview. The 251 existing HR country/region options remain available. Automatic statutory calculation and government filing remain explicitly unavailable.
- Added a read-only HTTPS/offline deployment checker and an operator acceptance procedure. SQLite offline inspection opens immutable/read-only, refuses pending WAL state and does not create database side files. The checker never substitutes technical preflight for enterprise approval.
- Replaced the previously blocked installed-Chrome attempt with an official portable Chromium headless engine using an empty disposable profile. It runs under the same mandatory filesystem/network restrictions; no existing browser profile, personal keychain or system certificate trust is used.
- Added a separately serving local HTTPS OIDC provider fixture. Real discovery, redirects, PKCE exchange, signed-token validation and JWKS retrieval are exercised through network requests, beyond the earlier mocked endpoint tests.
- Schema 5 adds payroll provenance while retaining prior draft editor/version controls. Backup verification accepts schemas 2–5; a future schema is rejected. Do not downgrade a schema-5 workspace into an older release.

## Verification results

Machine-readable evidence: [full protected report](validation/v0.3.2-isolation/report.json), [runtime fingerprints](validation/v0.3.2-isolation/runtime-fingerprints.json), [browser provenance](validation/v0.3.2-isolation/browser-provenance.json).

| Check | Observed result | Limit |
| --- | --- | --- |
| Backend regressions | 87 passed; 90.49% combined application-backend line coverage, 1,827/2,019 executable lines | Coverage is not proof of absence of bugs; deployment scripts are outside that application coverage denominator |
| Frontend logic | 20 routes, HTML/CSV escaping, reporting keys, failed-refresh duplicate prevention, revision polling and payroll review controls passed | DOM stubs supplement actual browser checks |
| Actual browser | All 20 screens rendered; course creation/assignment, benefit setup/enrollment, course completion, leave submission, own-approval controls, payroll edits/stale review, external import, HTML escaping, independent finalization and employee-only statements passed | Tested workflows only; no full licensed Workday feature acceptance, cross-platform or pixel/layout certification |
| HTTPS identity | 13 checks passed; 22 discovery, 11 PKCE-verified token exchanges and 11 JWKS requests | Separately serving synthetic local provider, not a commercial/live tenant |
| HTTPS preflight | Certificate trust, initialized setup, HSTS, CSP/framing, no-sniff, no-store and unauthenticated data denial passed | Loopback client, not a VPN second-device test |
| Slow headers | 100 connections; fresh login 200, read 200, save 201; zero unfinished inputs after deadline | Bounded local test, not enterprise capacity certification |
| Slow bodies | 100 connections; fresh login 200, read 200, save 201; zero unfinished inputs after deadline | Same limit |
| Encrypted loss recovery | Source server stopped, original path unavailable; downloaded-copy hash matched; restore/verification passed | Provider upload/download modeled by separate local folders |
| Recovered controls | Salary 720,000, audit, MFA, payroll version 2, external components/reference and editor exclusion preserved; old sessions/MFA replay denied | Two fictional users; measured local restore about 0.18 seconds is not a promised production recovery time |
| Source package | Integrity/manifest checked; fresh startup/setup and JP/JPY profile passed; private data excluded | Dependencies must be installed on a new host; source ZIP is not a preinstalled desktop binary |
| Isolation | Protected read/outside write/external connection attempts denied; sentinel unchanged; live-workspace fingerprints matched; temporary test fixtures removed | OS safeguards do not certify unrelated applications or the entire host |

Initial development runs exposed and corrected a SQLite-row/dictionary conversion, an omitted SQLite URI flag, future-schema assertions and unstable/live fixture assumptions. The final complete run passed after those corrections. No unresolved failure is hidden behind the final results.

The portable browser was obtained from Google's official Chrome for Testing metadata/download endpoints. ZIP integrity and local archive/binary SHA-256 were recorded. An independent publisher checksum was not available, so the evidence does not claim one was checked. [Official headless documentation](https://developer.chrome.com/docs/automation-and-testing/headless).

## Security and recovery assessment

The original eight reported weaknesses and the additional payroll/SSO fixes from 0.3.1 remain covered by regressions. This release additionally tests external payroll authorization, stale versions, exact payload shape, arithmetic consistency, integer/bounds validation, HTML escaping, locked final records and preserved provenance after recovery. These scoped checks found no unresolved failure in the tested paths; they do not establish that every vulnerability has been found.

OIDC tests reject wrong nonce/audience, expired tokens, unverified or unprovisioned identities, invalid signatures, reused state and a callback from another browser. Signing-key rotation works. An enrolled local factor remains required after SSO. Deactivation denies subsequent sign-in and revokes the established local session. Provider-side disablement alone is not an instant local-session revocation mechanism; SCIM/back-channel logout are not implemented.

Backups are authenticated encrypted snapshots, not database synchronization between independent servers. The recovery drill included payroll provenance and maker/reviewer exclusions, so restored data cannot silently shed that approval boundary. Live SQLite is not encrypted by this app. Disk encryption, passphrase custody, off-device copies, sync-client quota/health, an awake host and operating-system service recovery still need actual installation evidence. A read-only FileVault status command could not resolve the volume in this environment; no host encryption setting was changed or certified.

## Workday payroll research

Current Workday documentation lists Australia, Canada, France, Ireland, the UK and the US as native country payroll products. Wider global coverage is advertised through certified partners in more than 180 countries. OpenPeople implements neither Workday's licensed tax engines nor those certified connectors. [Country guide](https://doc.workday.com/admin-guide/en-us/payroll/payroll.html), [global payroll](https://www.workday.com/en-us/products/payroll/global-payroll.html).

The delivered [country guidance and contract](PAYROLL_COUNTRIES.md) explain supported manual/external modes and link to authoritative payroll sources. Automatic all-country tax calculations, filings, settlements, legal-entity/pay-group calendars, retroactive/year-end processing and bank/accounting reconciliation require jurisdiction-specific development and independent validation. Country selection and importing an externally calculated result do not certify compliance.

## Remaining acceptance and engineering

| Requirement | Current evidence | Required next evidence/work |
| --- | --- | --- |
| Small-team core HR | Working tested workflows and security controls | Actual individual accounts/MFA, employer-policy acceptance, host permissions/encryption, service restart, actual remote connection and off-device restore |
| Remote collaboration | Independent loopback HTTPS clients and stale-write rejection | Another authorized device on the chosen VPN/HTTPS setup; authenticated edit/refresh/denial tests |
| Cloud recovery | Encrypted recovery with the fictional source unavailable | Confirm real upload, retrieve through provider on a replacement device and restore with separately held phrase |
| Organization SSO | Local HTTPS protocol acceptance | Actual issuer registration, claims/policies, key rotation and leaver/session workflow |
| Multicountry payroll | Reviewed manual/external results and six-country planning guidance | Reviewed country/state engines or tested provider adapters, complete payroll/filing/payment acceptance |
| Enterprise operations | Single local organization, fixed roles, SQLite and bounded serving | Organization/field permissions, legal entities, configurable workflows/delegation, capacity testing, monitoring, independent audit/retention, incident handling and availability design |
| Broad Workday parity | Original HR navigation and listed workflows | Full recruiting/benefits/talent/learning/finance/planning/document/integration capabilities as required; see [capability map](ROADMAP.md) |

Use [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md) for concrete operator checks. The source code and portable test tools cannot create evidence for unavailable real accounts, another physical computer or unimplemented statutory engines. The release metadata therefore retains `production_approved: false`.
