# OpenPeople 0.7.0 release review

Review date: 2026-10-10. This release prepares generic source for GitHub publication without requiring a personal email or provisioning the author's workspace. It adds private operator enrollment and single-use account recovery. It is not unrestricted enterprise production approval or a complete Workday replacement.

## Changes

- A terminal-only setup command creates an administrator in an empty explicit workspace after privately entered password confirmation and actual TOTP proof. The default login `admin@openpeople.invalid` requires no real mailbox; no email or external account is used. MFA is mandatory, samples and sessions are absent, and temporary enrollment material is private and removed on interruption.
- Private file creation now removes newly created partial files when writing/flushing fails. Exclusive-creation failures leave existing files intact; the regression injects a disk-flush failure without touching personal storage.
- Ten 128-bit recovery codes are disclosed once following recent verified authentication and a fresh authenticator code. Only SHA-256 hashes are stored. Consumption is atomic, concurrent reuse fails, other sessions are revoked, and old sets are invalidated on replacement or password recovery. Disabled accounts cannot use codes. Both local and OIDC-factor login accept recovery codes.
- Schema 9 adds the recovery-code table. Encrypted snapshots and restore both discard recovery-code hashes as well as reusable sessions and temporary sign-in state. An old archive cannot resurrect a spent code. Operators need fresh recovery codes after restoration.
- A separate GitHub export includes source, MIT license, pinned dependencies, tests and documentation while excluding operational data, enrollment files, private test logs and local audit evidence. A manifest and probe check private-file exclusions and byte-for-byte runtime equivalence. GitHub workflow actions are pinned to official commit hashes, have read-only repository permissions and use no deployment credentials.
- Raised the allowed PyJWT minimum from 2.10.1 to the already installed/pinned 2.15.1. The [upstream recursion-error advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v) lists releases through 2.14.0 as affected and 2.15.0 as patched. This closes an overly permissive dependency constraint; no vulnerable installed PyJWT version was found. The advisory review is targeted, not a comprehensive supply-chain certification.

## Verification

Protected validation passed against source candidate SHA-256 `e5289d7755346650853375609bd71b7b85fb7ecfe83e7fbfeed164af61f31f3b`. Full and independent-service reports have the same 86 runtime/test/CLI manifest entries. Final documentation packaging is checked separately for runtime equivalence. The private evidence tree `docs/validation/v0.7.0-isolation/` remains local and is deliberately excluded from the GitHub ZIP; no operational key, account or recovery material is published.

| Verification | Observed result |
| --- | --- |
| Backend | 131 tests passed; 91.99% application line coverage. Includes concurrent single-use code consumption, disabled-account denial, CSRF/fresh-factor/recent-auth gates, replacement/password recovery, bootstrap refusal, enrollment interruption and injected disk-flush failure. |
| Real browser | 77 checks passed across 20 screens, including actual enrollment, code generation/display clearing, recovery sign-in, independent approvals and employer payroll boundaries. |
| HTTPS identity | 13 synthetic cases passed, including PKCE, state/nonce, signature/audience/expiry, verified/provisioned identity, key rotation, MFA and lifecycle denial. |
| Independent local services | Nine checks passed with Dex 2.46.0, Headscale 0.29.4, two Tailscale 1.104.1 userspace peers and TLS WsgiDAV 4.3.5. These are disposable independent local services, not a second physical host or commercial tenant. |
| HTTPS/recovery | TLS/proxy/Origin checks passed. Normal login/read/write stayed available during 100 unfinished header and 100 unfinished body connections; unfinished inputs expired. Encrypted recovery preserved payroll provenance, revisions, salaries and audit while rejecting old sessions and MFA replay. |
| Larger audit recovery | 200,005 fictional events; 49,721,344-byte database. Full streaming verification took about 1.97 seconds in this run; encrypted restore matched the retained anchor. This is not enterprise load certification. |
| Public packaging | Archive integrity, manifest, private workspace/log exclusions, home-path exclusions and byte-for-byte runtime checks passed. SHA-pinned CI is supplied; it has not run on GitHub. |
| Test isolation | OS sandbox denied outside writes, protected reads and external connections. Sentinel and actual workspace fingerprints were unchanged by both suites. Temporary trees/services were removed. |
| Actual local upgrade | 18 checks passed after refreshing the loopback instance from 0.6.0/schema 8 to 0.7.0/schema 9. Existing records, key and setup token were preserved; zero employees remain; integrity, foreign keys, audit, authorization and fresh encrypted backup/restore passed. No administrator was created. |

The suite first exposed an asynchronous browser fixture click before the account view finished rendering; it was corrected to await the visible control and the suite passed again. A separately reproduced disk-flush fault left a partial secret file; that implementation was patched and the regression now passes. Coverage is aggregate. These results do not prove every host, authority or legal scenario.

## Remaining limits

| Area | Status and consequence |
| --- | --- |
| Full statutory payroll | US federal withholding/FICA and UK ordinary Class 1 NI are partial dated previews. Complete cumulative/state/provincial/other-country engines, retro/year-end processing and bank payments are unfinished. Independently reviewed external results remain required for dated payroll. |
| Government submissions | A restricted SSA annual EFW2 exporter and filing workpaper/evidence tracking exist. Live authority transport, schemas/business rules for other agencies and official acceptance are unfinished. No government credentials or reviewed employer data were available. |
| Enterprise controls | Fixed roles, employer payroll scopes, mandatory MFA/OIDC, lifecycle session revocation and local audit chains exist. General field/organization permission policies, SCIM/SAML/passkeys, independent audit custody, HA and platform/capacity certification remain unfinished. |
| Remote/cloud/identity | Independent disposable local WireGuard, Dex and HTTPS WebDAV can exercise transport and recovery. A second physical/network host, off-device storage and actual provider tenant are absent; those acceptance claims cannot be made. |
| Local instance | The existing unconfigured test workspace remains unconfigured. No personal email or account was collected. The software release and a future operator's installation are separate deliverables. |

The research does not support promising embedded law for every country. Workday's [country payroll guides](https://doc.workday.com/admin-guide/en-us/payroll/payroll-considerations/dwn1595352231356.html.html) distinguish country products and third-party payroll integrations. The SSA [EWR web-services page](https://www.ssa.gov/employer/EWRWS.htm) currently says new EWRWS integrators are not accepted; authorised BSO upload remains a separate route. HMRC's [XML developer guide](https://www.gov.uk/guidance/basic-guide-for-xml-software-developers) describes its test transaction engine and supplied developer credentials, and [PAYE recognition guidance](https://www.gov.uk/guidance/paye-recognition-for-payroll-software-developers) requires development/testing and an application for recognition. An HTTP client alone cannot supply reviewed payroll rules or agency acceptance.

GitHub publication of the open-source project is possible independently of these installation and statutory gates. Publish the public source ZIP, state the supported scope and keep real employee data outside the repository. [Publishing and installation instructions](GITHUB_RELEASE.md) explain the next operator steps.
