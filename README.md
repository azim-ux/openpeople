# OpenPeople 0.8.1

An MIT-licensed, self-hosted HR workspace. Download the source from GitHub and run it on your own laptop, desktop or server. The browser interface, Python backend and database run on the host you choose; no OpenPeople hosting account or paid application server is required. It provides Workday-inspired navigation with original branding and code, shared team access, authenticator MFA, optional organization SSO, and encrypted recovery backups. OpenPeople is not affiliated with Workday or Kotak.

Use it on one computer at **http://127.0.0.1:8000**, or let a team connect to one shared host over private HTTPS/VPN. Each installation keeps its own data and creates its own administrator. Start with the [download and self-hosting guide](docs/SELF_HOSTING.md).

**Install without Python setup:** download the [offline installer ZIP for Windows, macOS or Linux](docs/INSTALLERS.md), extract it and run its installer. Python and application libraries are included. Use the source-install commands below if you prefer to maintain your own Python environment.

The **Core HR release candidate** provides people records, reporting relationships, leave, attendance, onboarding checklists, core reports, account security and encrypted backups. Its backend and interface disable payroll and the broader unfinished modules. See [Core HR installation and acceptance](docs/CORE_HR_RELEASE.md) and [the 0.8.0 report](docs/DEPLOYMENT_REVIEW_0.8.0.md). The full feature preview remains available separately; it is not an enterprise production release or a Workday-equivalent compliance claim.
You do not need to supply a personal email to build or publish this software. The [GitHub release guide](docs/GITHUB_RELEASE.md) describes a clean public source archive and private first-run setup for each future organisation. The optional terminal installer uses `admin@openpeople.invalid` as a local login identifier and verifies actual authenticator enrollment; no email is sent and no default credentials are shipped.

Protected tests use fictional records and disposable workspaces/services. The [latest review](docs/DEPLOYMENT_REVIEW_0.8.0.md) records backend, real-browser, packaged production launch, TLS, VPN and encrypted recovery evidence. No second device or actual external cloud account is available, so those installation acceptance checks remain pending.
## Download and run on your own computer

Download `openpeople-0.8.1-github.zip` from the project's GitHub release, or download the repository's source ZIP. Extract into a dedicated folder outside cloud-synced folders, then open a terminal in the folder containing this README. This is a source distribution: install Python 3.12 or newer first, then create a private virtual environment and install dependencies.

On macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py --profile core-hr
```

On Windows:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe server.py --profile core-hr --db "%LOCALAPPDATA%\OpenPeople\openpeople.db"
```

Open **http://127.0.0.1:8000**. The server prints the path to a private setup-token file, normally `data/openpeople.setup-token` on macOS/Linux, or `%LOCALAPPDATA%\OpenPeople\openpeople.setup-token` on Windows. Open that file locally and enter the token in the setup screen, then create your HR account. Setup cannot be claimed without this token and closes after the first administrator is created. There is no default password. For password and MFA enrollment together, follow the terminal setup procedure in the [self-hosting guide](docs/SELF_HOSTING.md).

After dependencies are installed, macOS users can double-click `start.command`; Windows users can use `start.bat`. Both select Core HR. If an unzip tool removes the macOS executable permission, run `chmod u+x start.command` first. On Linux run `./start.command` or the Python command above. The Windows launcher uses the Local AppData workspace shown above.

Alternatively, with uv installed, use `uv sync --locked` and `uv run --locked server.py --profile core-hr` (on Windows also supply `--db "%LOCALAPPDATA%\OpenPeople\openpeople.db"`). Installation downloads open-source dependencies; running the local application does not need an internet connection. Optional SSO needs access to its identity provider.

Keep the project and live database outside folders synchronized by cloud storage. On Windows, Desktop and Documents may already be synchronized by OneDrive; the Windows launcher uses Local AppData for that reason. Stop the server with Ctrl+C. Restarting preserves records.

## Bring your team together and protect backups

Use **one shared local server** as the authoritative workspace. Teammates connect through a private VPN and HTTPS; their browsers refresh changed records automatically while the page is idle. Each teammate needs an individual account and appropriate role. This release does not merge independent offline databases.

The local server uses Waitress and binds to loopback. The [remote-team guide](docs/LOCAL_TEAM_AND_BACKUP.md) includes WireGuard and Caddy configuration using your own computer, with no hosted application server required. That computer must stay on and reachable. Internet, electricity, storage quotas, and any relay you need remain dependent on your existing services.

Configure encrypted backups to a folder your chosen cloud client synchronizes:

```sh
.venv/bin/python backup.py configure --db data/openpeople.db --folder "/path/to/your/synced/OpenPeople-backups" --interval 60 --retain 30
.venv/bin/python backup.py run --db data/openpeople.db
```

On Windows use `.venv\Scripts\python.exe` and `--db "%LOCALAPPDATA%\OpenPeople\openpeople.db"` for every backup command, as shown in the [self-hosting guide](docs/SELF_HOSTING.md).

The command prompts privately for a recovery passphrase of at least 16 characters. Keep it separately from the computer. Backups use authenticated encryption, include the database and its protected-field key, and remove reusable sessions. The server checks the schedule every 30 seconds while it runs. The cloud client uploads encrypted `.opbackup` files; OpenPeople does not verify provider upload. Never synchronize the live SQLite database between computers.

Restore into a new folder:

```sh
.venv/bin/python backup.py restore "/path/to/file.opbackup" --destination "/path/to/recovered-workspace"
.venv/bin/python server.py --profile core-hr --db "/path/to/recovered-workspace/workspace.db"
```

Practice a restore from an off-device copy before relying on backups. Without the recovery passphrase, a lost computer's encrypted backups cannot be recovered. Live SQLite data needs operating-system full-disk encryption; see [SECURITY.md](SECURITY.md).

## Full feature preview workflows

The following table describes the broader preview (`--profile full`). Only the [Core HR scope](docs/CORE_HR_RELEASE.md) is exposed by the Core HR profile. `--production` defaults to Core HR and requires the documented technical setup.

| Area | Included behavior |
| --- | --- |
| People and organization | Version-checked employee edits, identity/date corrections, country/currency/timezone/workweek, deactivation, direct managers, roles and CSV export |
| Time and expenses | Leave budgets, accrual, holidays, half days, amendments/cancellation, expense limits/evidence/reconciliation, independent review, overnight/split attendance and corrections |
| Hiring and onboarding | Candidate pipeline, stage changes, initial checklists, completion tracking |
| Performance | Goals, due dates and progress |
| Benefits and learning | Enrollment windows/withdrawal and HR roster; overdue courses, reminders, reassignment and employee completion |
| Payroll | Effective salary and joining/exit/unpaid-leave proration, separate currency totals, monthly and employer-group dated snapshots, reviewed regular/bonus/adjustment periods, manual deductions or reviewed external results with components/provenance, independent finalization, immutable finalized statements, own-statement printing |
| Team communication | In-app notifications and polling for committed updates |
| Access | HR, employee, manager, recruiter, payroll and auditor roles; employer-restricted payroll access, local passwords, account/IP throttles, human-inactivity expiry, session inventory/revoke, TOTP MFA and optional OIDC SSO |
| Audit and recovery | Before/after business changes, authentication events, append-only local audit chains/retained-anchor checking, local account recovery, paginated audit/report exports, encrypted asynchronous/scheduled backups, destination health, retention and verified restore |

Payroll includes effective salary history, calendar-day joining/exit proration and approved unpaid leave. Dated previews cover partial US 2026 federal withholding/FICA and UK 2026/27 ordinary Class 1 National Insurance; neither is a complete or independently certified country payroll engine. They do not automatically populate pay runs. A separate restricted SSA annual wage-file export needs reviewed annual inputs and authorized AccuWage/BSO acceptance. Government transmission, payments and banking integrations remain unavailable. Choose from 251 offline country/region options, operating currencies and IANA work timezones; zero-, two- and three-decimal currencies remain separate in payroll. Country options do not imply statutory payroll support. Pay runs can record externally calculated earnings, deductions and employer contributions with a reviewed provider reference; the app validates format/totals and preserves provenance, while complete tax calculation, filing and payment remain external. Benefits record enrollment/withdrawal within configured windows; provider coverage and payroll deductions remain external. HR can configure leave budgets/accrual, reviewed employee allocations/carryover, workweeks and country/company holidays. Attendance supports split/overnight sessions and independently approved, version-checked corrections. The app remains one organization with fixed roles and approval templates.

## Accounts and permissions

HR can add accounts and assign roles in People. Employees see the shared basic directory and their own private records. Managers also see direct reports' leave, attendance, onboarding, goals and expenses. Recruiters handle candidates. Payroll reviewers have workforce access unless HR restricts them to selected employers under Organization; restrictions use original employer snapshots for historical pay. Saving a restriction revokes their sessions. Auditors can see business change details and security events, including sensitive values in authorized audit records. HR has workforce administration, policies and backup controls. Review legacy payroll accounts during upgrade and use the least privileged role each person needs.

HR cannot approve its own leave or expenses. Payroll deductions must be edited by a colleague; finalization requires an HR/payroll reviewer who neither created nor edited the run, using its current reviewed version. If both colleagues edit a draft, a third reviewer is needed. For two-stage requests, an assigned active manager reviews first and another HR reviewer finishes; requests without an available manager use independent HR review.

For local recovery after verifying the person's identity:

```sh
.venv/bin/python manage.py employee@example.org
.venv/bin/python manage.py employee@example.org --disable-mfa
```

Both commands prompt for a new password and revoke the account's sessions. Add `--db /path/to/workspace.db` for another database. Resetting an authenticator leaves the workspace MFA requirement in place, so the user must enroll again.

## Validation and contribution

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/run_coverage.py
node tests/test_frontend.mjs
node --check public/app.js
node --check public/team.js
```

Read the [validation record](docs/VALIDATION.md), [patch evidence](docs/PATCH_VALIDATION.md), [security scope](SECURITY.md) and [contributing guide](CONTRIBUTING.md). Tests use isolated fictional workspaces. The [macOS protected test runner](docs/TESTING_SAFETY.md) blocks test writes outside disposable storage and external network connections. Windows/Linux deployment and a real external identity/cloud provider need installation-specific verification.

## Architecture and license

`public/` is the responsive, same-origin interface. `server.py` handles API validation and sessions; `workspace.py` contains migrations, role rules and team workflows; `identity.py` implements MFA/OIDC; `serving.py` adapts the API to Waitress; `backup.py` encrypts SQLite online snapshots and restores them. A single SQLite database, local key and private backup configuration belong to the host. Only an explicit public asset allowlist is served. No analytics or remote fonts are used.

[MIT license](LICENSE). Workday is a trademark of its owner.

## New in 0.6.0

[Employer pay groups and dated periods](docs/PAY_PERIODS.md) support weekly, fortnightly, semimonthly and monthly regular runs, plus reviewed bonuses/adjustments. Membership edits use worker/group versions; overlapping regular runs are rejected. Every dated statement requires a period-bound externally reviewed result before independent finalization.

[Production launch controls and operations](docs/OPERATIONS.md) add an explicit `--production` profile, private readiness checks, minimal liveness, a read-only monitor and bounded crash supervision. The profile refuses unsafe technical configuration; it does not certify legal or off-device acceptance. Full stopped-workspace audit verification and restore now stream histories beyond the interactive 200,000-row budget. The 256-MB backup format limit remains.

Employer payroll restrictions, immutable history, partial US/UK statutory previews, the restricted SSA annual-file adapter and independent local identity/VPN/WebDAV acceptance remain available. Complete country payroll, online government submissions and actual off-device deployment acceptance still require further work.
