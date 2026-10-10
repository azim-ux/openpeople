# Latest release: 0.8.0

See [the Core HR review](DEPLOYMENT_REVIEW_0.8.0.md): 140 backend tests (92.03% coverage), 26 Core HR and 77 broader browser checks, 13 HTTPS identity checks, nine fresh public-package production/TLS installation checks, 12 independent local service checks, large-audit recovery and nine local upgrade checks passed. Full and service suites cover the same 92 runtime/test/CLI entries. Private evidence is under `docs/validation/v0.8.0-isolation/`; public export excludes it. Actual physical off-device, second-network, host operation and employer acceptance remain separate requirements.

# Previous release: 0.7.0

See [the 0.7.0 review](DEPLOYMENT_REVIEW_0.7.0.md) for the current summary: 131 backend tests, 91.99% line coverage, 77 browser checks, 13 HTTPS identity cases, nine independent local service checks, large-audit encrypted recovery and 18 actual local-upgrade checks passed. Full and service reports use the same 86 runtime/test/CLI entries. Local private logs/evidence are under `docs/validation/v0.7.0-isolation/`; the clean GitHub export deliberately excludes them. Real second-host/off-device/tenant acceptance, complete jurisdiction payroll and official government transport remain unfinished. Final package proof is recorded beside the archives.

## Earlier 0.6.0 evidence

See [the 0.6.0 review](DEPLOYMENT_REVIEW_0.6.0.md), [full protected evidence](validation/v0.6.0-isolation/report.json), [independent-service evidence](validation/v0.6.0-isolation/report-services.json) and [coverage](validation/v0.6.0-isolation/backend-coverage.json). The release passed 123 backend tests, 91.90% backend line coverage, 71 browser checks, 13 synthetic HTTPS identity cases, slow-input and encrypted recovery checks, nine independent local service checks and recovery with 200,005 audit events. Tests used fictional data and disposable same-computer services. Actual second-device/NAT/external-provider/off-device recovery and complete jurisdiction payroll remain unverified/unimplemented as specified in the release report. Final package hash/runtime equivalence are recorded separately.

The original results below remain historical.

# Validation — OpenPeople 0.3.0

Validated on 9 October 2026 on macOS using Python 3.13.15, Node 26.7.0, Brave and an isolated official Caddy 2.11.7 binary. Tests used fictional records and disposable workspaces. See the [deployment review](DEPLOYMENT_REVIEW_0.3.0.md) for findings, readiness and unverified installation gates.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Backend regression suite | 76 passed; original 36-test baseline retained | [Test log](validation/v0.3.0/backend-tests.log) |
| Combined backend line coverage | 89.87%, 1,713 / 1,906 executable lines; 80% gate passed | [Coverage](validation/v0.3.0/backend-coverage.json) |
| Frontend logic | 20 routes, escaping, duplicate-save/refresh, teammate polling; eight follow-up checks passed | [Route evidence](validation/v0.3.0/frontend-checks.json), [follow-up evidence](validation/v0.3.0/frontend-followup.log) |
| Actual HTTPS integration | Trusted/untrusted TLS, Secure cookie, HSTS, spoofed forwarding, Origin and stale-edit checks passed | [HTTPS/recovery evidence](validation/v0.3.0/https-recovery.json) |
| Slow requests through Caddy | 100 slow headers, then 100 slow bodies; fresh login/read/write succeeded during both; unfinished requests expired | Same HTTPS evidence |
| Encrypted recovery | Stopped source server, removed its original DB path, copied encrypted archive to simulated download folder, restored fresh workspace, verified salary/audit/MFA and rejected old sessions | Same HTTPS evidence |
| Dependency advisories | No known vulnerabilities returned for the 11 pinned third-party dependencies | [Dependency audit](validation/v0.3.0/dependency-audit.json) |
| Browser acceptance | Staged approval, conflict/reload/save, benefit roster, overdue learning, missing-backup warning and country/currency payroll display checked | [Browser observations](validation/v0.3.0/browser-observations.json) |
| Extracted source package | Archive hashes/private-file exclusions passed; fresh fictional Japan setup and API/static startup passed using installed dependencies | [Package smoke evidence](validation/v0.3.0/release-smoke.json) |
| Protected local re-test | 76 backend tests, frontend and TLS/recovery passed under an OS sandbox; outside writes/protected reads/external connections rejected; live workspace unchanged; fixtures removed | [Testing safety](TESTING_SAFETY.md), [run evidence](validation/local-isolation/report.json) |

Backend checks use real HTTP/SQLite and Waitress, fault-injected storage operations, and an actual separate configure CLI process. They cover bootstrap protection; account enumeration behavior; account lifecycle/session invalidation; idle/absolute expiry; CSRF/Origin; malformed identifiers, Unicode and non-finite numbers; independent approvals; role scope; persistent account throttles; session revocation; policy/denial/export audits; migration preservation; async backup/write concurrency; configuration races; missing/replaced storage; retention and corrupt read-back; wrong-key/tampered archive rejection; interrupted-job recovery; employee conflicts; compensation and payroll proration; overnight/corrected attendance; leave allocation/amend/cancel; benefits and learning; currencies/timezones/workweeks/country holidays; and native-currency expense policies.

Identity-provider endpoints are mocked, with real generated RSA signatures and TOTP checks. The HTTPS probe uses a real local proxy and explicit temporary CA trust; it does not install a system CA. Recovery used a separate restored database/listener on this computer. A provider was simulated by copying archive bytes between isolated folders. No real VPN, second computer or cloud account was available.

Coverage is aggregate, not a claim that every branch was exercised. Backup coverage is 78.04%, recovery CLI 64.29%; the rest ranges from 82.95% to 100%. Parent tracing does not capture separately executed CLI lines. Fault injection does not reproduce every hardware/filesystem failure. This is a focused regression/security assessment, not independent penetration-test certification.

## Reproduce

```sh
.venv/bin/python tests/run_coverage.py
node tests/test_frontend.mjs
node tests/test_frontend_followup.mjs
node --check public/app.js
node --check public/team.js
uv --cache-dir /tmp/openpeople-uv-validation pip check --python .venv/bin/python
.venv/bin/python scripts/package_release.py
.venv/bin/python tests/probe_release.py
```

For the isolated TLS drill, obtain the official Caddy 2.11.7 macOS ARM64 binary, verify its published checksum and place it at `/tmp/openpeople-caddy-audit/caddy`, then run:

```sh
.venv/bin/python tests/probe_https_recovery.py
```

The tested release archive SHA-256 for that Caddy download was `cda3030e5d5b13eb9f0b6fb541037f633bddd958c070c5f561d7a5cccb581665`. Other OS/architecture downloads have different checksums; adjust the probe binary path after verifying the appropriate official artifact. The probe opens temporary loopback listeners, never the default employee database. `tests/browser_release_fixture.py` starts a fictional UI fixture at port 8012.

## Installation-specific checks remaining

Actual offsite VPN connectivity and trusted-browser TLS, provider upload/download, restoration on another computer, external OIDC, OS disk encryption/ACLs, service restart, Windows/Linux installation, large-workforce capacity, mobile-device behavior and country statutory payroll remain unverified. These requirements are described in the [local team/recovery guide](LOCAL_TEAM_AND_BACKUP.md) and [capability map](ROADMAP.md).
