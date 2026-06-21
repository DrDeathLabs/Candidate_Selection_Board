# Security Policy

## Supported Versions

This application is under active development. Only the current `main` branch receives security fixes.

## Authentication Architecture

### Production Authentication

Candidate Selection Board implements **FISMA Moderate** authentication with two supported paths:

1. **Primary path: OIDC SSO** (agency IdP — Login.gov, ADFS, Okta)
   - Validates JWT signature via JWKS endpoint
   - Maps provider group claims to internal roles via `OIDC_GROUP_PREFIX`
   - Agency IdP handles PIV/CAC/MFA (satisfies IA-2 by delegation)
   - Configure: `OIDC_ISSUER_URL`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`

2. **Secondary path: Local username + password + TOTP**
   - Argon2id password hashing (FISMA IA-5)
   - TOTP (RFC 6238) second factor, AES-256 encrypted at rest
   - 14-character minimum, complexity requirements enforced
   - Password history (last 5) checked on every change
   - Password rotation enforced every 90 days

### Session Security

| Property | Value | Control |
|---|---|---|
| Session token | Opaque 32-byte random, SHA-256 hashed in DB | — |
| Cookie | `HttpOnly; SameSite=Strict; Secure` (set `SESSION_COOKIE_SECURE=true` in prod) | — |
| Idle timeout | 15 minutes | AC-11 |
| Absolute timeout | 8 hours | AC-12 |
| Concurrent sessions | 3 max per user | AC-10 |
| Failed login lockout | 5 attempts → 30-minute lockout | AC-7 |
| CSRF protection | Double-submit cookie (`sb_csrf` + `X-CSRF-Token` header) | — |

### Development Mode

Setting `DEV_AUTH_BYPASS=true` in `.env` (the default for local Docker Compose):

- Unauthenticated requests are treated as a local admin with all roles
- CSRF protection is disabled
- The Python code default for `DEV_AUTH_BYPASS` is `false` — this protects any deployment that bypasses Docker Compose

**Never deploy with `DEV_AUTH_BYPASS=true` in a non-local environment.**

### Admin Bootstrap

On first startup, seed the initial administrator account:

```bash
docker compose exec api python -m app.bootstrap seed-admin
```

This creates the initial `admin` (SYSTEM_ADMINISTRATOR) account. The generated password is printed **once** to stdout and is visible in `docker compose logs api`. Store it securely and rotate it immediately via **Admin → Users** or `POST /api/v1/auth/password/change`. It is not stored in plaintext after this point.

## Reporting a Vulnerability

Report security vulnerabilities through GitHub private vulnerability reporting for this repository.

Please include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations

Do **not** open a public GitHub issue for security vulnerabilities. If private reporting is unavailable, contact the maintainer through the repository owner profile and do not include exploit details in public.

## Known Dev-Only Defaults

| Setting | Dev Default | Required Production Value |
|---|---|---|
| `DEV_AUTH_BYPASS` | `true` (in `.env`) | `false` |
| `SESSION_COOKIE_SECURE` | `false` | `true` |
| `REDIS_PASSWORD` | (empty) | Strong random password |
| `POSTGRES_SSL_MODE` | `prefer` | `require` |
| `OPENSEARCH_SECURITY_DISABLED` | `true` | `false` |
| `POSTGRES_PASSWORD` | `change-me` | Strong random password |
| `MINIO_ROOT_PASSWORD` | `change-me` | Strong random password |
| `TOTP_ENCRYPTION_KEY` | dev placeholder | 32-byte Fernet key |

## FISMA Moderate Controls Implemented

| Control | ID | Implementation |
|---|---|---|
| Multi-Factor Authentication | IA-2 | TOTP (local) + OIDC PIV/CAC delegation |
| Authenticator Management | IA-5 | Argon2id, 14-char min, complexity, history, 90-day rotation |
| Failed Logon Attempts | AC-7 | 5 attempts → 30-min lockout |
| Session Lock | AC-11 | 15-min idle timeout |
| Session Termination | AC-12 | 8-hr absolute timeout |
| Concurrent Sessions | AC-10 | Max 3 per user |
| Account Management | AC-2 | Full CRUD at `/admin/users` |
| Access Enforcement | AC-3 | 7 roles, JWT/session-validated |
| Least Privilege | AC-6 | Role-scoped endpoints, no elevation path |
| Audit Events | AU-2 | LOGIN, LOGOUT, LOGIN_FAILED, ACCOUNT_LOCKED, PASSWORD_CHANGED, MFA_ENROLLED, CASE_*, EVAL_*, ADJUDICATION_* |
| Audit Content | AU-3 | session_id, source_ip, actor_id on all events |
| Rate Limiting | SI-10 | 10/min on `/auth/login` per IP |
| CSRF Protection | SC-8 | Double-submit cookie pattern |

## Infrastructure Controls (Action Required for Production)

| Control | ID | Action Required |
|---|---|---|
| Transmission Security | SC-8 | Install TLS cert; set `SESSION_COOKIE_SECURE=true` |
| Encryption at Rest (PII) | SC-28 | Provision FIPS-validated encrypted storage volumes for PostgreSQL and MinIO |
| SIEM Integration | AU-9 | Forward audit_events from audit-service to SIEM |
| OpenSearch Auth | AC-3 | Set `OPENSEARCH_SECURITY_DISABLED=false` and provision certs |
| mTLS Between Services | SC-8 | Deploy service mesh or per-container certs |
