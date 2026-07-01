# Derlem Security Hardening Backlog

**Date:** 2026-07-01
**Status:** Open production security gate; 6/8 P0 items open
**Target baseline:** OWASP ASVS Level 2

This register prevents known security gaps from disappearing inside general
roadmap text. The closed, single-machine Gardas pilot may continue, but
**internet-facing staging/production, public contribution, and external user
access are blocked until every P0 item is closed.**

## Priority

- **P0:** Blocks production and external access.
- **P1:** Required before v1.0 and official model-team use.
- **P2:** Defense in depth and operational maturity.

## Existing Controls

- JWT verification, RBAC, and bcrypt password hashing.
- Minimum 32-character JWT secret and 12-character bootstrap password checks.
- Parameterized PostgreSQL queries and transactional decisions.
- Append-only audit triggers.
- Content-addressed SHA256 storage and immutable frozen releases.
- Upload size bound, filename sanitization, and staging isolation.
- PII, rights, deduplication, decontamination, and human-review gates.
- `HttpOnly`, `SameSite=Lax`, and production `Secure` session cookies.
- Basic `nosniff`, frame denial, and referrer headers.

These controls do not close the production risks below.

## P0 - Production Blockers

| ID | Current gap | Risk | Completion evidence |
|---|---|---|---|
| `SEC-P0-01` | **Closed, 2026-07-01.** Every data route is registered fail-closed with an explicit non-empty role policy; raw/quarantined workspaces are limited to operations roles, similarity full text to reviewers, jobs to admin/data manager, and consumers to frozen releases. | A future endpoint may be opened to the wrong role or rely on frontend hiding. | [`api_authorization_matrix.en.md`](api_authorization_matrix.en.md), positive/negative tests for every protected GET route across seven roles, and the consumer draft-release filter. Source/project ACLs remain under `SEC-P1-02` before public multi-tenant contribution. |
| `SEC-P0-02` | **Closed, 2026-07-01.** PostgreSQL session store, hashed 256-bit `jti`, 30m idle/8h absolute timeout, current/all-session revocation, `auth_version` status/password/role triggers, and account+IP throttling are active. | Incorrect proxy trust, session replay, or a rate-limit regression. | [`session_security.en.md`](session_security.en.md); unit and desktop/mobile E2E tests; `429 + Retry-After`; failed/blocked login audit and structured warnings; rolled-back auth-version trigger smoke. Central alerts remain `SEC-P1-03`; admin MFA/Keycloak implementation remains `SEC-P1-01`. |
| `SEC-P0-03` | Nginx listens on HTTP with HTTPS redirect commented out; no HSTS/CSP/Permissions-Policy. Sensitive API responses lack global `Cache-Control: no-store`; state-changing BFF routes have no explicit CSRF control. The production DB example uses `sslmode=disable`. | Token/data interception, downgrade, amplified XSS impact, cache leakage, and CSRF. | Fail-closed production startup; HTTPS-only TLS 1.2/1.3 and HSTS; verified Secure cookie; CSP, Permissions-Policy, `no-store`, logout `Clear-Site-Data`; Origin/CSRF validation; DB TLS or documented private-network exception. |
| `SEC-P0-04` | Audit is append-only by trigger, but migration and runtime DB privileges are not separated. No actor email/role snapshot; `request_id` is not an HTTP correlation ID; CLI imports appear as `system`; most sensitive reads/downloads are not audited. | A privileged DB account can weaken evidence; historical attribution and exfiltration investigation are incomplete. | Separate migration-owner/runtime DB roles; runtime audit mutation denial; real request correlation, actor email/role snapshot, hashed session ID, controlled IP/user-agent metadata; CLI service/operator identity; sensitive read/download audit; off-host append-only/WORM or hash-chained audit; retention/redaction policy. |
| `SEC-P0-05` | Secrets load from environment files with no rotation/revocation flow. Bootstrap credentials may remain in production; startup does not reject `CHANGE_ME` or local test accounts. | Secret leakage, persistent account compromise, and environment confusion. | Vault/secret manager or protected secret files; JWT/DB rotation runbook; separate service identities; fail-closed rejection of placeholders, bootstrap password, and local accounts in production; secret scanning. |
| `SEC-P0-06` | Local storage is read-only by file mode, not true object lock/WORM. API and worker share one OS identity and storage authority. DB/object restore has not been exercised. | Ransomware, application compromise, or operator error can mutate evidence; recovery is unproven. | S3/MinIO Object Lock or separate writer/reader WORM design; periodic checksum inventory; encrypted DB/object backups; defined RPO/RTO; tested restore with frozen-manifest verification. |
| `SEC-P0-07` | Upload permits up to 50 GiB and removes request deadlines. There are no per-user quotas, concurrency bounds, disk-headroom reservation, content allowlist, or malicious-file quarantine. | Disk and connection exhaustion DoS; processing of unexpected files. | Role quotas and rate limits; global/per-user concurrency; disk-headroom checks; read/write deadlines; allowed formats/encoding/content; quarantine scanner; partial-upload cleanup and full-disk tests. |
| `SEC-P0-08` | CI runs tests/builds but lacks `govulncheck`, `gosec`, `pip-audit`, CI `npm audit`, secret scanning, CodeQL/SAST, dependency automation, and SBOM generation. | Known dependency or source vulnerability can ship. | Security CI jobs that fail on high/critical findings; Dependabot/Renovate; secret scan; CodeQL or equivalent SAST; version pinning and release SBOM. |

## P1 - Required Before v1.0

| ID | Target |
|---|---|
| `SEC-P1-01` | Keycloak/OIDC or equivalent identity provider with MFA, service accounts, key rotation, and user lifecycle. |
| `SEC-P1-02` | Source/project ACLs and least-privilege role matrix; organizational identity that prevents one person using multiple accounts for independent approval. |
| `SEC-P1-03` | Central security logging and alerts for failed login, authorization failures, audit gaps, queue anomalies, and disk pressure. |
| `SEC-P1-04` | ASVS Level 2 control matrix, threat model, abuse-case tests, and independent security test/pentest. |
| `SEC-P1-05` | Approved takedown/delete, KVKK access, and retention policy integrated with immutable releases. |
| `SEC-P1-06` | At-rest encryption/KMS for sensitive data and backups, including key-access and rotation audit. |

## P2 - Defense in Depth

- Risky-session and behavior anomaly detection.
- Tamper-evident audit hash chain with periodic external anchoring.
- Network segmentation, egress allowlisting, and optional management API mTLS.
- Chaos/restore exercises, incident-response games, and recurring red-team work.
- Artifact provenance/signing and reproducible production-build evidence.

## Delivery Order

1. `SEC-P0-01`, `SEC-P0-02`: complete.
2. `SEC-P0-03`: external access and transport boundary.
3. `SEC-P0-04`, `SEC-P0-05`: evidence and secret protection.
4. `SEC-P0-06`, `SEC-P0-07`: data resilience and DoS resistance.
5. `SEC-P0-08`: supply-chain gate.
6. After P0, implement P1 centralized identity, observability, and policy work.

An item is not complete without code, negative tests, production runbook
evidence, and a restore exercise where applicable. Documentation or “the
operator will be careful” is not completion evidence.

## Primary References

- [OWASP ASVS](https://devguide.owasp.org/en/06-verification/01-guides/03-asvs/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
