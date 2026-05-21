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
#
# Idempotent: safe to run multiple times. Each run pulls latest images and
# restarts only changed containers.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENVIRONMENT="${1:-staging}"
COMPOSE_FILE="${COMPOSE_FILE:-${HOME}/SmartVoucherDetection/infra/docker-compose.prod.yml}"

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

log "[1/5] Pulling latest images..."
docker compose -f "${COMPOSE_FILE}" pull

log "[2/5] Bringing services up..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

log "[3/5] Waiting 10s for services to stabilize..."
sleep 10

log "[4/5] Running services:"
docker compose -f "${COMPOSE_FILE}" ps

log "[5/5] Health check (api)..."
docker compose -f "${COMPOSE_FILE}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

log "=== Deploy complete | environment=${ENVIRONMENT} | $(ts) ==="
