"""Tests de api/services/cache_service.py.

Estrategia: monkeypatcheamos `redis.asyncio.from_url` para devolver un
fake client con el comportamiento que cada test necesite. Cero red, cero
Redis real corriendo.

Lo critico de este modulo es que `ping()` NUNCA levanta excepcion — el
endpoint /health depende de eso. Asi que la mayoria de los tests verifican
que distintos modos de falla (timeout, RedisError, errores raros) retornan
`False` en lugar de propagar.
"""

from __future__ import annotations

import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from services import cache_service


@pytest.fixture(autouse=True)
def _reset_client():
    """Cada test arranca con `_client=None` para no contaminar entre tests."""
    cache_service._client = None
    yield
    cache_service._client = None


class _FakeRedis:
    """Cliente Redis fake con comportamiento parametrizado."""

    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior
        self.closed = False

    async def ping(self) -> bool:
        if self.behavior == "ok":
            return True
        if self.behavior == "false":
            # Algun caller raro podria devolver False sin levantar.
            return False
        if self.behavior == "slow":
            await asyncio.sleep(5.0)
            return True
        if self.behavior == "redis_error":
            raise RedisConnectionError("simulated connection refused")
        if self.behavior == "redis_timeout":
            raise RedisTimeoutError("simulated socket timeout")
        if self.behavior == "unexpected":
            raise RuntimeError("simulated unexpected error")
        raise AssertionError(f"unknown behavior: {self.behavior}")

    async def aclose(self) -> None:
        self.closed = True


def _patch_redis(monkeypatch, behavior: str) -> _FakeRedis:
    """Hace que `redis_async.from_url` devuelva un FakeRedis."""
    fake = _FakeRedis(behavior)

    def _from_url(*_args, **_kwargs):
        return fake

    monkeypatch.setattr(cache_service.redis_async, "from_url", _from_url)
    return fake


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_ping_returns_true_when_redis_responds(monkeypatch):
    _patch_redis(monkeypatch, "ok")
    assert await cache_service.ping() is True


async def test_ping_caches_client_across_calls(monkeypatch):
    fake = _patch_redis(monkeypatch, "ok")
    await cache_service.ping()
    await cache_service.ping()
    # Si no estuviera cacheado, _client se sobreescribiria pero seria el mismo
    # fake (porque el factory siempre retorna el mismo objeto). Verificamos
    # via referencia identica.
    assert cache_service._client is fake


# ---------------------------------------------------------------------------
# Modos de falla — `ping` NUNCA levanta
# ---------------------------------------------------------------------------


async def test_ping_returns_false_on_redis_connection_error(monkeypatch):
    _patch_redis(monkeypatch, "redis_error")
    assert await cache_service.ping() is False


async def test_ping_returns_false_on_redis_timeout_error(monkeypatch):
    _patch_redis(monkeypatch, "redis_timeout")
    assert await cache_service.ping() is False


async def test_ping_returns_false_on_unexpected_exception(monkeypatch):
    _patch_redis(monkeypatch, "unexpected")
    assert await cache_service.ping() is False


async def test_ping_returns_false_on_asyncio_timeout(monkeypatch):
    _patch_redis(monkeypatch, "slow")
    # timeout corto para no esperar 5s
    assert await cache_service.ping(timeout_s=0.05) is False


async def test_ping_propagates_falsy_response(monkeypatch):
    """Si el cliente devuelve False sin levantar, lo respetamos."""
    _patch_redis(monkeypatch, "false")
    assert await cache_service.ping() is False


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


async def test_close_resets_client(monkeypatch):
    fake = _patch_redis(monkeypatch, "ok")
    await cache_service.ping()
    assert cache_service._client is fake

    await cache_service.close()

    assert cache_service._client is None
    assert fake.closed is True


async def test_close_is_idempotent(monkeypatch):
    _patch_redis(monkeypatch, "ok")
    await cache_service.close()  # nunca se inicializo
    await cache_service.close()  # llamarlo de nuevo
    # No debe levantar nada — eso es todo lo que pedimos.
