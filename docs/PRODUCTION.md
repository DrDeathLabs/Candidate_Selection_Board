# Production Readiness

This checklist is for an internet-facing or agency-internal network deployment.

## Required Secrets

Generate fresh production-only values before launch. Never reuse dev placeholders.

| Secret | Generation command |
| --- | --- |
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` |
| `REDIS_PASSWORD` | `openssl rand -base64 32` |
| `MINIO_ROOT_PASSWORD` | `openssl rand -base64 32` |
| `TOTP_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Use alphanumeric passwords or URL-encode special characters if embedding them in connection strings.

## Prebuilt Image Tagging

If you deploy from GHCR, prefer pinned release tags in `.env`:

```env
IMAGE_TAG=vX.Y.Z
```

Use `latest` only for convenience testing or short-lived evaluation environments. Production and long-lived internal deployments should be pinned to an exact version tag and upgraded deliberately.

Start the prebuilt stack with:

```bash
docker compose -f docker-compose.pull.yml up -d
```

## MFA

Candidate Selection Board enforces local TOTP MFA for all roles except `READ_ONLY_AUDITOR`. Users without MFA enrolled are blocked from all features until enrollment is complete.

TOTP secrets are encrypted at rest with `TOTP_ENCRYPTION_KEY`. Recovery codes are shown once and stored only as hashed values.

## TLS

1. Obtain a CA-issued certificate for your domain.
2. Configure your HTTPS reverse proxy (nginx, Caddy, Traefik, or cloud load balancer) with the certificate.
3. Set `SESSION_COOKIE_SECURE=true` in `.env`.
4. Set `CORS_ORIGINS` to the public HTTPS origin only.
5. Set `OIDC_REDIRECT_BASE_URL` to the public HTTPS base URL.

## Data-at-Rest Encryption (SC-28)

At-rest protection of candidate PII is satisfied by FIPS 140-validated volume/disk encryption of the data stores - this is an inherited control provided by your environment, not the application.

Provision encrypted storage for the PostgreSQL and MinIO volumes: encrypted EBS/persistent disks, an encrypted RDS/managed database, LUKS, or equivalent. The application does not perform field-level encryption; do not rely on it for at-rest protection.

## Database Migrations

Alembic migrations run automatically on API container startup:

```bash
docker compose exec api alembic upgrade head
```

To run manually before restart:

```bash
docker compose run --rm api alembic upgrade head
```

## Backups

Create a backup:

```bash
docker compose exec database pg_dump -U selection_board selection_board | gzip > backup-$(date +%Y%m%dT%H%M%S).sql.gz
```

Restore:

```bash
gunzip -c backup-TIMESTAMP.sql.gz | docker compose exec -T database psql -U selection_board selection_board
```

Backups are not a control until a restore has been successfully tested. Test restore into a clean stack before using backups for production recovery.

## OpenSearch Hardening

Set `OPENSEARCH_SECURITY_DISABLED=false` and provision TLS certificates for OpenSearch. Follow the OpenSearch security documentation for your deployment version.

## Final Gate

Before accepting live data, verify all of the following:

- `docker compose ps` shows all containers healthy
- `docker compose exec api curl -s http://localhost:8000/api/v1/health` returns OK
- `pytest` passes in `services/backend`
- `ruff check .` and `ruff format --check .` pass in `services/backend`
- `npx tsc --noEmit` passes in `services/frontend`
- `npm audit --audit-level=high` reports no actionable findings in `services/frontend`
- `SESSION_COOKIE_SECURE=true` is set
- `DEV_AUTH_BYPASS=false` is confirmed
- `OPENSEARCH_SECURITY_DISABLED=false` is confirmed
- TLS is active and the certificate is from a trusted CA
- `CORS_ORIGINS` contains only the production HTTPS origin
- All required secrets are non-placeholder values
- Privileged MFA coverage is 100% in the Security Posture dashboard
- A database backup has been created and a restore has been successfully tested
- The SOC audit log is being forwarded to your SIEM
- `sbom/selection-board.cdx.json` has been reviewed for known-vulnerable components
