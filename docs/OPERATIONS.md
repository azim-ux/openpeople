# Production launch controls and operations — 0.8.0

`--production` is an explicit technical launch profile and defaults to the enforced `core-hr` product scope. See [Core HR acceptance](CORE_HR_RELEASE.md). It refuses to bind the application listener when required checks fail. It requires schema 9, database/foreign-key/audit integrity, a configured HTTPS origin, an initialized real HR administrator, mandatory MFA with all active HR administrators enrolled, no demo workers, private POSIX database/key/directory permissions, and a successful current scheduled backup with an available destination. HR cannot disable mandatory MFA while this profile is running.

The HTTPS check validates the configured origin; the operator still must accept the proxy's actual certificate and endpoint. A local successful backup and an origin string do not prove off-device recovery or remote connectivity. Passing the profile does not approve payroll legality, government submissions, enterprise capacity or operating-system disk encryption. Reports keep those acceptance boundaries explicit.

Initialize accounts and enroll authenticators through the local setup first. Configure and verify scheduled backups using the private recovery passphrase; remove demo data by choosing a separate real-data workspace, never by silently deleting an existing workspace. Follow [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md) before real employee use.

An installing operator can use `python scripts/setup_workspace.py --db data/openpeople.db --country IN` while the app is stopped. It privately prompts for a password and real authenticator enrollment proof; the default local login `admin@openpeople.invalid` needs no personal mailbox. Building/publishing source requires no administrator. See [the release guide](GITHUB_RELEASE.md). Recovery codes are invalidated on password changes and deliberately excluded from archives; generate new codes after restoration.

Start a deliberately selected workspace behind its reviewed HTTPS proxy:

```sh
.venv/bin/python server.py --db /private/openpeople/workspace.db \
  --public-origin https://hr.example.internal --production
```

For bounded crash recovery, use the supervisor instead of starting a second server:

```sh
.venv/bin/python scripts/run_service.py --db /private/openpeople/workspace.db \
  --public-origin https://hr.example.internal --production --max-restarts 3
```

The supervisor locks this workspace's service slot, starts one loopback child, creates an owner-only `.service.log`, and retries crashes within a bounded budget. Normal exits and configuration refusal are not retried. Ctrl+C or termination stops its own child; it does not signal unrelated processes. It does not install launch agents, change sleep/network/trust settings, start after a computer reboot, or provide a second host. Monitored platform service installation and reboot acceptance remain operator work. Never run two supervisors or an ordinary server concurrently for the same workspace.

## Monitoring

`GET /api/health/live` exposes only status/version and uses existing Host/HTTPS/rate controls. It provides liveness, not privileged readiness or a production approval. Check a local instance with:

```sh
.venv/bin/python scripts/operations_check.py --origin http://127.0.0.1:8000
```

For remote checks use the exact HTTPS origin and, for a private CA, `--ca /private/reviewed-ca.pem`. Certificate checking remains enabled; redirects and embedded credentials are refused. The command never authenticates or changes HR records.

HR can open **Backup & recovery → Check technical readiness**. This uses cached destination health and bounded policy queries; it does not perform filesystem destination probes or unbounded database/audit scans in an HTTP worker. It reports current gaps without an enterprise-approved flag.

For full stopped-workspace inspection:

```sh
.venv/bin/python scripts/operations_check.py --db /private/openpeople/workspace.db
.venv/bin/python scripts/audit_check.py --database /private/openpeople/workspace.db \
  --anchor /separate-custody/audit-anchor.json
```

The offline checks refuse a nonempty WAL, use immutable read-only SQLite and do not migrate. The operations command cannot infer the deployed HTTPS origin, so that check remains false in offline mode. Full audit verification streams retained records without the old 200,000-row recovery ceiling; interactive anchor export remains bounded at 200,000 per chain. Keep anchors independently. Local database ownership still permits complete rewrite, and no automatic pruning/WORM storage is introduced.

Monitor process availability, backup freshness/failures, storage quota, encryption/key custody and alert response. The format's 256-MB database backup limit remains; larger deployment needs a reviewed streaming backup design. A local supervisor is not high availability, and a running computer is not proof that a remote client or independent recovery copy works.
