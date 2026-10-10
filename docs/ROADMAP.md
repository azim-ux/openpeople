# Core HR scope — 0.8.0

The process-selected Core HR release candidate exposes people/reporting relationships, leave, attendance, onboarding checklists, core reports, notifications, account security, audit and backups. Backend routes, reports, policy inputs and account roles enforce that scope. The capability table below describes the full feature preview, including workflows disabled in Core HR. See [installation and acceptance](CORE_HR_RELEASE.md). Production deployment still needs actual host/remote/off-device/operator acceptance.

# Capability map — OpenPeople 0.7.0

OpenPeople runs a shared local HR workspace. The [latest deployment review](DEPLOYMENT_REVIEW_0.7.0.md) documents private operator setup, single-use account recovery, clean public packaging and remaining gates. Earlier audits remain historical evidence. A private Workday or Kotak tenant was not inspected; this is not an exhaustive licensed-feature comparison or enterprise deployment approval. Building and publishing source requires no personal email or pre-created administrator.

## Current capability boundaries

| Area | Implemented in 0.7.0 | Remaining work |
| --- | --- | --- |
| Core HR | Directory, roles, manager hierarchy/cycle checks, audited email/start/end corrections, versioned edits, effective compensation, sample separation, legal employers/cost centers and versioned assignments captured in payroll | Custom fields, contracts/documents, imports and full lifecycle history |
| Countries | 251 country/region choices, operating currencies with correct minor-unit precision, IANA worker timezones, country holidays and custom workweeks | Country/state statutory engines, localized legal workflows, translations and legal-entity rules |
| Authorization | Employee/manager/HR/recruiter/payroll/auditor scope, ownership and independent review; versioned employer payroll grants/session revocation with historical snapshot enforcement | Custom permission sets, general field-level/organization security, delegates and multi-organization tenancy |
| Identity | Passwords, TOTP MFA/policy, private terminal operator enrollment, single-use hashed recovery codes, password changes, optional OIDC/PKCE, local recovery, session inventory/revoke, account throttling; private Dex configuration and independent local acceptance | SAML, SCIM/provider deprovisioning, passkeys, device/risk policy and actual installation/tenant acceptance |
| Leave | Annual/monthly company accrual, allocations/carryover, holidays/workweeks, partial days, balance/overlap checks, amendment and cancellation review | Region-specific entitlements, carryover expiry, exception rules, shared calendar and richer historical ledgers |
| Attendance | Worker-local dates, overnight/split sessions, breaks and independent correction review with stale-data rejection | Schedules, timesheets, overtime, clock devices and location policies |
| Payroll | Effective salary and calendar-day join/exit proration, approved unpaid leave, separate currency totals, manual deductions or externally calculated components/provenance, six-country guidance, partial US federal/UK NI previews, employer-scoped filing workpapers/evidence, restricted SSA annual-file export, immutable monthly/group-period snapshots, weekly/fortnightly/semimonthly/monthly pay groups, versioned roster, reviewed bonus/adjustment periods and mandatory period-bound external results, independent finalization and own statements | Independently accepted complete tax/statutory engines, automatic pay calendars, retro/year-end calculations, settlements, authority transmission/acceptance, other agency formats, reconciliation and bank payments |
| Benefits | Currency-scoped catalog, enrollment windows, roster/export, withdrawal/re-enrollment and audit | Eligibility/dependents/life events, provider enrollment and payroll deduction integrations |
| Approvals | HR-only, manager-or-HR and manager-then-independent-HR templates; policy saved with each request; staged UI | Arbitrary conditional routing, delegation, escalation and SLA management |
| Recruitment/onboarding | Candidate stages and initial worker checklist | Requisitions, interviews/offers, candidate-to-worker conversion, reusable onboarding/offboarding, equipment and e-signatures |
| Performance/learning | Goals/progress; course links, assignments, completion, overdue status, reminders and reasoned reassignment | Review cycles, competencies, calibration, succession; course delivery, quizzes, SCORM and certifications |
| Expenses | Native currencies and company limits, receipt references, independent review, pending amendment/cancellation, approved cancellation review, external reconciliation reference | Secure receipt-file storage, travel policies, actual reimbursements and accounting integration |
| Reporting | Demo-excluded workforce/department totals, separated money totals, bounded date/page exports and audit details | Custom report builder, effective-dated organization analytics, planning and large-workforce optimization |
| Audit | Redacted business/policy before-after history, authentication/access denials, exports and backup outcomes; append-only local SHA-256 chains and separately retained-anchor checking, including streamed full/offline restore verification beyond the interactive 200,000-row budget | Independent/WORM logging or signed custody, audit retention/pruning/archival and enterprise volume acceptance, incident alerts and independent assurance |
| Security/deployment | Hardened Waitress, tested Caddy TLS configuration, human inactivity timeout, schema migration, private files, encrypted authenticator fields, explicit technical production gates, bounded restart supervision and liveness/private readiness | Encrypted live database/key rotation, service installers/reboot acceptance, external monitoring/alerts, verified OS disk encryption/ACLs, Windows/Linux and actual remote installation tests |
| Backup/cloud | Async encrypted snapshots, cross-process config coordination, cached destination identity/health, read-back, generation-scoped retention, verify/restore CLI, interrupted-job recovery, HTTPS WebDAV conditional upload/read-back/download and absolute scheduled-transfer deadline; independent local WebDAV host-path-loss recovery | Off-device provider acceptance, restore from another computer, incremental/over-256-MB backups and automatic failover |
| Collaboration | One authoritative server, teammate polling, retry idempotency, employee/payroll optimistic conflicts and reviewed payroll versions; local userspace WireGuard peer HTTPS/write acceptance | Actual second-network/NAT acceptance, independent offline edits/merge, distributed replication and high availability |
| Broader suite | HR scope above | Financial management, procurement, projects, adaptive planning and broad enterprise integrations |

Country selection describes the worker's operating profile. It does not certify payroll or legal compliance. Company default leave/expense policies are editable examples; have the employer validate them before use. There is no foreign-exchange conversion or payment processing.

## Next priorities

1. Configure and accept the actual private VPN, trusted HTTPS, MFA, cloud client and recovery-passphrase custody. Download an archive on another computer and restore there before relying on offsite protection.
2. Use the six-country [payroll guidance](PAYROLL_COUNTRIES.md) and external-results contract. Implement authoritative tax/statutory rules or tested provider adapters with independently checked country/state fixtures; retain external/manual review until those checks pass.
3. Extend the implemented payroll employer scopes to reviewed general permission sets; add reusable onboarding/offboarding and candidate conversion, then the organization's required benefits/accounting integrations.
4. Accept monitored platform service installation, append-only audit delivery, passkeys, provider deprovisioning, storage/capacity checks and platform-specific acceptance.
5. Expand talent, documents, reporting and configurable workflows using reviewed domain rules and access scopes.

The app requires no hosted application server. Existing hardware, power, network reachability, cloud quota and any required relay remain installation-specific. Separate offline workspaces do not synchronize their databases.

## Active production capability contract

Operators need an explicit production launch mode that refuses unsafe technical configuration, operational health checks, restart supervision, and payroll groups with dated regular/adjustment periods. HR defines employer-bound groups and versioned memberships; authorized payroll operators prepare immutable period snapshots and import independently reviewed results. Independent colleagues finalize only complete reviewed periods. Original monthly runs and historical employer access must remain compatible.

Fixed invariants: no statutory compliance inferred from country selection, no government transmission or legal attestation without authorized credentials, no self-approval, no stale membership/result overwrites, no overlapping regular periods in the same group or for a worker across group transfers, and no personal-file or OS network/trust changes. Large audit verification must stream and preserve independently retained-anchor checks; interactive verification retains its bounded budget.

The implementation lane owns schema migration, period-bound external results, production technical checks, monitoring/supervision and regression/browser/recovery validation. It does not certify all-country law, authority acceptance, host disk encryption, off-device custody or high availability. These need real evidence and independent domain/installation review; an operator checkbox or same-disk backup cannot manufacture that evidence. See [the release report](DEPLOYMENT_REVIEW_0.6.0.md) for delivered status and remaining acceptance gates.
