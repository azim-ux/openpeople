# Employer payroll access and audit integrity — 0.6.0

HR administrators manage payroll access from **Organization → Payroll operator access**. A member can have all workspace employers, selected employers, or an empty restricted set. Saving requires authentication within five minutes, a current access version and CSRF protection. It immediately revokes that payroll member's sessions. Legacy payroll accounts preserve their prior all-workspace access until HR restricts them; review those accounts during upgrade.

Restrictions apply on the server to current salary previews, pay-result reads/edits, employer metadata and filing packets. Historical payroll uses the employer recorded in the original pay statement; transferring a worker does not reveal their earlier statements to a new employer's payroll operator. Unassigned workers are excluded from restricted previews. A restricted operator cannot create an organization-wide run or finalize a run that includes hidden statements. Payroll maker/checker rules still apply.

These are payroll permissions within one shared workspace. HR remains an administrator with workspace-wide access, and the basic employee directory remains shared. They do not isolate separate customer tenants, give arbitrary field permissions, or implement approval delegation/SAML/SCIM. Auditors retain their existing workspace audit role.

Business changes and security events now have separate SHA-256 chains. SQLite triggers append seals atomically and reject ordinary updates/deletes of event/seal rows. The **Security audit → Verify & export audit anchor** action verifies the retained chains and exports a count, last ID and digest. Save that small anchor independently of the database and computer. Later legitimate events remain compatible with an earlier anchor.

To check a stopped workspace against an earlier retained anchor:

```sh
.venv/bin/python scripts/audit_check.py --database /private/recovered/workspace.db --anchor /separate-custody/audit-anchor.json
```

The checker uses immutable read-only SQLite and refuses a live WAL. Missing/changed seals, altered records and rollback before the retained anchor fail verification. Schema-7-and-later recovery checks local audit integrity before publishing restored files. Existing pre-upgrade history is sealed as a migration baseline; that does not retrospectively prove its accuracy.

A host administrator can replace the database, code and chains. Local hashes are not independent signatures or WORM storage. Independent anchors detect changes relative to the retained history but do not prevent a compromised host from forging future events. External audit retention, signing/anchoring policy and incident ownership remain enterprise deployment requirements. The interactive verifier retains a 200,000-row-per-chain budget. Full stopped-workspace and automatic restore verification stream all retained records, including earlier-anchor checks. This removes the old recovery ceiling without creating an audit retention, pruning, WORM or enterprise capacity policy. The backup database format still has a 256-MB limit.

Employer-bound [pay groups and dated periods](PAY_PERIODS.md) retain the same historical employer boundaries. Restricted operators cannot prepare a hidden group or finalize a run containing hidden statements. Every dated statement needs an externally reviewed result. [Production controls](OPERATIONS.md) remain technical checks with deployment-specific acceptance outstanding.
