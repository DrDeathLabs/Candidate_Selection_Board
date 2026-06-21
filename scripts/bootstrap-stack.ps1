Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Applying database migrations inside the API container..."
docker compose exec -T api alembic upgrade head

Write-Host "Initializing system defaults (expert agents, prompt templates, and provider settings only)..."
docker compose exec -T api python -m app.bootstrap seed-all

Write-Host "Current stack status:"
docker compose ps
