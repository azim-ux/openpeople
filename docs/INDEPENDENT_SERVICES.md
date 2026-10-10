# Private service configuration and acceptance — 0.5.0

The release was tested against actual **Dex 2.46.0**, **Headscale 0.29.4**, two **Tailscale 1.104.1 userspace nodes**, and **WsgiDAV 4.3.5 / cheroot 11.1.2**. These were separate open-source services with their own databases/configuration, not handwritten protocol mocks. They ran in the mandatory disposable OS sandbox with verified HTTPS and fictional accounts. No system VPN, DNS, routes, trust store, browser profile or startup service was installed.

The user confirmed that no external computer/NAS/cloud account is available. The test configures and starts the services, performs acceptance, then stops them and removes the disposable configuration/data. It does not leave a persistent production deployment connected to the existing HR server. Passing same-computer tests does not establish remote NAT traversal, independently held backups, physical disk-loss survival or commercial identity-tenant policy.

Evidence and pinned tool digests are in [the service report](validation/v0.5.0-isolation/report-services.json) and [tool provenance](validation/v0.5.0-isolation/service-tools-provenance.json). Source-tag digests are distinguished from independently supplied publisher checksums. Portable service binaries and optional Python service packages are excluded from the source ZIP.

## Configure a self-hosted identity provider

`scripts/configure_identity.py` generates private Dex configuration and HR client settings. It requires the operator's selected HTTPS HR origin, issuer, matching nonexpired issuer certificate/private key, trusted CA bundle and reviewed provisioned users. It rejects mismatched certificate names/keys, unverified or duplicate identities, plaintext passwords and weak bcrypt work factors. It never replaces an existing service directory or changes the running HR instance.

Prepare a private 0600 JSON array of Dex user records with `email`, `username`, stable `userID`, bcrypt `hash` with cost 12–16, and `emailVerified: true` after independently checking email ownership. Those users must also be provisioned in OpenPeople; identity sign-in cannot assign HR roles. Generate hashes locally using a reviewed bcrypt implementation. Do not submit passwords in chat or store plaintext passwords in this file.

```sh
.venv/bin/python scripts/configure_identity.py \
  --directory services-private \
  --origin https://hr.example.internal \
  --issuer https://identity.example.internal/dex \
  --certificate /private/certificates/identity.pem \
  --key /private/certificates/identity.key \
  --ca /private/certificates/trusted-ca.pem \
  --users /private/provisioned-identities.json
```

The resulting directory is 0700; `dex.json` and `app-env.json` are 0600. The client secret is generated randomly and never printed. Start your reviewed Dex installation with `dex serve /absolute/private/services-private/dex.json`; provide its matching frontend assets/working directory when using a source-built binary. The listener stays on loopback (5556 by default); configure a verified HTTPS proxy to match the chosen public issuer. Domain/certificate/proxy configuration is installation-specific and is not created by the generator.

Start a deliberately selected HR database with the generated settings:

```sh
.venv/bin/python scripts/start_identity_configured.py \
  --settings /absolute/private/services-private/app-env.json \
  --db /private/openpeople/workspace.db \
  --public-origin https://hr.example.internal
```

This launcher accepts only four expected identity environment keys, preserves the existing process environment and requires an explicit database path. It starts a new process; stop/upgrade the intended HR server deliberately after taking a recovery backup. The test accepted this generator's client configuration through real Dex consent, PKCE/JWKS sign-in, local MFA and leaver denial. Operational certificate renewal, identity database backup, availability and external IdP policy still require acceptance.

## Configure remote access and backup

Use [the shared-server/VPN guide](LOCAL_TEAM_AND_BACKUP.md) and [HTTPS WebDAV configuration](CLOUD_WEBDAV.md) for the actual chosen host/provider. The tested alternative uses Headscale/Tailscale without a kernel tunnel, with private state/control sockets and DNS/route changes disabled. It proved encrypted peer traffic, verified HTTPS, unauthenticated denial and an authenticated HR save. A reachable control/relay service and the second network must be tested on the real installation; localhost URLs in the test cannot serve another computer.

WsgiDAV acceptance used a dedicated TLS/basic-auth collection and tested upload, fresh read-back, retry/collision protection, download, decryption and recovery after removing original paths. This validates a self-hosted WebDAV integration, not a free cloud account or off-device storage. For physical-loss protection, the provider/NAS/backup medium must live outside this computer and the recovery passphrase and audit anchor must be held separately. Existing computer hosting avoids renting an application server; storage limits, connectivity, electricity and relay availability remain real constraints.

To repeat the independent test on this Mac after obtaining the pinned tools and optional libraries in a task-owned directory:

```sh
OPENPEOPLE_SERVICE_TOOLS=/private/tmp/your-reviewed-service-toolkit \
  .venv/bin/python scripts/test_isolated.py --services-only
```

The toolkit layout is `bin/dex`, `bin/tailscale`, `bin/tailscaled`, `headscale`, `dex/<source-root>/web` and `py-libs` containing the reviewed WsgiDAV/cheroot/bcrypt packages. There is no unrestricted fallback if the sandbox or tools are unavailable. Actual device/provider acceptance remains the procedure in [deployment acceptance](DEPLOYMENT_ACCEPTANCE.md).
