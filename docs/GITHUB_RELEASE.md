# Build and publish the software

The current package contains the [Core HR release candidate and acceptance commands](CORE_HR_RELEASE.md), plus [offline installers for Windows, macOS and Linux](INSTALLERS.md). Each organisation must complete actual installation acceptance before entering real employee records.

Building OpenPeople does not require your personal email or a configured HR administrator. Each installing organisation creates its own account. Source packages contain no accounts, passwords, authenticator secrets, employee database or cloud credentials.

Build both the internal verification archive and the public GitHub archive:

```sh
.venv/bin/python scripts/package_release.py
.venv/bin/python scripts/package_public.py
.venv/bin/python tests/probe_public_release.py
```

Use `release/openpeople-0.8.2-github.zip` for publication. Extract it into a new empty folder and publish the contents of `openpeople-0.8.2-github/`. Do not publish the original working directory: it can contain a private `data/` workspace and local service files. The public export excludes those directories and private test logs rather than relying only on `.gitignore`. It includes MIT licensing, original source, pinned dependencies, tests, public documentation, a file-hash manifest and GitHub CI. The public repository is [azim-ux/openpeople](https://github.com/azim-ux/openpeople). Only verified clean exports and distribution assets belong there; never upload a live workspace. Each release remains a Core HR evaluation candidate until installation-specific acceptance is complete.

Distribute the same clean ZIP as the downloadable release asset. The repository README links to [the self-hosting guide](SELF_HOSTING.md) so users can install the source and dependencies on their own computer or server. The source export preserves executable permission on `start.command` and gives other files ordinary read/write source permissions. It does not include Python, an installed virtual environment or a preconfigured administrator. Users do not need to send the publisher their email, password or employee data. GitHub distributes the code; each operator runs and maintains their own application and database.

The workflow uses `push`, `pull_request` and manual dispatch, read-only repository permissions, no deployment secrets and SHA-pinned official actions. It runs backend coverage with an 80% minimum, frontend regressions and private-file/package checks. The supplied CI targets macOS and Python 3.13; it does not certify Windows/Linux, browser or external-provider acceptance. Browser and independent-service drills are documented in [testing safety](TESTING_SAFETY.md). GitHub-hosted execution becomes evidence only after a repository actually runs the workflow. Review dependency update pull requests before merging them.

## Installation by a future operator

Install Python 3.12+ and the pinned application dependencies in a virtual environment. Run the local setup command from an interactive terminal, with the application stopped:

```sh
.venv/bin/python scripts/setup_workspace.py --db data/openpeople.db --country IN
```

The default local login is `admin@openpeople.invalid`; it is an identifier, not a mailbox, and no email is sent. Operators may choose another email-format identifier with `--login` and a display name with `--name`. The country sets the administrator's operating profile; it does not install statutory tax rules. This creates an administrator only in an empty workspace.

For Windows, use `.venv\Scripts\python.exe` and `--db "%LOCALAPPDATA%\OpenPeople\openpeople.db"`, consistently for setup, startup, backups and maintenance. See the platform-specific commands in the self-hosting guide.

The command privately prompts for a new password and confirmation, creates a temporary private authenticator enrollment file, and asks for a current authenticator code. It removes that file after completion or interruption. It stores only a password hash and an encrypted authenticator secret, requires MFA, and creates no samples or logged-in sessions. Never share credentials in an issue, chat or command line. If enrollment fails, no account is inserted; the empty private database/key/setup-token can remain for a retry. A pre-existing workspace requires its existing administrator or the local recovery tool.

Sign in with the chosen identifier, password and a new authenticator code. Under **My account**, generate recovery codes using a fresh authenticator proof. Copy them into private storage outside the host. Codes are shown once; each requires the account password or organization sign-in and works once. Generating a new set invalidates the old set. Password changes and restored archives invalidate codes. Generate fresh codes after restoring a workspace.

Then configure scheduled encrypted backups with privately prompted passphrases, HTTPS and remote access according to [the operations guide](OPERATIONS.md) and [local team setup](LOCAL_TEAM_AND_BACKUP.md). First-run account setup is not a substitute for these deployment steps. `--production` enforces the documented technical gates; it does not certify payroll, official filing or off-device recovery.

See [the release report](DEPLOYMENT_REVIEW_0.8.0.md) and [capability map](ROADMAP.md) before using real employee data. Complete government submission and universal statutory payroll are not supplied by this release. This computer has no actual external cloud storage or identity tenant configured.
