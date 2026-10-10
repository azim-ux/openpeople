# Testing safely on this computer

The authorized test scope is OpenPeople and its fictional test fixtures. Personal documents, photos, email, browser profiles, cloud accounts, other applications, system settings and the actual employee workspace are outside the test scope.

## Enforced isolation

The macOS [test runner](../scripts/test_isolated.py) verifies and extracts the existing source release into a disposable `/private/tmp` directory. Test processes run under `sandbox-exec` with these restrictions:

- Writes are allowed only inside that run's temporary directory, plus discarded standard I/O to `/dev/null`. The live workspace, project source, personal files, system certificate stores and application settings are outside that write scope.
- Reads of the personal home directory are blocked, except the already installed Python environment/runtime needed to execute tests. The suite uses the extracted fictional workspace.
- Network binds and connections are limited to loopback. External cloud services and other computers are unavailable to the test processes.
- The runner performs negative controls before the software tests: a write/read attempt against a disposable protected sentinel and an external connection attempt must fail. It stops if these protections do not work; there is no unrestricted fallback.
- Execution time is bounded, test-only process groups are cleaned up, and temporary fixtures are removed afterward. No software, VPN, system certificate, service or cloud account is installed/configured.

The parent runner reads selected OpenPeople database/key/setup-file fingerprints before and after the run. It reports only whether they match; private bytes and key/token fingerprints are not published. Parent writes are limited to the owned temporary fixtures and project test evidence under `docs/validation/`. The historical 0.3.0 evidence remains in `local-isolation/`; new releases use their own versioned directory.

## Run and evidence

```sh
.venv/bin/python scripts/test_isolated.py
```

The command requires this computer's existing Python, Node, macOS sandbox tool and the previously verified portable Caddy binary. It selects the built source archive from the version in `pyproject.toml`; rebuilding that archive is a separate, explicit operation. It runs the archived backend coverage suite, frontend checks, a sandboxed empty-profile portable Chromium engine, a separately serving synthetic HTTPS identity provider, actual loopback TLS/encrypted recovery and a packaged smoke check. Ordinary non-sandboxed test commands do not inherit these restrictions.

The installed Chrome runtime was blocked in 0.3.1 because it attempted operations outside the permitted tree. Release 0.3.2 uses Google's portable Chrome for Testing headless shell in a task-owned temporary directory, with an empty profile, mock keychain and external network blocked. No sandbox permissions were widened. The browser ZIP came from an official HTTPS download; integrity and local hashes are recorded in [browser provenance](validation/v0.3.2-isolation/browser-provenance.json). It is a test tool, not shipped or installed into the user's applications.

To reproduce with the portable engine still available on this computer:

```sh
OPENPEOPLE_BROWSER_BINARY=/private/tmp/openpeople-readiness-tools-1iltbiuv/chrome-headless-shell-mac-arm64/chrome-headless-shell .venv/bin/python scripts/test_isolated.py
```

The temporary tool directory may be cleared by the OS; then supply a verified portable engine using the environment variable. Do not point at a personal profile or relax protection. `--browser-only`, `--identity-only` and `--followup-only` create separate partial reports, which do not substitute for the complete backend run.

## Verified results — 9 October 2026

The current **0.6.0** full run passed **123 backend tests (91.90% coverage), 71 browser checks and 13 synthetic HTTPS identity cases**, frontend/slow-client/recovery checks and an encrypted restore with **200,005 audit events**. Nine additional acceptance checks passed against independent local Dex, Headscale/Tailscale userspace peers and TLS WebDAV. Protected writes/reads/external connections were denied; sentinel/live workspace fingerprints matched and temporary trees were removed. See [the current review](DEPLOYMENT_REVIEW_0.6.0.md), [full evidence](validation/v0.6.0-isolation/report.json) and [independent-service evidence](validation/v0.6.0-isolation/report-services.json). All services were disposable, used fictional accounts and remained on this computer. No physical-loss or real external-provider acceptance is claimed.


The historical **0.3.2** full run passed **87 backend tests**, with **90.49%** application-backend coverage, frontend logic, **45 actual browser checks** across 20 screens, **13 HTTPS identity checks**, actual TLS/slow-input collaboration checks and encrypted simulated loss recovery. External payroll components/provenance, revisions and editor exclusions survived restoration. Protected reads/outside writes/external connections were denied; live workspace fingerprints matched; temporary fixtures were removed. See [historical evidence](validation/v0.3.2-isolation/report.json) and [the report](DEPLOYMENT_REVIEW_0.3.2.md). No actual cloud account, VPN device, personal browser profile or live employee data was used.

The 0.3.1 run remains historical: 81 backend tests, 90.11% coverage, frontend logic, TLS and encrypted recovery passed; the installed browser attempt was blocked then.

The following results describe the historical 0.3.0 run.

The protected run passed **76 backend tests in 56.635 seconds**, with **89.87% backend line coverage**, frontend checks for 20 routes and the follow-up frontend checks. Actual loopback HTTPS handled 100 slow headers and 100 slow bodies while fresh logins, reads and saves succeeded. Encrypted recovery preserved salary/audit/MFA and rejected old sessions. External provider and VPN portions remain simulations.

The negative file/network controls passed, the protected sentinel remained unchanged, the live HR database/key/setup fingerprints matched, and the run's temporary directories were removed. The existing local app listener remained running. No browser interaction or personal-file inventory was needed.

Two initial instrumented runs recorded HTTP timeouts: the coverage tool traced third-party server code because its ignore cache compared module basenames, including two unrelated `server.py` files. Coverage now uses an exact application-file allowlist. Five consecutive focused traced checks and the complete suite then passed under the same protections. Initial evidence is retained in [the first run](validation/local-isolation/initial-tracing-failure.log) and [the remaining basename collision](validation/local-isolation/basename-collision-failure.log); the corrected run is [here](validation/local-isolation/backend-tests.log).

The machine-readable [run report](validation/local-isolation/report.json) and accompanying logs record actual outcomes, cleanup and the live-workspace comparison. A local result does not certify an actual cloud provider, offsite VPN, second-device recovery or national payroll rules.

The restrictions protect against unintended test file/network operations. They do not certify the computer's entire OS, unrelated running applications or the absence of all possible vulnerabilities in the macOS sandbox itself.
