# Local team, remote access and recovery

This guide uses the selected model: one computer runs OpenPeople and owns the live database; teammates use browsers; a separate cloud client copies encrypted backups. It does not run a paid hosted application server or merge separate offline databases. Software changes are implemented; your VPN, cloud folder, certificates and optional identity provider still need configuration.

## Choose the host

Use a computer you can keep powered on with private local storage, a supported Python installation and full-disk encryption. Install OpenPeople as described in [README.md](../README.md). Keep its database outside cloud-synced directories. Start and complete initial setup locally using the token file. Add a separate account for each teammate in People and assign the minimum role needed.

Enable your own authenticator in My account. After another HR account can recover administration if necessary, use Workspace policies to require authenticators. Check reporting relationships and choose the leave/expense approval template. The creator cannot finalize their own payroll draft, and requests need an independent reviewer.

One process owns the database. SQLite transactions serialize writes; form retries carry an idempotency key. Browsers check for committed updates every 15 seconds while visible and not editing a form. Employee saves require a record version. A stale save returns 409 and offers Load latest values and review; re-enter only the intended changes. Independent offline editing/merge is not implemented.

## Private remote access

A practical self-hosted option is [WireGuard](https://www.wireguard.com/quickstart/), which connects each authorized device to a private network. Install its official client for your operating system and give each device its own key pair. A sample private network is `10.7.0.0/24`; select another range if it overlaps your LAN or a teammate's network.

Example host tunnel configuration, replacing every key placeholder:

```ini
[Interface]
Address = 10.7.0.1/24
ListenPort = 51820
PrivateKey = HOST_PRIVATE_KEY

[Peer]
PublicKey = FIRST_TEAMMATE_PUBLIC_KEY
AllowedIPs = 10.7.0.2/32

[Peer]
PublicKey = SECOND_TEAMMATE_PUBLIC_KEY
AllowedIPs = 10.7.0.3/32
```

First teammate configuration:

```ini
[Interface]
Address = 10.7.0.2/32
PrivateKey = FIRST_TEAMMATE_PRIVATE_KEY

[Peer]
PublicKey = HOST_PUBLIC_KEY
Endpoint = YOUR_REACHABLE_HOST_ADDRESS:51820
AllowedIPs = 10.7.0.1/32
PersistentKeepalive = 25
```

Use a unique address/key for every peer. Protect private keys, exchange public keys through a trusted channel, and remove a departing device's peer. Permit the VPN's UDP listener through the host/router as appropriate; permit HTTPS to the VPN interface. Do not forward application port 8000 or HTTPS to the public internet for this private configuration. Operating-system tunnel setup and firewall commands differ; use the official platform instructions.

The host needs a reachable endpoint, such as router port forwarding with an existing public address or suitable IPv6 connectivity. Carrier-grade NAT, blocked incoming traffic or lack of router control may require a relay/mesh service. Its business eligibility, limits and price need checking for your provider. OpenPeople cannot guarantee zero-cost remote connectivity on every network. If the host is off or the tunnel cannot connect, teammates cannot access the shared workspace.

## HTTPS on that private network

Install Caddy from its [official distribution](https://caddyserver.com/docs/install). This example binds HTTPS to the VPN address and uses Caddy's internal certificate authority. Authorized client devices must trust that CA through their operating-system/browser trust settings. Caddy describes that requirement in its [local HTTPS documentation](https://caddyserver.com/docs/automatic-https). Install the CA certificate securely; keep the CA private key on the host. Do not bypass certificate warnings.

Use the complete tested [deploy/Caddyfile](../deploy/Caddyfile), replacing the VPN address with your own. Use the tested Caddy 2.11.7 or a version independently validated with this configuration. It bounds headers/body sizes and upload deadlines, buffers the app’s small JSON bodies, and enables HTTP/1 full duplex so timeout/error responses do not drain an unfinished body. The latter Caddy option is experimental: test upgrades with `tests/probe_https_recovery.py` before rollout. Do not replace this file with a bare reverse proxy; the combined configuration passed the slow-request gate.

The `bind` directive restricts the listener's interface. [Caddy bind reference](https://caddyserver.com/docs/caddyfile/directives/bind). The proxy forwards to local Waitress while preserving the host and supplying the scheme/client address. [Caddy reverse-proxy reference](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

Start OpenPeople with the exact external HTTPS origin:

```sh
.venv/bin/python server.py --host 127.0.0.1 --port 8000 --public-origin https://10.7.0.1
caddy run --config /path/to/Caddyfile
```

These are separate long-running processes; run them in separate terminals or configure local operating-system services. Binding port 443 may require an appropriate service privilege/capability. Start the VPN first. In HTTPS mode, OpenPeople accepts the configured Host and rejects plain HTTP; direct access using `127.0.0.1:8000` is intentionally no longer the browser entry point. Visit **https://10.7.0.1** through the VPN, including from the host.

After certificate trust is configured, check from a teammate device that the browser has a valid HTTPS connection, a separate account can sign in with MFA, and committed edits appear on the other client's next refresh. Test a denied HR action from an employee account. The app trusts scheme/address forwarding only from one proxy at `127.0.0.1`; do not change that boundary or add arbitrary trusted proxies without review. The release passed an actual Caddy/Waitress TLS test on isolated loopback listeners; no real VPN or offsite device was available. See the [deployment review](DEPLOYMENT_REVIEW_0.3.2.md) and [installation acceptance procedure](DEPLOYMENT_ACCEPTANCE.md).

## Optional organization SSO

Use a trusted OIDC provider supporting authorization code, PKCE S256, RS256 or ES256 signatures and a verified email claim. Register OpenPeople and its exact callback:

```text
https://10.7.0.1/api/sso/callback
```

Configure these environment variables in the private server process/service:

```text
OPENPEOPLE_OIDC_ISSUER=https://your-identity-provider.example/issuer
OPENPEOPLE_OIDC_CLIENT_ID=your-registered-client
OPENPEOPLE_OIDC_CLIENT_SECRET=your-secret-if-the-client-is-confidential
```

The issuer must match discovery metadata exactly. Keep secrets out of source control, cloud folders and command history. Do not use the `.example` placeholders as a real provider. Provision accounts and roles in People first; SSO does not create administrators. A first verified identity links to the existing email, then subsequent logins use issuer/subject binding. Local MFA remains required when enabled. Provider-specific claims and registration need an actual integration test; automated tests now include separately serving synthetic HTTPS discovery/authorization/token/JWKS endpoints, real PKCE exchange and signed JWTs. This does not certify a live provider tenant. The implementation follows the checks described in [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html).

## Encrypted cloud-folder backups

Install/configure the sync client you already want to use, such as Drive, Dropbox, OneDrive or Nextcloud. Choose a dedicated folder outside the live database directory. Use available storage under the provider's current quota and terms; the application does not subscribe to a plan or hold cloud-provider credentials.

Configure and create the first backup locally:

```sh
.venv/bin/python backup.py configure --folder "/your/synced/OpenPeople-backups" --interval 60 --retain 30
.venv/bin/python backup.py run
.venv/bin/python backup.py status
```

For another database, add `--db /private/path/openpeople.db` to each command. Windows users use `.venv\Scripts\python.exe` and `--db "%LOCALAPPDATA%\OpenPeople\openpeople.db"`. Enter a long unique recovery passphrase when prompted and keep a copy in a separate safe location. The scheduled worker checks every 30 seconds while the application runs. Backup & recovery → Back up now queues a job and returns promptly. Confirm Completed and the filename, not just the queued toast. Missing/replaced folders are never silently recreated. Destination checks run in the background; the UI shows when it was checked. After restart, interrupted jobs become Failed and overdue scheduled work catches up while the host is awake.

Each snapshot is encrypted before any file is written into the sync folder. The archive includes the database and the key needed for its encrypted authenticator fields. It excludes reusable sessions, pending SSO state, idempotency responses and pending MFA enrollment. Authenticator configuration, account passwords as hashes, HR records and audit tables remain recoverable. [AES-GCM authentication](https://cryptography.io/en/latest/hazmat/primitives/aead/) protects backup integrity; [scrypt](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/) derives its key from the recovery passphrase.

Retain at least two archives per configuration generation (default 30). A failed new archive/read-back does not prune previous good copies. Older generations and unrelated workspace files remain untouched; keep their recovery phrases after rotation. Space and permission failures persist in status. To validate an archive without overwriting any workspace, run `backup.py verify /path/to/file.opbackup` and enter the phrase privately. This validates a temporary local restore, not provider upload.

Check the cloud client's upload status and open the provider from another device to confirm the `.opbackup` file exists off the host. With a local sync client, the app reports local creation only. The optional [WebDAV integration](CLOUD_WEBDAV.md) additionally verifies fresh remote read-back; that still does not establish recovery on another device. A 60-minute interval can lose up to roughly one interval of committed edits plus scheduling/upload delay; shutdown, sleep, storage errors or a paused sync client can make that longer. Automatic retention applies only to this workspace's current configuration generation after successful read-back. Cloud quota and older generations still require monitoring. The current backup format supports a database up to 256 MB.

## Restore after computer failure

1. Install the same application release and dependencies on a new trusted computer.
2. Download an intact `.opbackup` from your provider or another off-device copy.
3. Run the restore command and enter the separately saved recovery passphrase:

   ```sh
   .venv/bin/python backup.py restore "/downloaded/file.opbackup" --destination "/private/new-restored-folder"
   .venv/bin/python server.py --db "/private/new-restored-folder/workspace.db"
   ```

4. Sign in again. Old sessions cannot authenticate. Check expected people, requests, course records, audit history and finalized pay statements. Authenticator secrets are restored using the key in the encrypted archive.
5. Reconfigure the backup folder/passphrase, optional SSO environment and remote VPN/proxy on the new host. Restore does not carry a cloud-client account, local backup schedule, VPN keys or Caddy trust configuration.
6. If you continue from the recovered snapshot, make it the sole authoritative workspace. Do not run the failed/recovered hosts simultaneously and expect their databases to merge.

Restore never overwrites an existing folder. Wrong passphrases, damaged ciphertext and invalid archive contents are rejected before a workspace is created. Rehearse this procedure using a new private directory and an off-device file before relying on backups. No recovery is possible without the recovery passphrase.
