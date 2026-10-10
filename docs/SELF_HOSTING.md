# Download and self-host OpenPeople

OpenPeople runs on hardware you control. GitHub supplies the source download; your computer runs the browser interface, Python application and database. No OpenPeople account, publisher email registration, paid application hosting or Docker installation is needed. This release is source software, so each host needs Python 3.12+ and the pinned dependencies. For a bundled Python runtime and automatic per-user installation, use the [offline installer kits](INSTALLERS.md) instead.

## Choose a host

| Use | Where OpenPeople runs | How people connect |
| --- | --- | --- |
| One person on a laptop/desktop | That person's computer | Browser at `http://127.0.0.1:8000` |
| A small team or organisation | One computer or server maintained by the organisation | Individual accounts through its private HTTPS/VPN endpoint |

The shared host must remain on and reachable while the team uses it. Teammate computers need a browser and the chosen VPN client; they do not run another writable database. There is one authoritative database per installation. Encrypted backups can go to a folder synchronized by the operator's own cloud client. Backup synchronization does not merge independent editable copies.

## Download and install

Download `openpeople-0.8.1-github.zip` from the project's GitHub release, or download its repository source ZIP. Extract into a dedicated folder outside cloud-synced folders. Open a terminal in the extracted folder containing `README.md`, `requirements.txt` and `server.py`. The clean package contains no employee records or credentials.

Install Python 3.12 or newer through your normal platform installation method. Installation needs internet access to fetch dependencies. Afterward the local application can run offline; optional SSO and cloud uploads need access to their providers.

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/setup_workspace.py --db data/openpeople.db --country IN
.venv/bin/python server.py --profile core-hr --db data/openpeople.db
```

Windows **Command Prompt** (the `%LOCALAPPDATA%` syntax below is for Command Prompt):

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\setup_workspace.py --db "%LOCALAPPDATA%\OpenPeople\openpeople.db" --country IN
.venv\Scripts\python.exe server.py --profile core-hr --db "%LOCALAPPDATA%\OpenPeople\openpeople.db"
```

Replace `IN` with your organisation's two-letter country code. This chooses an operating profile, not a statutory payroll engine. Setup prompts privately for a password and authenticator enrollment; no default password is supplied. The default login is `admin@openpeople.invalid`, a local identifier which sends no email. You may choose another identifier and display name using `--login` and `--name`. Setup only accepts an empty workspace; an existing organisation uses its existing administrator.

Open **http://127.0.0.1:8000** and sign in with the chosen login, password and authenticator code. Under **My account**, generate recovery codes and keep them separately from the host. Add fictional employee records first and check the workflows in [Core HR acceptance](CORE_HR_RELEASE.md).

For the alternative browser setup, skip `setup_workspace.py` and start the server. It prints the location of a private setup-token file. Read that file locally and enter the token on the setup screen, then create your account and enroll MFA. Never publish the token or credentials.

## Start again and keep your data

Stop the server with **Ctrl+C** in its terminal. Starting it again with the same database path preserves records. After dependencies are installed:

- macOS: double-click `start.command`. If your extractor stripped executable permission, run `chmod u+x start.command` first.
- Linux: run `./start.command`, or the Python startup command above.
- Windows: double-click `start.bat`; it uses `%LOCALAPPDATA%\OpenPeople\openpeople.db`.

The macOS/Linux launchers use `data/openpeople.db` relative to the project folder. For a custom workspace, pass `--db /your/private/workspace.db` and use that exact path for setup, startup, backup and maintenance. Keep the live workspace and its key together, outside cloud-synced folders. Use host disk encryption and private file access. Do not upload the installed workspace, `.venv`, tokens, keys or recovery material to GitHub.

## Optional encrypted cloud backups

Choose a folder uploaded by your own installed cloud-sync client. Replace the example folder with your actual destination. On macOS/Linux:

```sh
.venv/bin/python backup.py configure --db data/openpeople.db --folder "/your/synced/OpenPeople-backups" --interval 60 --retain 30
.venv/bin/python backup.py run --db data/openpeople.db
```

On Windows Command Prompt:

```bat
.venv\Scripts\python.exe backup.py configure --db "%LOCALAPPDATA%\OpenPeople\openpeople.db" --folder "C:\your-synced-folder\OpenPeople-backups" --interval 60 --retain 30
.venv\Scripts\python.exe backup.py run --db "%LOCALAPPDATA%\OpenPeople\openpeople.db"
```

Keep the privately prompted recovery passphrase separately from the host. The scheduler runs while OpenPeople is running. Only encrypted `.opbackup` archives belong in the synchronized destination; never sync the live database. Confirm upload and download with the actual provider and practice [replacement-device recovery](CORE_HR_RELEASE.md#replacement-device-recovery). A backup kept only on the same disk cannot protect against loss of that disk. Cloud storage limits and costs depend on the operator's provider.

## Share with a team on your own server

First follow [private VPN, HTTPS and backups](LOCAL_TEAM_AND_BACKUP.md). Keep the application bound to loopback behind the HTTPS proxy and provision individual accounts with suitable roles and MFA. Do not expose the initial local HTTP command directly to the internet.

After configuring and verifying the production prerequisites on a suitable host:

```sh
.venv/bin/python scripts/run_service.py --db data/openpeople.db --profile core-hr --production --public-origin https://your-private-host
```

Replace the example origin with the actual HTTPS endpoint. Use the supplied [installation, endpoint and recovery checks](CORE_HR_RELEASE.md) from the real host and teammate devices. Configure and verify operating-system startup after reboot, backup monitoring and updates using [operations](OPERATIONS.md). No OS service or network settings are installed by the launchers. The Windows local testing path is supplied; Windows production ACL acceptance and Linux/Windows deployment certification have not been completed.

## Update an existing installation

Read the new release's migration notes. Stop the application, create and verify an encrypted backup, and retain the previous release for rollback. Extract the new release into a separate folder, install its pinned dependencies, and explicitly select the existing private database using `--db`. Keep its database, key and private configuration together. Do not replace those files with download contents or run two application versions against the workspace. Recheck startup, login, backups and recovery after the upgrade. Schema upgrades may require restoring the pre-upgrade backup to roll back.

## Scope and acceptance

The default documented install exposes the Core HR release candidate: people, reporting relationships, leave, attendance, onboarding, core reports, security and backups. Payroll and broader unfinished modules are disabled. The supplied tests used fictional data on macOS; actual device/network, independently held backup, host protection and organisation policy acceptance remain the installing operator's responsibility. Review [the release evidence](DEPLOYMENT_REVIEW_0.8.0.md) before using real employee data. Publishing source on GitHub does not make an installation production-approved.
