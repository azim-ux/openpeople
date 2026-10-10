# Offline installers — OpenPeople 0.8.2

These per-user installer ZIPs include Python 3.13.16, pinned application libraries and clean Core HR source. Users do not need Python, pip, Docker, an OpenPeople account or internet access to install or run the local application. Optional cloud backups and SSO still need their chosen providers. The ZIPs are install kits, not MSI/EXE setup wizards, notarized PKGs or Linux distribution packages.

## Pick your download

| Computer | Release asset | Run after extracting the entire ZIP |
| --- | --- | --- |
| Windows Intel/AMD 64-bit | `openpeople-0.8.2-windows-x64-installer.zip` | Double-click `Install.cmd` |
| Mac with Apple Silicon | `openpeople-0.8.2-macos-arm64-installer.zip` | Open `Install.command` |
| Linux Intel/AMD 64-bit with glibc 2.28+ | `openpeople-0.8.2-linux-x64-installer.zip` | Run `./install.sh` in a terminal |

Compare the ZIP's SHA-256 to the separately published `openpeople-0.8.2-SHA256SUMS.txt` before extraction. Do not run directly inside a ZIP viewer. If an extractor strips Unix executable permissions, restore them for the installer and bundled interpreter: `chmod u+x Install.command payload/runtime/bin/python3` (Mac), or `chmod u+x install.sh payload/runtime/bin/python3` (Linux). Choose the package matching your processor. Windows ARM, Linux ARM and Alpine/musl are not included in this release. Intel Macs are also excluded: current [cryptography releases removed macOS x86_64 support](https://cryptography.io/en/latest/changelog/#v49-0-0). This installer does not downgrade that dependency to restore Intel support.

The packages are unsigned and not notarized. Follow the platform's normal approval process for software from a publisher you trust; do not disable Gatekeeper, antivirus or execution policy. Managed computers may require IT approval. Native testing evidence is recorded separately: producing a package for another OS does not certify it on that OS.

## Install and start

The installer displays its destination and asks before proceeding. It uses dedicated locations:

- Windows: `%LOCALAPPDATA%\OpenPeople`.
- macOS: `~/Library/Application Support/OpenPeople`.
- Linux: `~/.local/share/OpenPeople`.

It installs only there, without administrator/root access, changing global Python, creating a service, adding firewall rules or configuring a VPN. Windows installation limits the folder's inherited permissions to the installing account and SYSTEM. Unix program/data directories use owner-only permissions. The default folders must be outside a synchronized live-data location; if necessary choose a dedicated private directory with `--root`.

Open the installed `Launch.cmd` (Windows) or `Launch.command` (Mac/Linux). On Mac the installed folder also contains `OpenPeople.app`, which opens the launch terminal; you may create an alias to it. Linux supplies `OpenPeople.desktop` in that folder, which you may add to your application menu using your desktop's normal method. Windows users may create a shortcut to `Launch.cmd`. The installer does not replace existing personal shortcuts.

The launcher starts Core HR on loopback and opens the browser after its HTTP endpoint is ready. Keep the terminal open while using the app; **Ctrl+C** stops it. Closing the browser alone does not stop the server. A port already in use causes an error instead of attaching this workspace to another application; use `--port 8001` if needed. Only one bundled launcher can hold a workspace at a time.

On first launch, the terminal shows the private setup-token file's location. Open that file locally, copy its token into the browser's setup form, and choose the organisation's administrator login and password. No default account or password is shipped. A local login such as `admin@openpeople.invalid` is allowed; no personal mailbox is required and no email is sent. Enroll MFA, keep recovery codes separately, and start with fictional records.

## Data, backups and updates

Employee records, encryption key and private backup configuration live in `data/` beneath the installation root. Program versions live in `versions/`. Deleting a downloaded ZIP does not remove installed records. Never publish an installed folder or synchronize its live database. Use disk encryption and scheduled encrypted recovery archives, with the passphrase held separately.

Stop the app before command-line maintenance. Use the installed interpreter and vendored libraries through `desktop.py --tool`, for example from the active version directory listed in `installation.json`:

```sh
./runtime/bin/python3 -I -B desktop.py --db /your/install-root/data/openpeople.db --tool backup configure --folder /your/synced-backups --interval 60 --retain 30
./runtime/bin/python3 -I -B desktop.py --db /your/install-root/data/openpeople.db --tool backup run
```

On Windows use `runtime\python.exe` and quote the full `--db` path. The wrapper supplies that installed database path to commands which need it; do not repeat `--db` after `--tool`. Passphrases are prompted privately. Supported tools are `backup`, `manage`, `setup`, and `acceptance`; use `--tool TOOL --help` for their options. Read [backup and team access](LOCAL_TEAM_AND_BACKUP.md) and [Core HR acceptance](CORE_HR_RELEASE.md).

To recover an installed workspace, restore and verify the downloaded archive into a new private folder first. With the app stopped, retain the old `data/` files separately and move the verified restored `workspace.db` and `workspace.key` into the installed `data/` directory as `openpeople.db` and `openpeople.key`. Do not copy old WAL/SHM, sessions, backup settings or pending credentials. Keep the files owner-only, verify fresh MFA login, regenerate recovery codes and configure/test a new backup destination. The [replacement-device drill](CORE_HR_RELEASE.md#replacement-device-recovery) checks the restored data before this final placement.

Before installing a newer version, stop the app and make/verify an encrypted backup. Running the new kit with the same installation root preserves `data/` and keeps earlier program versions. Same-version reinstall verifies files and refuses to overwrite a modified program. The application may migrate the schema on its next launch; rolling back a schema migration requires the pre-upgrade backup. The installer does not automatically copy data from an older source-only installation: use its encrypted backup and the documented restoration procedure in a new private workspace.

Run the installed `Uninstall.cmd` or `Uninstall.command` to remove managed launchers/programs. **Employee data is retained**, along with its ownership receipt, so reinstalling can reuse it. On Windows, the running uninstaller retains program versions and an inventory because Windows cannot reliably delete its own loaded runtime; after it exits you can remove the dedicated `versions/` folder manually, keeping `data/`. User-added files are not removed. A modified launcher, symbolic link, missing ownership marker or running workspace causes refusal rather than removal.

## Your own team server

Use one authoritative host. Configure and verify private HTTPS/VPN, individual accounts, MFA and independently recoverable backups before sharing it. The installed launcher supports `--no-browser --production --public-origin https://your-private-host`; the existing production startup checks still apply. Windows production ACL acceptance remains outside the supplied backend's POSIX production gates. No platform installer turns local testing into an approved enterprise deployment.

## Build and publish on GitHub

The builder uses digest-pinned [Python Build Standalone runtimes](https://github.com/astral-sh/python-build-standalone/releases/tag/20261009), includes their bundled notices, and verifies application wheel downloads against `uv.lock`. Dependencies are installed into the package using pip's [hash-checking and platform options](https://pip.pypa.io/en/stable/cli/pip_install/), without executing foreign-platform binaries.

```sh
.venv/bin/python scripts/package_release.py
.venv/bin/python scripts/package_public.py
.venv/bin/python scripts/package_installers.py
```

Publish the three `*-installer.zip` assets, `openpeople-0.8.2-SHA256SUMS.txt`, installer verification report and clean `openpeople-0.8.2-github.zip` from `release/`. Do not publish `installer-cache/`, temporary build directories, internal source archives or an installed workspace. The supplied installer workflow builds and tests the native package on Windows, macOS and Linux, then makes build artifacts available; it does not upload a release automatically. Hosted build and native acceptance results are available in [GitHub Actions](https://github.com/azim-ux/openpeople/actions). Check the run for the release commit before relying on its evidence. Follow [the publishing guide](GITHUB_RELEASE.md).
