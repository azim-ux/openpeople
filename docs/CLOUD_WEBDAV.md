# Encrypted WebDAV backups

OpenPeople 0.4.0 transfers encrypted `.opbackup` files to a dedicated HTTPS WebDAV collection. Providers without WebDAV still work through a locally synchronized folder. No real provider is configured or accepted on this installation.

## Private configuration

Create a dedicated collection using your provider's instructions. Supply these variables privately to the server/service process:

| Variable | Meaning |
| --- | --- |
| `OPENPEOPLE_WEBDAV_URL` | HTTPS collection URL; no credentials, query or fragment in the URL |
| `OPENPEOPLE_WEBDAV_USER` | Dedicated account/app-password user |
| `OPENPEOPLE_WEBDAV_PASSWORD` | Private credential; keep out of source control and shell history |
| `OPENPEOPLE_WEBDAV_CA` | Optional trusted private CA bundle; TLS verification stays enabled |

Use a directory separate from personal files. This integration does not list/delete remote files or create collections. The provider must support GET and conditional PUT (`If-None-Match: *`). It does not promise free storage or verify a specific provider's quota. Proxy environment settings are ignored; direct HTTPS connectivity is required.

Configure a local encrypted backup folder using [the backup guide](LOCAL_TEAM_AND_BACKUP.md). The worker creates the local archive and updates its status before releasing local snapshot/configuration locks and transferring it. **Completed** means local backup success; the separate **Verified remote copy** status requires fresh HTTP read-back and a matching SHA-256. Transfers started by the backup worker have a 75-second absolute subprocess deadline and retain the local archive on failure. Large backups on slow links may need a separate sync client.

Remote filenames are immutable. Same-byte retries succeed; conflicting files are not intentionally replaced and fail verification. A provider that ignores conditional writes must fail deployment acceptance and must not be used. Redirects, untrusted certificates, unsafe filenames, oversized files and nonciphertext markers are rejected. Remote retention is managed through the provider; monitor quota.

## Transfer and recovery

With the private environment configured:

```sh
.venv/bin/python cloud_backup.py upload /private/snapshots/openpeople-example.opbackup
```

Retain the returned filename and SHA-256 outside the host. On the recovery computer, create a dedicated empty download folder and use that separately recorded digest:

```sh
.venv/bin/python cloud_backup.py download openpeople-example.opbackup --destination /private/downloads --sha256 YOUR_RECORDED_64_CHARACTER_SHA256
.venv/bin/python backup.py verify /private/downloads/openpeople-example.opbackup
.venv/bin/python backup.py restore /private/downloads/openpeople-example.opbackup --destination /private/new-recovery-workspace
```

Download refuses existing filenames, publishes verified ciphertext atomically with owner-only permissions, and removes partial files on failure. Restore separately authenticates/decrypts with the privately entered recovery passphrase. Standalone transfer commands have idle and between-chunk time budgets; the absolute subprocess deadline applies to the backup worker. Supervise standalone operations with an operator/service timeout.

## Test scope

Tests use a separate synthetic HTTPS provider, real TLS trust, credentials, conditional uploads and fresh downloads. Cases cover retries, wrong credentials, redirects, untrusted certificates, tampering, hash mismatch, collisions, plaintext/symlink rejection and redacted status. The recovery test stops its fictional source server and removes the original database and archive paths before downloading and restoring; old sessions remain revoked.

All fixture storage is on this computer. This verifies transport/recovery code, not physical disk-loss survival, a real provider or separately held passphrase custody. Complete [actual deployment acceptance](DEPLOYMENT_ACCEPTANCE.md) on another computer before relying on off-device recovery.
