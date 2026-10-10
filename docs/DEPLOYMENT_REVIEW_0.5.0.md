# OpenPeople 0.5.0 — security, payroll, service acceptance and recovery report

9 October 2026. Scope: the source release, fictional employees, disposable browser profiles and protected local services on this Mac. Earlier reports and archives remain historical evidence. Test processes were confined to temporary storage with personal-home reads and external connections denied. The existing HR database/key/setup token were fingerprinted before and after and remained unchanged. System network, DNS, routes, trust store, browser profiles and startup services were not changed.

## Deployment decision

**Ready for a controlled fictional-data pilot; not approved for real-data enterprise production or complete multicountry statutory payroll.** This release adds working controls and passes the checks below. It does not complete every capability requested. Complete country engines, online authority adapters, several enterprise workflows and actual off-device deployment acceptance remain unfinished.

The user confirmed that no second computer, NAS or external cloud account is available. Independent self-hosted identity, VPN and WebDAV services were configured and accepted on this computer, then stopped and their disposable data removed. This is stronger interoperability evidence than handwritten protocol fixtures, but it cannot demonstrate recovery after physical loss of this computer or access across two real networks. No persistent production services were connected to the existing HR process.

Small-team real-data use still requires actual host/access/MFA, employer-policy and off-device recovery acceptance. Enterprise use additionally requires independently accepted jurisdictions, general permission/workflow requirements, measured capacity and operational/security ownership.

## Delivered and rechecked

| Area | New behavior | Scope and limits |
| --- | --- | --- |
| Payroll access | HR grants all employers, selected employers or an empty restricted set; recent authentication, CSRF, version conflicts and immediate target-session revocation | Fixed payroll role within one workspace; HR/auditors keep their existing scope, basic directory stays shared; legacy payroll accounts remain unrestricted until reviewed |
| Historical payroll | Reads/edits and filing exports follow captured employer IDs; current salary previews follow current assignments | A worker transfer cannot expose old statements through the new assignment; unassigned workers are excluded for restricted operators |
| Approval boundary | Restricted operators cannot create a workspace-wide pay run or finalize a run containing hidden statements | Existing peer edits, permanent draft-maker exclusions, reviewed versions and immutable finalized snapshots remain enforced |
| Audit integrity | Separate SHA-256 chains, transactionally inserted seals, triggers rejecting ordinary event/seal changes, anchor export and read-only prefix/rollback verification | Local database-owner rewrites are not prevented; independent custody is essential; pre-upgrade history is a baseline, not retrospectively authenticated |
| Recovery integrity | Schema-7 restores verify audit chains before publishing restored files; corrupted history fails without creating a recovered workspace | Local chain verification is capped at 200,000 rows per chain; an independent anchor is needed to detect complete historical rewrite/rollback |
| UK statutory component | Dated 2026/27 ordinary non-director weekly/monthly Class 1 NI across 16 categories, strict applicability, integer pence and HMRC software rounding | Component preview only; PAYE, directors, irregular periods, loans, pensions, statutory pay and government transmission excluded |
| US statutory component | Existing 2026 modern-W-4 federal periodic withholding/FICA preview remains tested | State/local/unemployment and special pay/corrections excluded; neither country pack is independently payroll-certified or automatically applied to pay runs |
| Agency file adapter | Restricted SSA 2026 EFW2 domestic regular annual RA/RE/RW/RT/RF export, monetary reconciliation, private exclusive file output | Reviewed annual inputs with no optional amounts only; no monthly-to-annual inference, AccuWage approval or online submission |
| Private identity setup | Certificate/key/name/validity and provisioned-user checks; cost-12–16 bcrypt input; random client secret; new 0700 directory/0600 files; explicit-database launcher | Does not install a service, create a public domain, renew certificates or configure an external tenant; only four identity environment keys are accepted |
| Service interoperability | Actual Dex consent/PKCE/JWKS, local MFA/leaver handling; actual userspace WireGuard peer transport with HTTPS; independent TLS WebDAV upload/read-back/download/restore | Disposable same-computer services; no TUN, system route/DNS/trust changes, second network, real cloud account or separately held backup |

Details: [enterprise controls](ENTERPRISE_CONTROLS.md), [statutory scope](STATUTORY_AND_FILINGS.md), [SSA adapter](GOVERNMENT_SUBMISSION.md), [private service configuration](INDEPENDENT_SERVICES.md) and [cloud transport](CLOUD_WEBDAV.md).

## Final verification

The final code candidate passed **111 backend tests at 91.84% backend line coverage**, **63 Chromium workflow/security checks**, **13 synthetic HTTPS identity checks**, six synthetic HTTPS WebDAV test methods and **nine additional independent-service acceptance checks**. Coverage is combined over the application backend modules; it is not frontend or exhaustive security coverage. The packaged code was extracted into the protected test tree, rather than tested against the existing live database.

| Verification | Observed result |
| --- | --- |
| Original eight reported issues | Existing regressions still pass for unfinished input, token-gated setup, lifecycle/session revival, duplicate retries, large account-timing difference, self-approval, malformed/Unicode input and reserved department names |
| Earlier deployment blockers | Slow input remains bounded; backup I/O/transfer does not hold API write locks; configuration generations, unavailable destinations, optimistic salary edits, human inactivity and audit history remain covered |
| Backend control tests | Employer read/write/metadata/historical access, stale grants, recent authentication, empty scope, revoked sessions; audit edit denial, retained-prefix verification, deliberate corruption and recovery-before-publication rejection |
| Payroll mathematics | US independently worked federal/FICA examples; UK published thresholds/categories, independently worked cases, expiry/input rejection and HMRC's third-decimal rounding examples |
| SSA file format | Fixed record lengths/positions/sequence, two-worker annual totals, unsupported input/identifiers and private non-overwriting output; no actual authority validation |
| Real Chromium | All 20 screens and 63 checks, including UK preview, audit-anchor control, employer-grant form, historical visibility, current-salary hiding and restricted finalization; existing learning/benefits/leave/payroll/filing flows remain covered |
| Synthetic OIDC negatives | Browser-bound state/replay, nonce, audience, expiry, verification, provisioning, signature, key rotation, local MFA and deactivation; real TLS/discovery/PKCE/JWKS transport |
| Independent identity | Generated private configuration accepted by Dex 2.46.0; real consent/code/PKCE/JWKS sign-in, local MFA requirement and inactive identity/existing-session denial |
| Independent VPN | Headscale 0.29.4 and two Tailscale 1.104.1 userspace peers: encrypted WireGuard transport, verified HTTPS, unauthenticated data denial and authenticated save |
| Independent backup | WsgiDAV 4.3.5/cheroot 11.1.2 over TLS: unauthorized request denied, encrypted conditional upload, fresh read-back, retry/collision defense and download |
| Slow connections | 100 unfinished headers followed by 100 unfinished bodies through Caddy TLS; another client signs in, reads and writes; unfinished requests expire. Normal activity was 0.184/0.189 seconds in this run, not a large-workforce benchmark |
| Provider outage | Stalled transfer child is killed at its deadline while concurrent database writes remain available and successful local archives remain intact |
| Source-path-loss recovery | Fictional source stopped/original paths removed; independent provider download restores new private files, no reusable sessions, intact audit anchor and retained payroll/security history; same physical computer only |
| Isolation | Negative file/network controls passed; protected sentinel and live-workspace fingerprints unchanged; owned test folders/processes removed |
| Source package | Explicit source allowlist and SHA-256 manifest; private databases/keys/tokens/backups/service dependencies excluded; fictional Japan startup/setup passed |

Machine evidence: [complete run](validation/v0.5.0-isolation/report.json), [independent services](validation/v0.5.0-isolation/report-services.json), [coverage](validation/v0.5.0-isolation/backend-coverage.json) and [service provenance](validation/v0.5.0-isolation/service-tools-provenance.json). The suite tested code candidate SHA-256 `e9e76ef1e3e16858b5a3ed8074bd250d04cd7af0fb70df118666bd6f4ab7b2b3`. Final packaging adds documentation and evidence; `final-package-smoke.json` records final ZIP integrity, runtime manifest equivalence and an additional isolated startup check. An unchanged runtime does not require pretending that the earlier run used the later ZIP hash.

Development checks identified configuration/schema test expectations, TLS test-certificate watcher placement and local password recovery's audit-function registration. These were corrected before the final complete run. No failed development run is reported as a pass. Passing the listed checks does not establish absence of every vulnerability or an independent security certification.

## Remaining requirements and risks

| Priority | Requirement | Evidence needed before relying on it |
| --- | --- | --- |
| Real-data deployment gate | Private remote access, trusted HTTPS, awake/reboot service operation and endpoint authorization | Actual selected host and a second device/network, individual MFA accounts, authenticated shared writes, denied/stale operations and restart acceptance |
| Physical-loss recovery gate | Off-device encrypted backup, quota/retention monitoring, separately held passphrase/anchor | Download from an independent provider/medium onto a replacement device with the source unavailable, restore canaries/audit and measure recovery time/data loss |
| Identity installation gate | Persistent self-hosted or external IdP policy, provisioning, certificate renewal and identity recovery | Accept the actual issuer/callback/claims and leaver process; existing local sessions require OpenPeople revocation. SAML/SCIM/provider-side continuous revocation remain absent |
| Payroll/legal gate | Complete dated jurisdiction engines and official filing acceptance | Applicable employer/state/province/worker/pay rules, cumulative/retro/year-end/correction cases, independent payroll/legal review and maintained rule updates; country guidance is not executable law |
| Authority-adapter gate | Online transports and all other agency formats | Employer registrations, approved credentials/signing/certificates, official/provider conformance testing and authenticated receipts. Local SSA export must first pass authorized AccuWage/BSO checks |
| Enterprise capability gate | General permission sets, delegation/conditional approvals, pay groups, lifecycle/benefits/accounting integrations | Organization-specific acceptance cases and least-privilege review beyond the implemented payroll scopes |
| Enterprise operations gate | Independent audit custody, retention/alerts, capacity, incident response and high availability | Tested workforce/load envelope, archival design beyond 200,000 rows per chain and 256-MB backup limit, monitored installation, recovery ownership and independent security review |
| Host/platform gate | Disk encryption, private OS accounts/ACLs, patching and platform behavior | Operator verification of FileVault/BitLocker/LUKS and actual Windows/Linux deployment where used; application SQLite is not fully encrypted at rest |

The single shared SQLite host is neither a distributed service nor a high-availability enterprise architecture. Existing unrestricted payroll accounts must be reviewed; generic audit access remains sensitive and HR is workspace-wide. Host compromise can expose live HR data and saved configuration even if off-device backups are encrypted. Local audit hashes do not change that boundary.

No external device/account is available, so installing another service on this same disk cannot satisfy the physical-loss recovery gate. Existing computer hosting avoids renting an application server; available storage, electricity, network reachability and relay/provider limits are still deployment constraints.

## Country and authority source checks

Workday documents native payroll guides for Australia, Canada, France, Ireland, the UK and the US, while its global product uses partner integrations for broader coverage. This project does not copy a private engine or claim universal law coverage. [Workday country guides](https://doc.workday.com/admin-guide/en-us/payroll/payroll.html), [global payroll integrations](https://www.workday.com/en-us/products/payroll/global-payroll.html).

The UK component follows dated [HMRC rates](https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2026-to-2027) and [software technical guidance](https://www.gov.uk/government/publications/payroll-technical-specifications-national-insurance); the downloaded 2026/27 v1.1 ODT hash is retained in tool provenance. The SSA adapter follows the [2026 EFW2 specification](https://www.ssa.gov/employer/efw/26efw2.pdf). As checked on the report date, SSA is not accepting new EWRWS users/consolidators, while BSO upload/W-2 Online remain available; no employer account or legal attestation was used. [EWRWS status](https://www.ssa.gov/employer/EWRWS.htm), [AccuWage requirements](https://www.ssa.gov/employer/accuwage/index.html).

## Next operational step

Use the release with fictional records and the [actual-installation acceptance procedure](DEPLOYMENT_ACCEPTANCE.md). The existing old process was deliberately not restarted or migrated during testing. Source changes alone do not upgrade an already running process. Take a private recovery backup, stop the intended server cleanly, and start the new release against a deliberately selected database; review access grants and retain an independent audit anchor. Keep tax/filing/payment in an externally reviewed system until each required jurisdiction is accepted.

This release has no automatic production-approved flag. The missing external recovery setup and enterprise/regulatory capabilities must remain visible when deciding whether real employee data can be used.
