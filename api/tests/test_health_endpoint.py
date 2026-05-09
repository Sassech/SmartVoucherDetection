"""Tests del endpoint /health (task 1.7.2).

Estrategia: usar `TestClient` de FastAPI con `app.dependency_overrides` para
inyectar una sesion DB controlada y monkeypatch para `cache_service.ping` y
las funciones internas del router. Cero red real, cero Postgres real, cero
Redis real — todos los chequeos son deterministicos.

Casos cubiertos:
- Todos los servicios OK → response 200 con tres `ok=True`.
- llama caido (timeout/error) → 200 con `llama.ok=False`, otros OK.
- DB caida → 200 con `db.ok=False`.
- Redis caido → 200 con `redis.ok=False`.
- Multiples servicios caidos → 200 con flags correspondientes.

Nota: el endpoint debe responder 200 SIEMPRE — el HTTP no refleja salud,
los flags `ok` por servicio si.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi.testclient import TestClient

from database import get_session
from main import app
from routers import health as health_router
from services import cache_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeSession:
    """Sesion mock que responde a `execute(text("SELECT 1"))`.

    Comportamiento configurable via `behavior`:
    - "ok": devuelve un resultado dummy.
    - "error": levanta excepcion.
    - "slow": espera mas que el timeout del check.
    """

    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior

    async def execute(self, *_args, **_kwargs):  # noqa: D401 — mimic SQLAlchemy
        if self.behavior == "error":
            raise RuntimeError("simulated db connection error")
        if self.behavior == "slow":
            await asyncio.sleep(5.0)  # mas que _CHECK_TIMEOUT_S
        return object()  # el endpoint no usa el resultado


def _override_session(behavior: str):
    """Construye un override de `get_session` que yield-ea un FakeSession."""

    async def _gen() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession(behavior)

    return _gen


@pytest.fixture
def client():
    """TestClient con cleanup garantizado de overrides."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def patch_llama_ok(monkeypatch):
    """Mock httpx.AsyncClient para que llama-server `/health` devuelva 200."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    _patch_llama_with_handler(monkeypatch, _handler)


@pytest.fixture
def patch_llama_500(monkeypatch):
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    _patch_llama_with_handler(monkeypatch, _handler)


@pytest.fixture
def patch_llama_network_error(monkeypatch):
    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _patch_llama_with_handler(monkeypatch, _handler)


def _patch_llama_with_handler(monkeypatch, handler) -> None:
    """Reemplaza httpx.AsyncClient en el router por uno con MockTransport.

    El router instancia un `httpx.AsyncClient(base_url=..., timeout=...)`.
    Le inyectamos un transport via `MockTransport` ignorando los kwargs
    de produccion (base_url/timeout) — para tests no importan.
    """
    real_async_client = httpx.AsyncClient

    def _factory(*_args, **kwargs):
        # Conservamos `base_url` porque httpx valida la URL del request final
        # contra ella; descartamos `timeout` (irrelevante para MockTransport).
        return real_async_client(
            transport=httpx.MockTransport(handler),
            base_url=kwargs.get("base_url", "http://mock-llama"),
        )

    monkeypatch.setattr(health_router.httpx, "AsyncClient", _factory)


@pytest.fixture
def patch_redis_ok(monkeypatch):
    async def _ping(timeout_s: float = 1.0) -> bool:  # noqa: ARG001
        return True

    monkeypatch.setattr(cache_service, "ping", _ping)


@pytest.fixture
def patch_redis_down(monkeypatch):
    async def _ping(timeout_s: float = 1.0) -> bool:  # noqa: ARG001
        return False

    monkeypatch.setattr(cache_service, "ping", _ping)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_all_services_ok(client, patch_llama_ok, patch_redis_ok):
    app.dependency_overrides[get_session] = _override_session("ok")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["llama"]["ok"] is True
    assert body["db"]["ok"] is True
    assert body["redis"]["ok"] is True
    # `detail` debe contener latencia con sufijo "ms" en los OK.
    assert body["llama"]["detail"].endswith("ms")
    assert body["db"]["detail"].endswith("ms")
    assert body["redis"]["detail"].endswith("ms")


def test_health_llama_500_marks_only_llama_down(
    client, patch_llama_500, patch_redis_ok
):
    app.dependency_overrides[get_session] = _override_session("ok")

    response = client.get("/health")

    assert response.status_code == 200  # endpoint NUNCA falla por dep caida
    body = response.json()
    assert body["llama"]["ok"] is False
    assert "500" in body["llama"]["detail"]
    assert body["db"]["ok"] is True
    assert body["redis"]["ok"] is True


def test_health_llama_network_error(
    client, patch_llama_network_error, patch_redis_ok
):
    app.dependency_overrides[get_session] = _override_session("ok")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["llama"]["ok"] is False
    # Debe ser network error o unexpected — pero NO 200.
    assert body["llama"]["detail"]


def test_health_db_error_marks_only_db_down(
    client, patch_llama_ok, patch_redis_ok
):
    app.dependency_overrides[get_session] = _override_session("error")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["llama"]["ok"] is True
    assert body["db"]["ok"] is False
    assert "db error" in body["db"]["detail"]
    assert body["redis"]["ok"] is True


def test_health_db_slow_times_out(
    client, patch_llama_ok, patch_redis_ok, monkeypatch
):
    # Bajamos el timeout del check para no esperar 1s en el test.
    monkeypatch.setattr(health_router, "_CHECK_TIMEOUT_S", 0.05)
    app.dependency_overrides[get_session] = _override_session("slow")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"]["ok"] is False
    assert "timeout" in body["db"]["detail"]


def test_health_redis_down_marks_only_redis_down(
    client, patch_llama_ok, patch_redis_down
):
    app.dependency_overrides[get_session] = _override_session("ok")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["llama"]["ok"] is True
    assert body["db"]["ok"] is True
    assert body["redis"]["ok"] is False


def test_health_all_services_down(
    client, patch_llama_network_error, patch_redis_down
):
    app.dependency_overrides[get_session] = _override_session("error")

    response = client.get("/health")

    # Aunque las 3 dependencias esten caidas, el HTTP debe ser 200.
    assert response.status_code == 200
    body = response.json()
    assert body["llama"]["ok"] is False
    assert body["db"]["ok"] is False
    assert body["redis"]["ok"] is False
