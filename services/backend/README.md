# Backend Services

Shared Python codebase for the API, worker, parser, AI gateway, export service, and audit service.

## Entrypoints

- `app.main:app` - core REST API
- `app.parser.main:app` - document parsing boundary
- `app.gateway.main:app` - model gateway
- `app.export.main:app` - export orchestration boundary
- `app.audit.main:app` - audit ingestion API
- `app.workers.celery_app:celery_app` - Celery worker

