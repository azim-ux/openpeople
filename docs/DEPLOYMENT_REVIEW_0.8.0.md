# Core HR release review — 0.8.0

Date: 2026-10-10. Decision: the scoped Core HR release candidate and its acceptance commands are implemented and verified with fictional records. Publication of clean source is supported. Real employee deployment still requires the installing organisation's actual host, access, privacy/security and independent recovery acceptance. Enterprise payroll and broader Workday-equivalent functionality are outside this milestone.

## What changed

- Added a process-selected Core HR profile. Its API route allowlist runs before idempotent replay; state projection, report choices, roles, policy inputs, navigation, dashboard actions and onboarding/reporting surfaces follow the same scope. Payroll and broader unfinished modules are disabled. Their stored records remain intact.
- Production startup defaults to Core HR and checks that active account roles fit the scope, in addition to existing HTTPS, MFA, private-file, integrity/audit and current scheduled-backup gates. Desktop launch wrappers select Core HR; the full feature preview remains an explicit separate option.
- Added `scripts/accept_core_hr.py` for stopped-workspace installation checks, verified HTTPS endpoint checks, a frozen recovery reference and restoration into a new destination. Evidence is created exclusively as private files; passphrases are prompted privately. Recovery verifies the data fingerprint, retained audit chains, authenticator-key usability and removal of reusable credentials. It records restoration time against an explicit objective without claiming physical custody or legal approval.
- Added [the operator installation and acceptance procedure](CORE_HR_RELEASE.md), maintained the generic installer with no personal mailbox requirement, and excluded private acceptance evidence from source control/public export.
- Added [download and self-hosting instructions](SELF_HOSTING.md) for personal computers and shared organisation servers. Corrected preview-selecting examples and Windows backup paths. The public ZIP now normalizes ordinary file permissions and preserves the executable macOS launcher; a regression check first reproduced the missing mode metadata and then passed against the rebuilt export.

## Verification

| Check | Result |
| --- | --- |
| Backend integration/security regressions | 140 tests passed; 92.03% combined backend line coverage |
| Core HR real-browser acceptance | 26 checks passed across its 12 screens, including record creation, policy save, leave submission, self-approval denial, role/salary visibility and disabled deep links |
| Broader preview browser regressions | 77 checks passed |
| Synthetic verified-HTTPS identity acceptance | 13 checks passed |
| Fresh public-source installation | Nine checks passed: manifest-verified clean extraction, private installer state, actual packaged production CLI behind Caddy TLS, endpoint evidence, two-client MFA/shared edits/stale rejection, scope enforcement, source-path-loss recovery and replacement-host backup refusal |
| Independent local services | 12 checks passed using actual Dex 2.46.0, Headscale 0.29.4/two Tailscale 1.104.1 userspace peers, WsgiDAV 4.3.5/cheroot 11.1.2 over verified TLS |
| Independent service recovery | Provider upload/read-back/collision handling/download, original database and local archive paths unavailable, retained record/audit reference match, fresh MFA login and old-session rejection passed |
| Availability and larger audit history | Existing 100 slow-header + 100 slow-body TLS drills and recovery of 200,005 fictional audit events passed |
| Dependencies and frontend | Offline lock consistency, installed dependency compatibility, frontend syntax/workflow/scope regressions passed |
| Live local preview upgrade | Nine checks passed after encrypted rollback verification; version 0.8.0/Core HR, rows/key/setup token preserved, integrity/foreign keys, unauthenticated denial and a fresh encrypted backup verified |

Protected full and service suite reports cover the same 92 runtime/test/CLI entries. The runner blocks personal-home reads except the installed Python environment, confines child writes to a removed temporary tree, and blocks external networking. Sandbox sentinel and live-workspace fingerprints remained unchanged during both suites. The subsequent separately authorised local upgrade intentionally updated only the project application/workspace files. No system VPN/TUN/DNS/routes, certificate trust, browser profile, personal files or reboot/sleep settings were changed.

The download follow-up changes documentation, public packaging and its regression probe. Application/backend/frontend source remains identical to the full-suite build. The companion `release/openpeople-0.8.0-verification.json` records exact current archive hashes, unchanged runtime entries and the separately checked packaging changes, plus the final package's fresh installation/TLS/recovery outcome. It supersedes earlier archive hashes for distribution.

Private working-folder evidence is retained under `docs/validation/v0.8.0-isolation/` (full/service reports, coverage, browser/installation/recovery logs and local upgrade verification). The clean GitHub export excludes those logs and all databases, keys, setup tokens, recovery material and private service state. Post-package proof is kept beside the release archives rather than embedding a circular archive hash.

## Current local instance

The preview at `http://127.0.0.1:8000` now runs 0.8.0 in the Core HR profile, schema 9. It has no administrator or employee records and remains in local testing mode. Its existing setup token and encryption key were preserved. No administrator password, mailbox or authenticator was invented on behalf of the user. Installing organisations choose credentials privately with the supplied installer.

## Remaining installation acceptance

The VPN peers, identity provider and backup provider used above were separate processes on this computer and were stopped after testing. No actual external device/account exists in this installation. These passes cannot demonstrate physical disk-loss survival, another real network/NAT, separately held credentials or a particular external identity tenant. The commands facilitate those checks; they keep approval/custody flags false.

Before real employee use, validate the actual host's disk encryption/ACLs, individually provisioned accounts and MFA, monitored startup/reboot/TLS renewal/backups/updates, intended load/capacity, independent recovery storage/passphrase/reference, total recovery time/data-loss objectives, employer leave/attendance/privacy policies and independent security review. Verify external identity-provider acceptance if SSO is selected. The single-host SQLite design, 256 MB database backup limit and absence of high availability remain deployment constraints.

Statutory payroll, government transmission, bank payments, broad configurable enterprise permissions/approvals, SCIM/WORM custody and the other full-preview roadmap gaps are not advertised as supplied by Core HR. Keep payroll and filings in reviewed external systems. GitHub publication and hosted CI execution remain operator actions; publishing source does not run its Python backend or database.
