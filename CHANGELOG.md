# Changelog

## 0.8.2 — Hosted installer acceptance fixes

- Windows ACL verification now treats PowerShell errors and missing confirmation as failure, and removes incompatible inherited PowerShell module paths.
- Windows workspace locking detects an active host without reading its locked byte.
- Installer safety fixtures resolve macOS temporary-directory aliases while preserving rejection of user-selected symlink paths.
- Added three Windows permission-verification regressions. Core HR behavior and dependency versions are unchanged.
- Public repository and installer instructions link to GitHub downloads and hosted acceptance results.

## 0.8.1 — Offline installer kits

- Added per-user Windows x64, macOS Apple Silicon and Linux x64 installer ZIPs containing SHA-256-pinned portable Python and hash-verified application wheels. No global Python installation or install-time download is required. Current cryptography dependencies no longer support Intel Mac wheels; no dependency downgrade is used.
- Added dedicated private workspace storage, verified payloads, running-workspace locks, preserved program versions, rollback on failed launcher publication and data-preserving uninstall/reinstall. No OS service/network settings or default administrator credentials are installed.
- Added a bundled browser launcher and maintenance commands, installation/security regressions, native installer acceptance probe and a cross-platform GitHub build/test workflow. Platform execution and publisher signing/notarization are recorded separately from artifact construction.

## 0.8.0 — Core HR release candidate

- Added a user-facing download/self-hosting guide for individual computers and shared servers, with consistent Core HR startup and Windows workspace/backup paths. Normalized public ZIP file permissions and preserved the macOS launcher's executable bit; package verification checks both.

- Enforced process-selected Core HR scope across APIs, replay, state, reports, roles, policies and browser navigation; existing broader data is retained. Production defaults to Core HR.
- Added private read-only installation/HTTPS evidence and reference-based recovery commands, bounded restore objectives, authenticator-key usability checks and explicit physical-custody limits.
- Added Core HR browser/regression coverage, public-package production CLI/TLS installation and independent local VPN/WebDAV recovery drills.
- Documented installation acceptance and excluded private evidence folders from source control. No personal credentials, remote account, second device or OS changes are required to build/test the release.


## 0.7.0 — 2026-10-10

- Added private, interactive operator setup with verified TOTP enrollment and mandatory MFA; no personal email or pre-created release account is required.
- Fixed private file creation to remove newly created partial enrollment/key material after a write/flush failure and preserve existing files on exclusive-creation refusal.
- Added once-disclosed, hashed, single-use MFA recovery codes for local and OIDC-factor sign-in, concurrent-use protection, session revocation and replacement/password-reset invalidation.
- Migrated to schema 9 and excluded recovery codes from encrypted snapshots/restores to prevent credential resurrection.
- Raised the allowed PyJWT minimum to the pinned/tested 2.15.1 instead of permitting older releases covered by the upstream recursion-error advisory.
- Added a separate public GitHub source export, manifest/privacy/runtime checks, read-only SHA-pinned CI and dependency update configuration. No remote publication or external-provider acceptance is implied.

## 0.6.0 — 2026-10-09

- Added employer pay groups, versioned memberships and dated weekly/fortnightly/semimonthly/monthly, bonus and adjustment snapshots. Prevented regular overlaps within groups, across worker group transfers and with legacy monthly payroll in both creation orders.
- Added period-bound external payroll v2, complete-result requirements, independent finalization, own dated statements and recovered period/group snapshots. Statutory calculation and official submission remain separate acceptance requirements.
- Added an explicit production launch profile, mandatory-MFA protection, private operational readiness, minimal liveness, read-only diagnostics and bounded child restart supervision without OS service installation.
- Changed full audit/recovery verification to stream records without the interactive 200,000-row ceiling; kept interactive verification bounded. The existing backup byte-size limit remains.
- Added browser, security, production-profile, supervisor and large-audit recovery cases. The next deployment report records actual results and remaining external/regulatory/enterprise gates.

## 0.5.0 — 2026-10-09

- Added employer-scoped payroll access, recent-authentication/version guards and session revocation. Salary previews, historical statements and filing exports respect original employer snapshots; partial-scope finalization is denied.
- Added append-only audit/security-event hash chains, independent anchor export/comparison and schema-7 recovery rejection for corrupted history. Local administrator rewrites still require independent retention to detect.
- Added UK 2026/27 weekly/monthly Class 1 NI component previews across the published categories and HMRC's special third-decimal rounding. PAYE and full UK payroll remain unsupported.
- Added a restricted SSA 2026 EFW2 annual-file formatter, private non-overwriting exports and structural/reconciliation tests. No authority submission or acceptance is claimed.
- Added private certificate/user-validated Dex/client configuration and an explicit-database SSO launcher. Configured and tested independent Dex, actual userspace WireGuard peers and WsgiDAV recovery inside the disposable sandbox.
- Expanded real-browser employer-scope/audit/UK-preview checks. No external device/account was available; remote NAT, off-device physical recovery, commercial tenant acceptance and universal payroll/enterprise readiness remain pending.

## 0.4.0 — 2026-10-09

- Added encrypted HTTPS WebDAV conditional uploads, independent checksum read-back, verified non-overwriting downloads, redacted cloud status and a 75-second scheduled-transfer subprocess deadline. Cloud failures preserve successful local archives and hold no database/configuration/snapshot locks.
- Added the partial dated US 2026 federal periodic-withholding/FICA preview, strict applicability/input checks and explicit exclusions. It does not silently apply tax or claim complete statutory payroll.
- Added legal employers, cost centers and optimistic worker assignments, with immutable per-statement employer/center snapshots. Schema 6 and encrypted recovery preserve them.
- Added provider-neutral filing workpapers from finalized externally reviewed payroll, canonical hashes, independent review, stale-version rejection and audited external receipt tracking. Government submission and authenticated agency acceptance remain unavailable.
- Expanded protected HTTPS cloud recovery, mathematical/authorization/filing tests and actual browser workflows. All actual VPN/cloud/identity services remain unconfigured.

## 0.3.2 — 2026-10-09

- Added reviewed external payroll results with component totals, provider provenance, currency/employee/month binding, version preconditions, maker exclusions and immutable finalized statements. Schema 5 retains provenance; encrypted recovery preserves it.
- Added browser import/templates and component display, plus payroll guidance for Australia, Canada, France, Ireland, the UK and the US based on current primary sources. Automatic statutory calculation, filing and payments remain unavailable.
- Added read-only HTTPS/offline deployment diagnostics and an actual-installation acceptance procedure.
- Resolved the prior browser testing block using an official portable headless Chromium engine inside the same mandatory sandbox. All 20 screens and 45 workflow/security checks passed with disposable profiles and fictional records.
- Added real local HTTPS OIDC protocol acceptance: 13 checks covering PKCE, signed identity tokens, state binding/replay, key rotation, MFA and deactivation; no commercial tenant was available.
- Passed 87 backend tests at 90.49% combined application-backend line coverage, frontend checks, real loopback TLS/two-client collaboration, 100 slow headers and 100 slow bodies, encrypted simulated source-host loss recovery and source-package smoke checks. Personal-file protections and live-workspace fingerprints passed.
- Added the [0.3.2 deployment report](docs/DEPLOYMENT_REVIEW_0.3.2.md). Actual off-device recovery/remote setup, live IdP tenant and enterprise/jurisdiction capabilities remain acceptance requirements.

## 0.3.1 — 2026-10-09

- Reproduced three additional weaknesses using archived source and fictional data: payroll own-deduction editing followed by same-actor approval, stale payroll approval, and shared-worker exhaustion during a slow trusted SSO provider.
- Added peer-only deduction edits, retention of every draft editor, independent finalization and transactional reviewed-version preconditions. Schema 4 preserves legacy draft-editor exclusions from audit history; backup verification accepts schemas 2/3/4.
- Updated payroll UI controls and invalidated a review when background refresh sees a newer version; reopening is required before finalization.
- Added nonblocking SSO concurrency admission shared by starts/callbacks, with capacity reserved for normal requests and exception-safe release.
- Added five backend regressions, six frontend security checks and protected before/after evidence. Real Chrome acceptance was attempted in an empty profile but denied by mandatory isolation; it is explicitly unverified.
- Validated 81 backend tests (90.11% combined coverage), frontend logic, actual loopback TLS with two 100-connection slow-input probes, and simulated encrypted loss recovery preserving payroll revisions/editor exclusions, salary, audit and MFA. Live-workspace fingerprints matched and fixtures were removed.
- Added the [security and deployment report](docs/DEPLOYMENT_REVIEW_0.3.1.md). Actual remote/provider recovery, browser acceptance and enterprise/domain capabilities remain required before production use.

## 0.3.0 — 2026-10-09

- Fixed slow-request admission and deadlines, including fresh fragmented requests. Added the tested bounded Caddy HTTPS configuration.
- Moved backup work and destination checks outside API write transactions. Added cross-process locks/generation protection, cached destination health, persistent failures, interrupted-job recovery, catch-up, retention and archive read-back verification.
- Added required employee versions, explicit conflict reconciliation, intentional field changes and effective compensation history. Corrected future/current salary scheduling.
- Fixed idle renewal from polling, cleared private browser caches on expiry, and added session inventory/revoke, account throttles, sanitized policy history/denials and paginated exports.
- Added leave entitlements/accrual/allocations, partial days, workweeks, country/company holidays, amendments and independent cancellation review; overnight/split attendance and independent corrections.
- Added benefits withdrawal/windows/roster, learning overdue/reminders/reassignment, expense evidence/limits/amendment/reconciliation and corrected staged approval messages.
- Added offline country/region, currency and timezone options; segregated currency totals and preserved zero-/two-/three-decimal amounts. Sample data is opt-in and excluded from operational payroll/reports.
- Validated 76 backend tests (89.87% combined coverage), frontend checks, actual loopback Caddy TLS with two 100-connection slow-input probes, and simulated new-host recovery with MFA.
- Added a macOS test sandbox with negative file/network controls, live-workspace fingerprint checks and cleanup verification. Corrected coverage instrumentation to trace only exact backend files in extracted source copies; the protected 76-test/frontend/TLS/recovery run passed.

Country-specific statutory payroll, broad enterprise suite parity, actual offsite VPN/provider validation and independent Windows/Linux deployment remain outside the validated release. See [the report](docs/DEPLOYMENT_REVIEW_0.3.0.md).

## 0.2.0 — 9 October 2026

- Fixed all eight reproduced audit findings: unfinished-request write blocking, bootstrap takeover, session revival, duplicate retries, large login timing difference, HR self-approval, malformed identifiers/Unicode errors and reserved department names.
- Added fixed specialist/manager roles, direct reporting relationships, configurable independent/two-stage approvals and lifecycle session revocation.
- Added benefits enrollment, learning assignments/completion, notifications and client update polling.
- Added manual payroll snapshots, deductions, independent finalization and private printable statements.
- Added encrypted authenticator MFA, required-MFA policy, local password changes/recovery, optional signed OIDC/PKCE sign-in and authentication auditing.
- Switched the CLI to bounded Waitress serving, exact HTTPS-origin/Host checks and an explicit loopback proxy boundary.
- Added versioned authenticated encrypted backup, scheduled cloud-folder output, validated restore and Unix private file permissions.
- Added backend/frontend regressions, real Waitress concurrency checks, disaster-recovery command tests, launchers and setup documentation.

Full statutory payroll, enterprise Workday parity, independent offline synchronization and live external-provider deployment are outside this release.
