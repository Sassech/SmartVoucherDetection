#!/usr/bin/env bash
# Wrapper para docker-compose.prod.yml
# Garantiza que el .env de la raíz del repo se pase siempre,
# independientemente del directorio desde donde se llame.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE_FILE="${REPO_ROOT}/infra/docker-compose.prod.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: .env no encontrado en ${ENV_FILE}" >&2
    exit 1
fi

exec docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
