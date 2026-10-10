# Installer release review — 0.8.1

Date: 2026-10-10. Distribution: offline per-user ZIP installer kits for Windows x64, macOS Apple Silicon and Linux x64/glibc 2.28+. They contain a verified Python runtime, pinned libraries and clean application source. Installation does not need global Python or internet access. These are terminal installers, not native signed setup wizards.

## Installation protections

Payload checks reject altered/missing/unlisted files, wrong platforms, traversal, symbolic links and Windows junctions. New installations refuse unrelated nonempty folders. Program versions, private records and recovery configuration are separate. A workspace lock prevents bundled launchers, updates or uninstall from running concurrently. Same-version reinstall verifies existing program bytes. Upgrades keep old program versions and restore previous launchers if publication fails. Unix directories/files are owner-only; Windows uses current-user/SYSTEM ACLs and checks for unexpected explicit grants.

Uninstall preserves employee data, the encryption key, backup configuration and user-added files. Windows retains its loaded program versions/inventory for later manual cleanup; it cannot reliably delete its own interpreter. All installers are unsigned and not notarized, and install no global services, startup tasks, firewall rules, VPNs, cloud accounts or preconfigured HR credentials.

## Verification evidence

- The scoped application suite passed 154 integration/security tests at 92% combined backend line coverage, frontend regressions, 26 Core HR browser checks, 77 broader-preview browser checks, synthetic verified-HTTPS identity and fresh public-package production/TLS/recovery checks. The small server ready callback supports opening a browser only after the host has bound its endpoint.
- Native macOS offline installation passed nine checks: actual installer entry script, bundled runtime/libraries, cryptography/SQLite/MFA/encrypted backup, installed Core HR startup, running-workspace update refusal, MFA denial, data-preserving reinstall, database-selected maintenance, data-preserving uninstall and private workspace permissions. These related behaviors are grouped into the nine reported checks.
- Installer safety regressions cover install/update/reinstall/uninstall, partial-copy and launcher-publication failure, preserved data/personal sentinels, changed launchers, traversal/unlisted files, wrong platform, linked payload/destination and tampered inventory. The final regression count and exact installer hashes are in the companion release verification JSON.
- Every platform package is checked for ZIP/member integrity, SHA-256 payload hashes, plain-file modes, current clean application source, all 11 pinned dependency versions, included runtime license notices and exclusion of HR databases/keys/tokens/backups. Foreign binaries are not executed by this check.

Local native/application tests run inside mandatory macOS sandbox-exec. Test children can write only to disposable temporary storage; personal-home reads and external network are blocked. Protection sentinels, live-workspace fingerprints and temporary-folder removal are checked. Browser tests use disposable profiles. Installer construction downloads only public pinned runtimes and hash-locked wheels into project-owned caches. No personal directory, operating-system security setting, trust store, browser profile or live employee workspace is changed by these tests.

The installer companion `release/openpeople-0.8.1-installer-verification.json` records exact current ZIP digests and separates build/inspection evidence from native execution. `docs/validation/v0.8.1-isolation/` retains private full-suite and native-installation logs. Clean public source excludes these logs. The local preview server was not upgraded by installer testing.

## Remaining checks and limits

Windows and Linux artifacts are built and inspected, but their native execution remains pending. The read-only SHA-pinned installer workflow builds/tests them on actual GitHub Windows/Linux runners and tests the Mac package in a disposable sandbox. Its first hosted run and GitHub publication remain pending; no remote repository was supplied. Verify installation through each OS's normal download/quarantine/antivirus approval flow on a clean user computer before promoting these installer candidates.

Intel Macs are excluded because current [cryptography versions removed macOS x86_64 support](https://cryptography.io/en/latest/changelog/#v49-0-0); the installer retains cryptography 50.0.2. Windows/Linux ARM and Alpine/musl packages are not supplied. GUI shortcut activation, automatic startup/reboot and each target's OS protection policy need platform-specific acceptance. The Mac application wrapper opens a terminal; it is not a native HR UI.

Packaging does not change the [Core HR production acceptance requirements](CORE_HR_RELEASE.md). Actual host protection, remotely connected devices, independently held recovery copies and organisation privacy/HR acceptance are still required before real employee deployment. The backend's production permission gates remain POSIX-specific; Windows local installation does not imply Windows enterprise production certification. Statutory payroll and broad enterprise parity remain outside the Core HR scope.

Read [installation and publishing instructions](INSTALLERS.md) for the exact user steps and release assets.
