#!/usr/bin/env bash
# infra/scripts/deploy.sh
#
# Deploy SmartVoucherDetection services via Docker Compose.
# Usage:
#   bash ~/SmartVoucherDetection/infra/scripts/deploy.sh [staging|production]
#
# Make executable: chmod +x ~/SmartVoucherDetection/infra/scripts/deploy.sh
#
# Required env vars (set before calling):
#   COMPOSE_FILE  — path to docker-compose.prod.yml
#                   (default: ~/SmartVoucherDetection/infra/docker-compose.prod.yml)
#   SKIP_BUILD    — set to "1" to skip --build (use cached images)
#
# Idempotent: safe to run multiple times. Each run rebuilds local images
# (using BuildKit cache) and restarts only changed containers.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENVIRONMENT="${1:-staging}"
COMPOSE_FILE="${COMPOSE_FILE:-$(cd "$(dirname "$0")/../.." && pwd)/infra/docker-compose.prod.yml}"
SKIP_BUILD="${SKIP_BUILD:-0}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ts() { date '+%Y-%m-%d %H:%M:%S'; }

log()  { echo "[$(ts)] $*"; }
fail() { echo "[$(ts)] ERROR: $*" >&2; }

on_failure() {
    local exit_code=$?
    fail "Deploy failed (exit code ${exit_code}). Last 50 lines of api logs:"
    docker compose -f "${COMPOSE_FILE}" logs --tail=50 api || true
    exit 1
}

trap on_failure ERR

# ---------------------------------------------------------------------------
# Validate environment argument
# ---------------------------------------------------------------------------
if [[ "${ENVIRONMENT}" != "staging" && "${ENVIRONMENT}" != "production" ]]; then
    fail "Invalid environment '${ENVIRONMENT}'. Must be 'staging' or 'production'."
    exit 1
fi

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
log "=== Deploy start | environment=${ENVIRONMENT} | compose=${COMPOSE_FILE} ==="

# Pull only external/pre-built images (postgres, redis, nginx).
# Local services (api, webapp, celery-worker) are built from source — pull
# would be a no-op for them and can error when no registry is configured.
log "[1/6] Pulling external images (postgres, redis, nginx)..."
docker compose -f "${COMPOSE_FILE}" pull postgres redis nginx || true

if [[ "${SKIP_BUILD}" == "1" ]]; then
    log "[2/6] Skipping build (SKIP_BUILD=1) — using cached images."
else
    log "[2/6] Building local images (BuildKit cache active)..."
    DOCKER_BUILDKIT=1 docker compose -f "${COMPOSE_FILE}" build \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        api webapp celery-worker
fi

log "[3/6] Bringing services up..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

log "[4/6] Waiting 10s for services to stabilize..."
sleep 10

log "[5/6] Running services:"
docker compose -f "${COMPOSE_FILE}" ps

log "[6/6] Health check (api)..."
docker compose -f "${COMPOSE_FILE}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

log "=== Deploy complete | environment=${ENVIRONMENT} | $(ts) ==="
