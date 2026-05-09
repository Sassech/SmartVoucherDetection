"""Tests de api/services/ocr_service.py.

Estrategia: 100% offline usando `httpx.MockTransport`. Inyectamos un
`AsyncClient` configurado con un handler que simula respuestas de
llama-server. Cero red, cero monkeypatching global.

`asyncio_mode = auto` esta seteado en pyproject → no hace falta decorar.
"""

import json

import httpx
import pytest
from fastapi import HTTPException
from tenacity import wait_fixed

from services import ocr_service
from services.ocr_service import CAMPOS_ESPERADOS, extract_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(handler) -> httpx.AsyncClient:
    """AsyncClient con MockTransport — sin red real."""
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://mock-llama",
    )


def _ok_response(body: dict) -> httpx.Response:
    """200 con estructura OpenAI-compatible y `body` serializado en `content`."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(body)}}]},
    )


@pytest.fixture
def fast_retries(monkeypatch):
    """Quita el wait de 1s entre reintentos para tests rapidos.

    Tenacity expone la config del decorador via `func.retry`. Pisamos solo
    `wait` — el resto (stop, retry condition) queda intacto.
    """
    monkeypatch.setattr(
        ocr_service._post_completion.retry, "wait", wait_fixed(0)
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


async def test_extract_fields_happy_path():
    expected = {
        "monto": 1234.56,
        "fecha": "01/05/2026",
        "referencia": "PAGO-123",
        "numero_operacion": "TRX-987654",
        "banco": "BBVA",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # El path debe coincidir con lo que arma _post_completion.
        assert request.url.path == "/v1/chat/completions"
        return _ok_response(expected)

    async with _make_client(handler) as client:
        result = await extract_fields("FAKE_BASE64", client=client)

    assert result == expected


async def test_extract_fields_with_explicit_nulls():
    """Si el modelo devuelve null en algun campo, lo respetamos."""
    body = {
        "monto": 100,
        "fecha": None,
        "referencia": None,
        "numero_operacion": "X-1",
        "banco": None,
    }

    def handler(request):
        return _ok_response(body)

    async with _make_client(handler) as client:
        result = await extract_fields("B64", client=client)

    assert result == body


async def test_missing_keys_filled_with_none():
    """Contrato: las 5 keys SIEMPRE presentes; faltantes → None."""
    body = {"monto": 50, "banco": "Santander"}

    def handler(request):
        return _ok_response(body)

    async with _make_client(handler) as client:
        result = await extract_fields("B64", client=client)

    assert set(result.keys()) == set(CAMPOS_ESPERADOS)
    assert result["monto"] == 50
    assert result["banco"] == "Santander"
    assert result["fecha"] is None
    assert result["referencia"] is None
    assert result["numero_operacion"] is None


# ---------------------------------------------------------------------------
# Estructura del payload
# ---------------------------------------------------------------------------


async def test_payload_structure_openai_compatible():
    """El body que mandamos cumple el schema OpenAI chat/completions multimodal."""
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _ok_response({k: None for k in CAMPOS_ESPERADOS})

    async with _make_client(handler) as client:
        await extract_fields("MY_IMAGE_B64", client=client)

    body = captured["body"]
    assert body["model"] == "GLM-OCR"
    assert body["temperature"] == 0.0
    assert len(body["messages"]) == 1

    msg = body["messages"][0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)

    parts_by_type = {p["type"]: p for p in msg["content"]}
    assert "text" in parts_by_type
    assert "image_url" in parts_by_type
    assert (
        parts_by_type["image_url"]["image_url"]["url"]
        == "data:image/png;base64,MY_IMAGE_B64"
    )


# ---------------------------------------------------------------------------
# Errores transitorios → retry → 503
# ---------------------------------------------------------------------------


async def test_503_on_network_error_after_retries(fast_retries):
    """ConnectError persistente → 3 intentos → HTTPException(503)."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("server down")

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 503
    assert call_count == 3  # 3 intentos exactos


async def test_503_on_upstream_5xx_after_retries(fast_retries):
    """500 persistente → reintenta 3 veces → 503."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="boom")

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 503
    assert call_count == 3


async def test_recovers_after_one_5xx(fast_retries):
    """Si el 1er intento es 500 pero el 2do es 200, devuelve OK (retry funciona)."""
    call_count = 0
    body = {k: None for k in CAMPOS_ESPERADOS} | {"monto": 42}

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, text="warming up")
        return _ok_response(body)

    async with _make_client(handler) as client:
        result = await extract_fields("B64", client=client)

    assert call_count == 2
    assert result["monto"] == 42


# ---------------------------------------------------------------------------
# Errores NO transitorios → SIN retry
# ---------------------------------------------------------------------------


async def test_502_on_4xx_no_retry():
    """4xx → 502 inmediato, NO se reintenta."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, text="bad request")

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 502
    assert call_count == 1  # NO reintenta


async def test_503_on_invalid_json_in_content():
    """Modelo respondio texto crudo en lugar de JSON → 503 sin retry."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "no soy json en absoluto"}}]},
        )

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 503
    assert call_count == 1


async def test_503_on_unexpected_response_structure():
    """Respuesta sin `choices` → 503."""
    def handler(request):
        return httpx.Response(200, json={"weird": "shape"})

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 503


async def test_503_when_content_is_json_but_not_object():
    """`content` es `"[1,2,3]"` → JSON valido pero no dict → 503."""
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[1, 2, 3]"}}]},
        )

    async with _make_client(handler) as client:
        with pytest.raises(HTTPException) as exc_info:
            await extract_fields("B64", client=client)

    assert exc_info.value.status_code == 503
