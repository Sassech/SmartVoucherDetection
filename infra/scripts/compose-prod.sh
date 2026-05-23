#!/usr/bin/env bash
# Wrapper para docker-compose.prod.yml
# Garantiza que el .env de la raíz del repo se pase siempre,
# independientemente del directorio desde donde se llame.
#
# Post-deploy: si el comando incluye "up" y "--build", purga el caché de
# Cloudflare automáticamente para que los nuevos assets sean servidos.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE_FILE="${REPO_ROOT}/infra/docker-compose.prod.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: .env no encontrado en ${ENV_FILE}" >&2
    exit 1
fi

# Cargar vars del .env para usarlas en este script (purge)
set -o allexport
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +o allexport

# Ejecutar docker compose con todos los args originales
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
COMPOSE_EXIT=$?

# Purgar caché de Cloudflare solo si el comando fue "up ... --build"
HAS_UP=false
HAS_BUILD=false
for arg in "$@"; do
    [[ "${arg}" == "up" ]] && HAS_UP=true
    [[ "${arg}" == "--build" ]] && HAS_BUILD=true
done

if [[ "${HAS_UP}" == true && "${HAS_BUILD}" == true ]]; then
    if [[ -z "${CF_ZONE_ID:-}" || -z "${CF_API_TOKEN:-}" ]]; then
        echo "⚠️  CF_ZONE_ID o CF_API_TOKEN no configurados — saltando purge de Cloudflare." >&2
    else
        echo "🔄 Purgando caché de Cloudflare para zona ${CF_ZONE_ID}..."
        HTTP_STATUS=$(curl -s -o /tmp/cf_purge_response.json -w "%{http_code}" \
            -X POST "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/purge_cache" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data '{"purge_everything":true}')

        if [[ "${HTTP_STATUS}" == "200" ]]; then
            echo "✅ Caché de Cloudflare purgado exitosamente."
        else
            echo "❌ Error al purgar caché (HTTP ${HTTP_STATUS}):" >&2
            cat /tmp/cf_purge_response.json >&2
        fi
        rm -f /tmp/cf_purge_response.json
    fi
fi

exit "${COMPOSE_EXIT}"
