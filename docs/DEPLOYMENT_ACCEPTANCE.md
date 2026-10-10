# Deployment acceptance on the actual installation

Release 0.8.0 supplies a scoped Core HR product and private acceptance commands. Follow [the Core HR procedure](CORE_HR_RELEASE.md) for the first small-team release; the broader checks below remain relevant to each actual installation.

Use this procedure after accepting the tested release with fictional records. Keep the live database outside cloud-synced folders. Name the operator, define acceptable recovery time/data loss, and retain a recovery passphrase outside the host. These checks do not create a production approval automatically.

The earlier release 0.6.0 repeated acceptance against independent local Dex, Headscale/Tailscale userspace peers and TLS WebDAV services, in addition to synthetic negative protocol fixtures. Those services were disposable and stopped afterward. The user confirmed no second device or external account is available, so actual installation, remote-network reachability and physical-loss recovery remain pending. [Configuration and evidence](INDEPENDENT_SERVICES.md) describe what was exercised and how to prepare private identity settings.

## Checks supplied with the release

From a teammate's computer, using the actual private VPN HTTPS address:

```sh
.venv/bin/python scripts/deployment_check.py --origin https://your-private-host
```

For a private certificate authority, add `--ca /path/to/trusted-ca.pem`. Certificate verification is always enabled; never bypass it. This checks reachability, initialized setup, HTTPS/security headers and denial of unauthenticated HR data. It never signs in or changes an HR record. Run it both on the host and on the teammate device; a host-only pass does not prove remote access. Use your actual origin without a path, username, password or query parameters.

Stop the local server cleanly before checking its explicit data path:

```sh
.venv/bin/python scripts/deployment_check.py --db /private/path/openpeople.db
```

This uses immutable read-only SQLite and refuses an active WAL. It checks supported schema, integrity, foreign keys, an active HR account, MFA policy and POSIX file/key/directory permissions. It does not migrate or repair a database. It does not inspect FileVault, VPN settings, other files, cloud credentials or personal browser profiles. Windows NTFS permissions and disk encryption need verification by the operator.

The current schema is 9. The offline preflight also verifies local audit chains. Retain an independently held audit anchor before a recovery exercise and compare it using `scripts/audit_check.py`; a locally recomputed hash alone does not detect a database owner's complete rewrite. Review legacy payroll accounts, restrict employer access where needed and confirm revoked sessions and historical-employer boundaries from a separate operator account.

The command exits 0 for passing technical checks and 1 for incomplete/failed checks. Its JSON keeps `enterprise_production_approved` false: a read-only preflight cannot attest to payroll legality, successful cloud upload or authenticated collaboration.

## Browser and access acceptance

Create individual fictional HR, employee, manager and payroll accounts. Enable authenticators and the workspace MFA requirement. From two devices, sign in separately, save an employee edit, and confirm the other browser refreshes it. Attempt a stale edit and confirm it requires review. Verify denied HR actions, own-request approval denial, account deactivation and session revocation. Review leave/attendance/benefit/course workflows against your employer's policies.

Check that only the private HTTPS endpoint is reachable remotely; the backend remains bound to loopback. Restart the application and proxy through the intended service setup, verify recovery after reboot, and confirm the host remains awake when needed. The included Caddy configuration's slow-input limits are part of the tested boundary.

## Identity-provider acceptance when used

Register the exact HTTPS callback and configure the issuer/client/secret privately. Provision users and roles in OpenPeople first. On the actual tenant, check a provisioned verified-email identity, an unprovisioned user, MFA requirements, issuer/subject linkage, signing-key rotation and account disablement. OpenPeople does not have SCIM provisioning or automatic provider-side logout/session revocation. Provider deactivation can stop new sign-ins without instantly terminating an already established local session; revoke the OpenPeople account/sessions as part of the leaver workflow.

The protected synthetic HTTPS fixture verifies protocol handling and negative token cases; independent local Dex additionally verifies interoperable generated configuration, real consent/PKCE/JWKS, local MFA and account-disablement boundaries. Neither establishes a particular Okta, Microsoft, Google or other external tenant's claims, policy or provisioning configuration. Self-hosted Dex still needs operational TLS renewal, monitored startup, secure provisioning and identity database recovery acceptance.

## Cloud and replacement-host recovery acceptance

1. Configure a dedicated folder with your cloud client, or configure the [HTTPS WebDAV integration](CLOUD_WEBDAV.md). Run a backup; confirm its job is **Completed** and record the archive hash/time privately.
2. Confirm upload in the actual provider UI; for WebDAV also require Verified remote copy and its recorded checksum. Local archive completion does not mean off-device upload completed.
3. Retrieve the encrypted file from the provider on another authorized computer. Do not copy it only from the original host or place the live database in the sync folder.
4. With the original host unavailable, use the separately retained passphrase to restore to a new empty destination:

```sh
.venv/bin/python backup.py verify /path/to/downloaded.opbackup
.venv/bin/python backup.py restore /path/to/downloaded.opbackup --destination /private/new-empty-recovery-folder
.venv/bin/python server.py --db /private/new-empty-recovery-folder/workspace.db
```

5. Check known fictional canary records, payroll component/reference history, audit events and fresh MFA login. Confirm old sessions cannot be reused. Stop the recovered server, check its database with the offline diagnostic, then reconfigure backups for the replacement host. Record elapsed recovery time, last recovered edit and all failures.

The local release drills stop their fictional source host and remove original paths before restoring. One uses simulated folders; the additional independent TLS WebDAV service exercises actual upload/read-back/download and audit-anchor comparison. Both remain on this computer and cannot prove survival of physical disk loss, an external cloud account or a separately held passphrase.

## Production launch and operational checks

After the installation checks pass, enable the explicit `--production` profile and use [the operations guide](OPERATIONS.md) for liveness, private readiness, full offline checks and bounded crash supervision. Technical startup gates do not establish a legal/enterprise approval. Configure a monitored platform service and test reboot; the supervisor alone does not run after reboot. Accept dated group periods/results with fictional workers before operational use.

## Small-team and enterprise release decision

Small-team core HR use needs the actual access, MFA, host protection, backup/restore and employer-policy acceptance above. Keep tax calculation, filings and payments in a reviewed payroll system until jurisdiction validation is complete. Confirm provider terms/quota, available connectivity and costs; the app can run without rented application servers, but cannot promise free unlimited storage or uninterrupted remote access.

Enterprise use additionally requires measured capacity for the expected workforce, organizational/legal-entity and data-access scope, configurable approval/delegation requirements, statutory payroll acceptance where needed, operational monitoring, independent auditing/retention, incident response and an independent security review. SQLite on one awake host is not a high-availability deployment. Use [the capability map](ROADMAP.md) to decide whether the current architecture meets the organization's requirements.
