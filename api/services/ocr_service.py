"""Servicio OCR — cliente async hacia llama-server (modelo GLM-OCR).

Responsabilidad UNICA: tomar una imagen en base64, mandarsela al endpoint
OpenAI-compatible de llama-server con el prompt del plan §1.3, y devolver un
dict con los 5 campos crudos del comprobante. NO normaliza nada — eso vive
en `parser_service.py` (seccion 1.5 del PROGRESO).

Politica de errores (decision conservadora — Stripe/AWS-style):
- Retry SOLO en errores transitorios: red caida o upstream 5xx.
- 4xx → 502 inmediato (request mal armado, reintentar no arregla nada).
- JSON malformado en `content` → 503 (el modelo "alucino" texto basura;
  reintentar con misma temperatura no garantiza fix).
- Si tras N intentos sigue fallando → `HTTPException(503)`.

Inyeccion de cliente:
La funcion `extract_fields` acepta opcionalmente un `httpx.AsyncClient` para
permitir testear con `MockTransport` sin tocar red ni monkeypatch global.
En produccion, si no se pasa cliente, se crea uno con la config de settings.
"""

import json
from typing import Any

import httpx
from fastapi import HTTPException, status
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from config import settings

# Prompt literal del plan_desarrollo.md §1.3 — actualizado 2026-05-18.
# Cambio v2: agregado campo "importe_base" para capturar el monto neto antes
# de comisión en tickets OXXO, Banorte y similares donde hay dos valores
# numéricos: el monto base y el total con comisión incluida.
# Regla: "monto" = total cobrado (incluyendo comisión si la hay),
#        "importe_base" = monto neto transferido sin comisión (null si no aplica).
OCR_PROMPT = """Analiza esta imagen de comprobante bancario y extrae los siguientes campos en JSON:

{
  "monto": número decimal (total cobrado, incluyendo comisión si la hay),
  "importe_base": número decimal (monto neto transferido sin comisión; null si no hay comisión separada),
  "fecha": string en formato DD/MM/YYYY,
  "hora": string en formato HH:MM,
  "referencia": string,
  "numero_operacion": string,
  "banco": string
}

Si un campo no es visible, usa null. Responde SOLO el JSON, sin texto adicional."""

# Las 7 keys que esperamos en el JSON de respuesta. Si el modelo omite alguna,
# la rellenamos con None (no rompemos el contrato hacia el caller).
CAMPOS_ESPERADOS: tuple[str, ...] = (
    "monto",
    "importe_base",
    "fecha",
    "hora",
    "referencia",
    "numero_operacion",
    "banco",
)


class _RetryableError(Exception):
    """Marker interno: errores transitorios (red, 5xx) que merecen retry.

    NO debe escapar del modulo: siempre se traduce a HTTPException(503) en
    el orquestador `extract_fields`.
    """


def _build_payload(img_b64: str) -> dict[str, Any]:
    """Arma el body OpenAI-compatible para `/v1/chat/completions`.

    El campo `image_url.url` usa el esquema `data:image/png;base64,<...>`
    que llama-server (con mmproj cargado) interpreta como input visual.
    `temperature=0` para reducir alucinaciones en la extraccion estructurada.
    """
    return {
        "model": settings.llama_model_alias,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 512,
        "temperature": 0.0,
    }


@retry(
    stop=stop_after_attempt(settings.llama_max_retries),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(_RetryableError),
    reraise=True,
)
async def _post_completion(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST al endpoint chat/completions con politica de retry transitoria.

    Raises:
        _RetryableError: red caida o upstream 5xx (sera reintentado).
        HTTPException(502): 4xx (NO reintenta — contrato roto).
    """
    try:
        response = await client.post("/v1/chat/completions", json=payload)
    except httpx.RequestError as exc:
        # Timeouts, DNS, connection refused, etc. → reintenta.
        raise _RetryableError(f"network error: {exc}") from exc

    if response.status_code >= 500:
        raise _RetryableError(f"upstream {response.status_code}")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"llama-server rechazo el request ({response.status_code})",
        )
    return response.json()


async def extract_fields(
    img_b64: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Extrae los 5 campos crudos de un comprobante via llama-server.

    Args:
        img_b64: imagen en base64 (string puro, SIN prefijo `data:`).
        client: opcional — para inyectar un `AsyncClient` con `MockTransport`
            en tests. En produccion se crea uno nuevo y se cierra al salir.

    Returns:
        dict con keys exactas de `CAMPOS_ESPERADOS`. Valores son los crudos
        del modelo (puede ser str, number, None) — la normalizacion vive en
        parser_service.

    Raises:
        HTTPException(503): tras agotar reintentos por red/5xx, o si el
            cuerpo de respuesta no es JSON parseable / estructura inesperada.
        HTTPException(502): si llama-server respondio 4xx (request invalido).
    """
    payload = _build_payload(img_b64)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            base_url=settings.llama_server_url,
            timeout=settings.llama_timeout_s,
        )
    assert client is not None  # narrow para type checker

    try:
        try:
            data = await _post_completion(client, payload)
        except _RetryableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"llama-server no disponible: {exc}",
            ) from exc

        # Estructura OpenAI-compatible: {choices:[{message:{content:"..."}}]}.
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="llama-server devolvio una estructura inesperada",
            ) from exc

        # Algunos modelos envuelven el JSON en backticks markdown
        # (```json ... ```). Limpiamos antes de parsear.
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            # Quitar primera línea (```json) y última (```)
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="llama-server no devolvio JSON valido",
            ) from exc

        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="llama-server devolvio JSON pero no es un objeto",
            )

        # Garantia de contrato: las 5 keys siempre presentes (None si faltan).
        return {key: parsed.get(key) for key in CAMPOS_ESPERADOS}
    finally:
        if own_client:
            await client.aclose()
