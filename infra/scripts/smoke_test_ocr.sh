#!/usr/bin/env bash
# ============================================================================
# smoke_test_ocr.sh — prueba de humo para llama-server con GLM-OCR
#
# Envía una imagen sintética de comprobante al endpoint multimodal y valida
# que responda en <5s con texto extraído > 0 caracteres.
#
# Uso:
#   ./infra/scripts/smoke_test_ocr.sh                  # imagen default
#   ./infra/scripts/smoke_test_ocr.sh ruta/img.png     # imagen custom
#
# Requisitos:
#   - llama-server corriendo (./llama.cpp/GLM-OCR.sh)
#   - curl, jq, base64, awk
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_IMAGE="${SCRIPT_DIR}/fixtures/sample_comprobante.png"
readonly LLAMA_URL="${LLAMA_SERVER_URL:-http://localhost:8080}"
readonly TIMEOUT_SEC=30
readonly TARGET_SEC=5
readonly MODEL="GLM-OCR"

IMAGE_PATH="${1:-${DEFAULT_IMAGE}}"

# --- Pre-flight --------------------------------------------------------------
for cmd in curl jq base64 awk; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ERROR] Falta la herramienta requerida: ${cmd}" >&2
    exit 2
  fi
done

if [[ ! -f "${IMAGE_PATH}" ]]; then
  echo "[ERROR] No se encontró la imagen: ${IMAGE_PATH}" >&2
  echo "  Generala con: uv run --project api python infra/scripts/generate_sample.py" >&2
  exit 2
fi

# Health check --------------------------------------------------------------
if ! curl -fsS -m 5 "${LLAMA_URL}/health" >/dev/null; then
  echo "[ERROR] llama-server no responde en ${LLAMA_URL}/health" >&2
  echo "  Levantalo con: ./llama.cpp/GLM-OCR.sh" >&2
  exit 3
fi

# --- Encode + payload --------------------------------------------------------
MIME="$(file -b --mime-type "${IMAGE_PATH}")"
B64="$(base64 -w0 "${IMAGE_PATH}")"

read -r -d '' PROMPT <<'EOF' || true
Extrae todo el texto visible de este comprobante bancario.
Responde solo con el texto plano, sin comentarios ni markdown.
EOF

PAYLOAD="$(jq -n \
  --arg model "${MODEL}" \
  --arg prompt "${PROMPT}" \
  --arg uri "data:${MIME};base64,${B64}" \
  '{
    model: $model,
    temperature: 0,
    max_tokens: 512,
    messages: [{
      role: "user",
      content: [
        {type: "text", text: $prompt},
        {type: "image_url", image_url: {url: $uri}}
      ]
    }]
  }')"

# --- Request -----------------------------------------------------------------
echo "[INFO] Enviando ${IMAGE_PATH} (${MIME}) a ${LLAMA_URL}/v1/chat/completions"
START_NS="$(date +%s%N)"

HTTP_BODY="$(curl -fsS -m "${TIMEOUT_SEC}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${LLAMA_URL}/v1/chat/completions")"

END_NS="$(date +%s%N)"
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
ELAPSED_S=$(awk "BEGIN { printf \"%.2f\", ${ELAPSED_MS}/1000 }")

# --- Parse + validate --------------------------------------------------------
TEXT="$(echo "${HTTP_BODY}" | jq -r '.choices[0].message.content // empty')"
TOKENS_OUT="$(echo "${HTTP_BODY}" | jq -r '.usage.completion_tokens // 0')"

if [[ -z "${TEXT}" ]]; then
  echo "[FAIL] La respuesta no contiene texto." >&2
  echo "${HTTP_BODY}" | jq . >&2 || echo "${HTTP_BODY}" >&2
  exit 4
fi

PREVIEW="$(echo "${TEXT}" | tr '\n' ' ' | awk '{ if (length($0) > 200) print substr($0, 1, 200) "..."; else print $0 }')"

echo "[INFO] Tokens generados: ${TOKENS_OUT} | tiempo: ${ELAPSED_S}s"
echo "OK — texto extraído: ${PREVIEW}"

# Status final según target de 5s.
if (( ELAPSED_MS > TARGET_SEC * 1000 )); then
  echo "[WARN] El tiempo (${ELAPSED_S}s) supera el target de ${TARGET_SEC}s." >&2
  exit 1
fi
exit 0
