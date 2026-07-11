# Session and Login Security

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

**Date:** 2026-07-01
**Scope:** `SEC-P0-02` implementation and operations contract

Derlem uses JWT only as a signed authorization assertion. A valid signature is
not sufficient for access: the corresponding PostgreSQL session must be active,
within its time limits, and aligned with the user's current authorization
version.

## Session Model

- The JWT carries a random 256-bit `jti` and the user's `auth_version`.
- The raw `jti` is never stored; only its SHA-256 digest is kept in
  `auth_sessions.jti_hash`.
- Default idle timeout is `30m`; absolute timeout follows the `8h` JWT lifetime.
- The API enforces idle and absolute timeouts server-side.
- Logout revokes the active server session before the cookie is removed.
- `POST /api/v1/auth/logout-all` revokes every active session for the user.
- User status/password changes and role insert/delete operations increment
  `auth_version` through database triggers and revoke open session rows with
  reason `principal_changed`. Old tokens receive `401` on their next request.
- Deploying the session model invalidates legacy JWTs without `jti`; users sign
  in once again.

## Login Throttling

Failure state lives in PostgreSQL, so multiple API instances share one limit.
Domain-separated HMAC-SHA256 keys derived from the server secret are stored
instead of raw email and IP values.

| Setting | Default | Meaning |
|---|---:|---|
| `LOGIN_ACCOUNT_FAILURE_LIMIT` | `5` | Per-account failures within the window |
| `LOGIN_IP_FAILURE_LIMIT` | `30` | Per-client-IP failures within the window |
| `LOGIN_FAILURE_WINDOW` | `15m` | Failure counting window |
| `LOGIN_LOCKOUT_DURATION` | `15m` | Temporary block after the threshold |
| `SESSION_IDLE_TTL` | `30m` | Session inactivity limit |
| `JWT_TTL` | `8h` | Absolute session limit |

The API returns `429 Too Many Requests` with `Retry-After` in seconds. Failed and
blocked logins enter the append-only audit log; blocked attempts emit structured
warning logs using hashed keys. Central alerting and SIEM integration remain in
`SEC-P1-03`.

## Client IP Boundary

The API normally uses the TCP remote address. It accepts a validated
`X-Real-IP` only when the connection itself comes from loopback, representing
the local Nginx/Next proxy. In public production the API must bind to localhost
and only Nginx may be internet-facing.

## Admin MFA/SSO Plan

The closed local pilot continues with password plus server-side session. Before
internet-facing use, the P1 identity phase introduces Keycloak/OIDC or an
equivalent IdP: MFA is mandatory for admins and critical reviewers, while agents
receive separate service accounts and short-lived credentials. Until that
transition, `auth_sessions` is the revoke and timeout authority; afterwards it
is integrated with the IdP session/token lifecycle.

## Verification

- Unit tests cover JWT `jti/auth_version`, session entropy/hash, trusted proxy IP,
  and `Retry-After`.
- Playwright proves rejection of a stolen cookie after logout, second-session
  invalidation after logout-all, and `429` after repeated bad passwords.
- Migration smoke verifies that role insert/delete and user status changes bump
  `auth_version` inside a rolled-back transaction.

```powershell
go test ./...
Set-Location web
npx playwright test tests/e2e/session-security.spec.ts
```

## Primary References

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
