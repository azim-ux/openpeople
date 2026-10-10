# Core HR installation and acceptance — 0.8.0

This release candidate supplies a deliberately limited product: one organisation using one authoritative server. Employees and managers access the shared server through its private HTTPS endpoint. Backups are recovery copies, not independent editable workspaces.

## Included product scope

People records, effective-dated compensation records, reporting relationships, deactivation, individual accounts, leave requests and independent approvals, reviewed leave budgets/holidays, attendance and correction review, initial onboarding checklists, workforce/leave/attendance exports, notifications, security auditing, passwords/MFA/recovery codes, session revocation and encrypted backups. Roles are employee, manager, HR and auditor. Audit access includes sensitive business change details and must be assigned deliberately.

The Core HR profile disables recruitment, goals, expenses, benefits, learning, payroll calculations/runs/statements, employer payroll groups and government filing workpapers. Navigation, quick actions, report choices and account roles follow this scope. The backend rejects disabled routes before idempotent replay; selecting a hidden URL cannot enable a module. Existing broader-module records are retained, not deleted. Keep payroll, benefit provision and government submissions in externally reviewed systems. Leave budgets and attendance records need employer policy review; they do not certify statutory entitlements or overtime.

The optional full profile remains a feature preview, not an enterprise approval. The profile is selected by the host process and cannot be changed through an HTTP request. Production startup defaults to Core HR; local direct `server.py` testing retains the full preview unless `--profile core-hr` is supplied. Desktop launch wrappers select Core HR.

## Install with fictional records first

Extract the clean public source ZIP into a new project folder. Install Python 3.12+ and the pinned dependencies. On macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/setup_workspace.py --db data/openpeople.db --country IN
.venv/bin/python server.py --db data/openpeople.db --profile core-hr
```

The installing operator privately chooses a password and proves authenticator enrollment. The default login `admin@openpeople.invalid` is a local identifier; no personal mailbox or email delivery is required. No credentials or employee records are shipped. On Windows use `.venv\Scripts\python.exe` and a private dedicated workspace; POSIX production permission checks do not certify Windows ACLs. Windows production acceptance is not supplied.

Open `http://127.0.0.1:8000` for local fictional-data acceptance. Generate recovery codes under My account and retain them securely outside the host. Provision each teammate separately. Before production, configure scheduled encrypted backups, verify host disk encryption and file access, and configure the reviewed [HTTPS/VPN setup](LOCAL_TEAM_AND_BACKUP.md). Keep the live database out of synced folders. No OS service, network route, DNS, trust store or sleep setting is installed automatically.

Once the proxy and backup exist, start the selected host using the technical production gates:

```sh
.venv/bin/python scripts/run_service.py --db data/openpeople.db \
  --profile core-hr --production --public-origin https://your-private-host
```

This refuses incomplete technical setup and reserves the Core HR API scope. It does not certify remote access, independent storage, policy legality or enterprise readiness. Test monitored automatic startup after reboot separately. A restored host must configure its own backup destination before production startup.

## Record actual installation and client acceptance

Create a dedicated owner-only evidence directory (`mkdir -m 700 acceptance-private`). Evidence contains paths, checks and private data fingerprints; keep it outside source control. Stop the selected application cleanly before offline checks:

```sh
.venv/bin/python scripts/accept_core_hr.py installation \
  --db data/openpeople.db --output acceptance-private/installation.json
```

The command uses immutable read-only SQLite, refuses a nonempty WAL and never migrates or repairs the database. It checks schema/integrity/audit, required MFA, active administrators, Core HR roles, absence of samples and private workspace files. Disk encryption, backup operation and runtime profile require their separate checks.

From the actual host and each teammate device, use separate output files:

```sh
.venv/bin/python scripts/accept_core_hr.py endpoint \
  --origin https://your-private-host --ca /path/to/trusted-ca.pem \
  --output acceptance-private/endpoint-from-teammate.json
```

Omit `--ca` for a normally trusted certificate. Verification cannot be disabled. The check proves TLS, security headers, initialized setup, Core HR profile and unauthenticated denial from that client. It does not determine whether the client is on a separate physical network.

Use two independently signed-in browsers with fictional employee/manager/HR accounts. Verify MFA enrollment, directory/salary visibility, account deactivation/session revocation, attendance corrections, leave approval and own-request denial, onboarding task ownership, shared refresh and rejection of a saved stale employee version. Verify that payroll and broader modules are unavailable. Accept the configured leave budgets and workweeks with the employer. Record device/network, application version, time and failures privately; do not put employee data or credentials in GitHub issues.

## Replacement-device recovery

For a repeatable drill, stop editing and stop the source application. Capture the reference and make the encrypted backup from the same frozen workspace. Later edits require a new reference/backup pair; the strict comparison intentionally fails when business records differ.

```sh
.venv/bin/python scripts/accept_core_hr.py reference \
  --db data/openpeople.db --output acceptance-private/reference.json
.venv/bin/python backup.py create --db data/openpeople.db --folder /your/backup-folder
```

Both commands avoid plaintext business-data output. Retain the reference, encrypted backup and passphrase independently. Confirm upload through the actual provider or verified WebDAV transfer. Retrieve the archive on another authorised computer while the original physical host is unavailable. Install the same release there, then run:

```sh
.venv/bin/python scripts/accept_core_hr.py recovery \
  --archive /downloaded/snapshot.opbackup --destination /new/private/recovered \
  --reference /independent/reference.json --max-seconds 300 \
  --output acceptance-private/recovery.json
```

The recovery password is prompted privately, never accepted in arguments. Existing destinations and evidence files are never overwritten. The check authenticates the archive, restores to a new private directory, checks business-data fingerprints and retained audit chains, and confirms sessions, OIDC state, pending authenticators, request replay and old recovery codes are absent. Failed comparisons retain the new restored workspace for investigation. Its timing includes restore/check work, not download, OS installation or service restart; record total outage time separately. The matched frozen reference proves that baseline was recovered, not that all later edits were backed up.

Start the restored workspace with `--profile core-hr`; check fresh MFA login and known fictional records, confirm old sessions fail, regenerate recovery codes, and configure/test new scheduled backups. Record measured data loss and total recovery time against the organisation's objectives.

## Release decision

The supplied tests use this computer, disposable services and fictional data. They cannot establish an actual second network, independently held backup or physical host-loss survival. Evidence keeps `production_approved` and `off_device_recovery_verified` false because code cannot attest physical custody. Successful technical checks are necessary evidence, not automatic approval.

Before real employee use, the organisation must accept remote access when needed, disk protection, independently recoverable backups, monitored startup/reboot/updates, restore objectives, intended capacity, HR/privacy policies and independent security review. Payroll and broader Workday-equivalent enterprise capabilities are outside this Core HR release. A source publication on GitHub does not host its Python application or database.
