# Historical audit patch validation — OpenPeople 0.2.0

The [original audit](audit/2026-10-09/REPORT.md) describes the pre-patch application and remains historical evidence. This record describes OpenPeople 0.2.0 fixing the eight original reproduced issues. The subsequent 0.2.0 audit identified additional blockers; their fixes and current verification are in the [0.3.0 deployment review](DEPLOYMENT_REVIEW_0.3.0.md) and [VALIDATION.md](VALIDATION.md).

| Finding | Change | Regression evidence |
| --- | --- | --- |
| High: unfinished unauthenticated request blocks writes | Parse bounded request body before acquiring a SQLite write transaction; native deadlines plus Waitress buffering/channel limits | Stalled-body regression commits another write before timeout; real Waitress test succeeds with concurrent clients and an unfinished body |
| High: unconfigured instance can be claimed | Random owner-only bootstrap-token file, constant-time token verification, exact Host allowlist, setup closes after initialization | Missing/wrong token and untrusted Host denied; valid token works once |
| Medium: session revives after reactivation | Delete all sessions on deactivation and role change; recheck lifecycle inside write transaction; revoke legacy sessions on schema upgrade | Original employee cookie remains invalid after reactivation; upgrade preserves records and removes legacy sessions |
| Medium: save followed by failed refresh duplicates records | Treat successful save as committed and close form before refresh; stable form submission keys and atomic account/path/payload idempotency | Frontend failed-refresh/retry commits once; replay returns same ID; changed payload conflicts; simultaneous Waitress replay commits one row |
| Medium: login reveals account existence through hashing cost | Precompute dummy hash and perform one PBKDF2 verification for both missing and existing accounts | Test counts one verification for each path; large reproduced cost discrepancy removed, without claiming exact timing equality |
| Medium: HR approves its own requests | Server-side independent approval guard, direct-manager scope and configurable two-stage routing | Self-approval denied, independent HR succeeds, assigned manager stage remains pending, another HR finishes |
| Low: identifiers/Unicode cause server errors | Bound integer/path identifiers, validate Unicode text, reject non-ASCII security tokens and authenticator digits safely | Oversized/malformed identifiers and surrogates return client errors; malformed headers/codes do not produce 500 |
| Low: department names break reporting totals | Use a JavaScript Map rather than inherited object keys | `__proto__` and `constructor` count correctly in frontend regression |

## Added capabilities

Working additions include manager/specialist roles, benefits enrollment, learning assignments, notifications, manual reviewed payroll snapshots/statements, authenticator MFA, required-MFA enrollment gates, optional OIDC/PKCE, before/after auditing, bounded production WSGI serving and encrypted scheduled/manual recovery backups.

The selected collaboration design uses one authoritative local database, browser update polling, and a private remote-access configuration. The cloud integration boundary is encrypted files in the owner's chosen locally synced folder. No provider subscription, credential, upload, live VPN or external SSO registration has been created on behalf of the owner.

## Remaining scope

This patch does not establish feature/security parity with Workday. Automatic tax/statutory payroll, deep benefits/provider processing, arbitrary enterprise workflows, effective-dated compensation, leave entitlements, broader integrations, independently tamper-proof auditing, live-database application encryption, offline replica merge and production assurance remain explicit work in [the capability map](ROADMAP.md). Use operating-system disk encryption for live local records and verify off-device backup upload/restore as described in [the setup guide](LOCAL_TEAM_AND_BACKUP.md).
