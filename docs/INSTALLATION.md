# Installation Guide

This guide covers the supported ways to install and run Candidate Selection Board.

## Choose an Install Path

| Path | Best for | Builds source locally? |
| --- | --- | --- |
| Source-build Docker Compose | Contributors and operators who want local builds | Yes |
| Pull-based Docker Compose from GHCR | Operators who want prebuilt images | No |

Both paths use the same `.env` file and the same container topology. The pull-based path still starts from this repository because it needs the Compose file and bundled nginx config, but it does not build the first-party services locally.

## Requirements

All install paths require:

- Docker Desktop on Windows or macOS, or Docker Engine on Linux
- Docker Compose v2
- 4 GB RAM minimum available to Docker (8 GB recommended for full AI analysis pipeline)

The application runs in Linux containers and works on Windows, macOS, and Linux hosts.

## Files You Must Provide

These files are intentionally not committed to the repository:

- `.env` - secrets and deployment configuration

## Path 1: Source-Build Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/DrDeathLabs/candidate-selection-board.git
cd candidate-selection-board
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and replace every `change-me` and `replace-with-*` placeholder. Required values:

- `POSTGRES_PASSWORD` - strong random password
- `TOTP_ENCRYPTION_KEY` - 32-byte Fernet key

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Build and start the stack

```bash
docker compose up -d --build
```

This starts: reverse proxy, API, Celery worker, parser, OCR, AI gateway, export service, audit service, PostgreSQL, Redis, MinIO, OpenSearch, and virus scanner.

### 4. Seed the first administrator account

```bash
docker compose exec api python -m app.bootstrap seed-admin
```

The generated password is printed once to stdout. Copy it before closing the terminal. If you miss it:

```bash
docker compose logs api | grep -i "bootstrap\|password\|admin"
```

### 5. Open the app

```text
http://127.0.0.1:8610
```

Sign in with username `admin` and the generated password. You will be required to enroll TOTP MFA before accessing any features.

## Path 2: Pull-Based Docker Compose from GHCR

### 1. Clone the repository

```bash
git clone https://github.com/DrDeathLabs/candidate-selection-board.git
cd candidate-selection-board
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and replace every `change-me` and `replace-with-*` placeholder. Optional image pinning:

- `IMAGE_TAG=latest` keeps you on the latest published main-branch image
- `IMAGE_TAG=vX.Y.Z` pins all first-party services to an exact published release

### 3. Pull the first-party images

```bash
docker pull ghcr.io/drdeathlabs/candidate-selection-board-backend:latest
docker pull ghcr.io/drdeathlabs/candidate-selection-board-frontend:latest
docker pull ghcr.io/drdeathlabs/candidate-selection-board-ocr:latest
```

If you pinned `IMAGE_TAG=vX.Y.Z` in `.env`, replace `latest` in the manual `docker pull` commands with that same version tag.

### 4. Start the stack

```bash
docker compose -f docker-compose.pull.yml up -d
```

### 5. Seed the first administrator account

```bash
docker compose -f docker-compose.pull.yml exec api python -m app.bootstrap seed-admin
```

If you miss the generated password:

```bash
docker compose -f docker-compose.pull.yml logs api | grep -i "bootstrap\|password\|admin"
```

### 6. Open the app

```text
http://127.0.0.1:8610
```

If anonymous pulls return `403`, open each published GHCR package once and set its visibility to **Public** in GitHub package settings.

## Production Deployment

For internet-facing use:

1. Use a real domain name with a CA-issued TLS certificate.
2. Put the stack behind a trusted HTTPS reverse proxy such as nginx, Caddy, Traefik, or a cloud load balancer.
3. Set `SESSION_COOKIE_SECURE=true` and `OPENSEARCH_SECURITY_DISABLED=false`.
4. Set `CORS_ORIGINS` to the public HTTPS origin only.
5. Use strong random values for all secrets.
6. Restrict the host firewall to allow only the reverse proxy port inbound.

See [docs/PRODUCTION.md](PRODUCTION.md) for the full checklist.

### Port bindings

By default, Candidate Selection Board binds only to localhost:

```env
HOST_BIND_ADDRESS=127.0.0.1
```

This is safe for local testing or when a host-level reverse proxy is in front. To expose directly, change to `0.0.0.0` only when the host firewall and TLS are fully configured.

## Environment Reference

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL database password |
| `REDIS_PASSWORD` | Redis password (empty = no auth, prod must set) |
| `MINIO_ROOT_PASSWORD` | MinIO object storage password |
| `TOTP_ENCRYPTION_KEY` | 32-byte Fernet key for encrypting TOTP secrets |
| `TOTP_ISSUER_NAME` | Name shown in authenticator apps |
| `SESSION_COOKIE_SECURE` | Set `true` in production (requires HTTPS) |
| `SESSION_IDLE_TIMEOUT_MINUTES` | Idle session timeout (FISMA AC-11, max 15) |
| `SESSION_ABSOLUTE_TIMEOUT_HOURS` | Absolute session timeout (FISMA AC-12, max 8) |
| `MAX_CONCURRENT_SESSIONS` | Sessions per user (FISMA AC-10, default 3) |
| `MAX_FAILED_LOGIN_ATTEMPTS` | Lockout threshold (FISMA AC-7, default 5) |
| `ACCOUNT_LOCKOUT_MINUTES` | Lockout duration (default 30) |
| `PASSWORD_MIN_LENGTH` | Minimum password length (FISMA IA-5, min 14) |
| `PASSWORD_HISTORY_COUNT` | Passwords remembered to prevent reuse (default 5) |
| `PASSWORD_MAX_AGE_DAYS` | Forced rotation interval (default 90) |
| `OIDC_ISSUER_URL` | OIDC provider URL (Login.gov, ADFS, Okta) |
| `OIDC_AUDIENCE` | OIDC JWT audience claim |
| `OIDC_JWKS_URL` | OIDC JWKS endpoint for JWT signature validation |
| `OIDC_GROUP_PREFIX` | Group claim prefix for role mapping |
| `DEV_AUTH_BYPASS` | Set `true` in `.env` for local dev only; never in production |
| `AI_DEFAULT_PROVIDER` | `ollama`, `claude`, or `openai` |
| `CELERY_BROKER_URL` | Redis URL for task queue |
| `CELERY_RESULT_BACKEND` | Redis URL for task results |
| `IMAGE_TAG` | Tag used by `docker-compose.pull.yml` for first-party images |

## Updating

Source-build deployments:

```bash
git pull
docker compose up -d --build
```

Pull-based deployments:

```bash
git pull
docker compose -f docker-compose.pull.yml pull
docker compose -f docker-compose.pull.yml up -d
```

Alembic migrations run automatically on API startup.

## Backup and Restore

### Back up PostgreSQL

```bash
docker compose exec database pg_dump -U selection_board selection_board | gzip > backup-$(date +%Y%m%dT%H%M%S).sql.gz
```

### Restore PostgreSQL

```bash
gunzip -c backup-TIMESTAMP.sql.gz | docker compose exec -T database psql -U selection_board selection_board
```

Test restores into a clean stack before relying on backups for production recovery.

## Troubleshooting

### The app does not load

Check container status:

```bash
docker compose ps
```

Check API logs:

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 reverse-proxy
```

Check health directly:

```bash
docker compose exec api curl -s http://localhost:8000/api/v1/health
```

For pull-based deployments, prefix those commands with `-f docker-compose.pull.yml`.

### 504 through the reverse proxy

The API may be processing long AI analysis tasks. Check if the worker is running and if requests eventually complete. For persistent 504s, check OpenSearch and PostgreSQL connectivity in the API logs.

### Port already in use

Change `APP_HTTP_PORT` in `.env`:

```env
APP_HTTP_PORT=8620
```

Then open `http://127.0.0.1:8620`.

### Database auth fails

Verify `POSTGRES_PASSWORD` matches the value used when the volume was first initialized. If this is a fresh install you can discard:

```bash
docker compose down -v
docker compose up -d --build
```

Then re-run the bootstrap.

### Virus scanner shows unhealthy

ClamAV takes several minutes to download its signature database on first start. The unhealthy status is expected during initialization. File uploads are held until the scanner is ready.
