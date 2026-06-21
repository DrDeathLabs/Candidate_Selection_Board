# FISMA Compliance Overview

**System:** Candidate Selection Board
**Impact Level:** FISMA Moderate (self-certified, pre-authorization)
**Last Updated:** 2026-06-19

FISMA compliance features are optional. They are designed for organizations operating under FISMA Moderate requirements and do not need to be configured for non-federal deployments.

---

## Implemented Controls

| Control ID | Control Name | Implementation | Status |
| --- | --- | --- | --- |
| AC-2 | Account Management | Full CRUD at `/admin/users`; roles, activation, lockout | Implemented |
| AC-3 | Access Enforcement | 7 roles enforced on every endpoint via JWT/session | Implemented |
| AC-6 | Least Privilege | Role-scoped endpoints; no privilege elevation path | Implemented |
| AC-7 | Unsuccessful Logon Attempts | 5 attempts → 30-minute lockout; configurable via env | Implemented |
| AC-10 | Concurrent Session Control | Max 3 sessions per user; configurable | Implemented |
| AC-11 | Session Lock | 15-minute idle timeout; configurable | Implemented |
| AC-12 | Session Termination | 8-hour absolute timeout; configurable | Implemented |
| AU-2 | Event Logging | LOGIN, LOGOUT, LOGIN_FAILED, ACCOUNT_LOCKED, PASSWORD_CHANGED, MFA_ENROLLED, CASE_\*, EVAL_\*, ADJUDICATION_\* | Implemented |
| AU-3 | Content of Audit Records | actor_id, session_id, source_ip, timestamp, entity_type, entity_id on all events | Implemented |
| AU-9 | Protection of Audit Information | Append-only audit model; immutable event records | Implemented |
| IA-2 | Identification and Authentication | TOTP MFA (local) + OIDC with PIV/CAC delegation | Implemented |
| IA-5 | Authenticator Management | Argon2id hashing, 14-char minimum, complexity, history (5), 90-day rotation | Implemented |
| SC-8 | Transmission Confidentiality | CSRF double-submit cookie; Secure/HttpOnly session cookies; HTTPS terminated at the reverse proxy (TLS cert provided by deployment) | Implemented |
| SC-28 | Protection of Information at Rest | At-rest encryption via FIPS 140-validated volume/disk encryption of the PostgreSQL and MinIO data stores (provided by the deployment environment) | Implemented (inherited) |
| SI-3 | Malicious Code Protection | ClamAV virus scanner gate on all uploaded documents | Implemented |
| SI-10 | Information Input Validation | Rate limiting on auth endpoints; file type allow-listing; malware scan gate | Implemented |

Controls marked *(inherited)* are satisfied by the deployment environment rather than application code; the corresponding action is listed under Deployment Requirements.

---

## Deployment Requirements

These must be completed before operating with live personnel data:

- [ ] Set `SESSION_COOKIE_SECURE=true` (requires HTTPS on the reverse proxy)
- [ ] Install a TLS certificate on the reverse proxy — satisfies SC-8
- [ ] Provision FIPS-validated encrypted storage volumes for the PostgreSQL and MinIO data stores — satisfies SC-28
- [ ] Set `OPENSEARCH_SECURITY_DISABLED=false` and provision OpenSearch TLS certificates
- [ ] Configure SIEM forwarding for audit events from the audit-service — satisfies AU-9 external retention
- [ ] Automate nightly PostgreSQL backups to offsite storage — satisfies CP-9
- [ ] Set `DEV_AUTH_BYPASS=false` (or leave unset — the code default is `false`)
- [ ] Enforce TOTP MFA enrollment for all privileged accounts before granting access

The following are inherited controls — provided by your own environment, not the application:

- [ ] Sign container images in your CI/CD pipeline (SA-10)
- [ ] Terminate mTLS between internal services via your service mesh or PKI (SC-8)
- [ ] Apply an audit-record retention schedule through your backup / records-management software (AU-11)

See [PRODUCTION.md](PRODUCTION.md) for the full production readiness checklist.

---

## Software Bill of Materials

A complete CycloneDX 1.6 SBOM is published in [`sbom/`](../sbom/). It covers every component — the first-party `backend`, `frontend`, and `ocr` images and all pinned third-party images (nginx, PostgreSQL, Redis, MinIO, OpenSearch, ClamAV) — with exact dependency versions and container OS packages.

- `sbom/selection-board.cdx.json` — merged SBOM for the whole platform
- `sbom/<component>.cdx.json` — per-image SBOMs
- `sbom/thirdparty-images.txt` — pinned third-party image references

The SBOM is regenerated on every push by CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) and attached to each GitHub Release. Regenerate locally with `bash scripts/generate-sbom.sh`.

---

## Data Handled

| PII Category | Source | Stored In |
| --- | --- | --- |
| Full name | Uploaded resume | PostgreSQL, MinIO |
| Email address | Uploaded resume | PostgreSQL |
| Phone number | Uploaded resume | PostgreSQL |
| Mailing address | Uploaded resume | PostgreSQL |
| Employment history | Uploaded resume | PostgreSQL, OpenSearch, MinIO |
| Education history | Uploaded resume | PostgreSQL, OpenSearch, MinIO |
| Veterans preference | Uploaded resume | PostgreSQL |
| Reviewer identity | System account | PostgreSQL |
| Evaluator notes and ratings | System input | PostgreSQL |
| Selection decisions | System output | PostgreSQL, MinIO |

**AI and privacy:** AI analysis extracts evidence from resumes and suggests dimension ratings. All AI-generated ratings are subject to human review and override. Final selection decisions require explicit adjudication by a `SELECTING_OFFICIAL`. AI outputs do not autonomously advance or eliminate candidates.

**On-premise inference:** Set `AI_DEFAULT_PROVIDER=ollama` to keep candidate PII on-premise and avoid transmission to external AI APIs.

**Data store encryption:** PostgreSQL and MinIO volumes must be encrypted at rest by the host OS or cloud provider (FIPS 140-validated volume/disk encryption). This is the SC-28 at-rest control and is provided by the deployment environment.

---

## System Boundary

```
┌─────────────────────────────────────────────────────────────────────┐
│  Authorization Boundary: Candidate Selection Board                  │
│                                                                     │
│  ┌─────────────┐   ┌──────────────────────────────────────────┐    │
│  │   Browser   │   │  Docker Host (127.0.0.1 bind)            │    │
│  │  (User)     │──▶│                                          │    │
│  └─────────────┘   │  ┌──────────────┐  ┌────────────────┐   │    │
│                    │  │ reverse-proxy │  │    frontend    │   │    │
│                    │  │ (nginx:80)   │  │  (React SPA)   │   │    │
│                    │  └──────┬───────┘  └────────────────┘   │    │
│                    │         │                                │    │
│                    │  ┌──────▼───────┐  ┌────────────────┐   │    │
│                    │  │     api      │  │    worker      │   │    │
│                    │  │  (FastAPI)   │  │   (Celery)     │   │    │
│                    │  └──────┬───────┘  └───────┬────────┘   │    │
│                    │         │                   │            │    │
│                    │  ┌──────▼───────────────────▼────────┐  │    │
│                    │  │            Internal Services       │  │    │
│                    │  │  PostgreSQL │ Redis │ MinIO        │  │    │
│                    │  │  OpenSearch │ ClamAV               │  │    │
│                    │  └──────────────────────────────────┘  │    │
│                    │                                          │    │
│                    │  ┌────────────────────────────────────┐  │    │
│                    │  │         AI / Processing Layer       │  │    │
│                    │  │  ai-gateway │ parser │ ocr          │  │    │
│                    │  │  export-service │ audit-service     │  │    │
│                    │  └────────────────────────────────────┘  │    │
│                    └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

External Dependencies (outside boundary):
  - Agency OIDC Provider (Login.gov, ADFS, Okta) — authentication delegation
  - AI Provider (Ollama local / Anthropic / OpenAI / Gemini) — LLM inference
  - Agency SIEM — audit event forwarding (deployment-provided)
```

| Zone | Components | Exposure |
| --- | --- | --- |
| Edge | reverse-proxy, frontend | Host-bound port 8610 (localhost only by default) |
| API | api, worker | Internal Docker network only; direct port 8612 for dev |
| Data | PostgreSQL, Redis, OpenSearch, MinIO | Internal Docker network only |
| Processing | ai-gateway, parser, ocr, export-service, audit-service, ClamAV | Internal Docker network only |

**FISMA Impact Level: Moderate / Moderate / Moderate** — Candidate PII requires confidentiality protection; evaluation and selection records require integrity assurance; availability disruption delays hiring but does not create immediate safety risk.
