"""Tests de api/services/cache_service.py.

Estrategia: monkeypatcheamos `redis.asyncio.from_url` para devolver un
fake client con el comportamiento que cada test necesite. Cero red, cero
Redis real corriendo.

Lo critico de este modulo es que `ping()` NUNCA levanta excepcion — el
endpoint /health depende de eso. Asi que la mayoria de los tests verifican
que distintos modos de falla (timeout, RedisError, errores raros) retornan
`False` en lugar de propagar.

B1 (Fase 2): `check_hash` y `set_hash` siguen el mismo patron de no-raise.
"""

from __future__ import annotations

import asyncio
import uuid

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
    """Cliente Redis fake con comportamiento parametrizado.

    B1: agrega soporte para GET (check_hash) y SET (set_hash).
    """

    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior
        self.closed = False
        # Para inspeccion en tests de set_hash:
        self.set_calls: list[tuple] = []
        # Valor que devuelve GET (check_hash):
        self._get_value: bytes | None = None

    def configure_get(self, value: bytes | None) -> None:
        """Configura el valor que devuelve GET."""
        self._get_value = value

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

    async def get(self, key: str) -> bytes | None:
        if self.behavior == "redis_error":
            raise RedisConnectionError("simulated connection refused")
        if self.behavior == "unexpected":
            raise RuntimeError("simulated unexpected error")
        return self._get_value

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        if self.behavior == "redis_error":
            raise RedisConnectionError("simulated connection refused")
        if self.behavior == "unexpected":
            raise RuntimeError("simulated unexpected error")
        self.set_calls.append((key, value, ex))

    async def aclose(self) -> None:
        self.closed = True


def _patch_redis(monkeypatch, behavior: str = "ok") -> _FakeRedis:
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


# ---------------------------------------------------------------------------
# B1: check_hash — Capa 1 Redis lookup
# ---------------------------------------------------------------------------


async def test_check_hash_hit_returns_uuid(monkeypatch):
    """CAP-03 Scenario 1: hash en Redis → retorna el UUID correctamente."""
    comp_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    fake = _patch_redis(monkeypatch, "ok")
    fake.configure_get(str(comp_id).encode())

    result = await cache_service.check_hash("abc123deadbeef")

    assert result == comp_id


async def test_check_hash_miss_returns_none(monkeypatch):
    """CAP-03 Scenario 2: hash no en Redis → retorna None."""
    fake = _patch_redis(monkeypatch, "ok")
    fake.configure_get(None)

    result = await cache_service.check_hash("nohash0000")

    assert result is None


async def test_check_hash_redis_error_returns_none_never_raises(monkeypatch):
    """CAP-03 Scenario 3: Redis caido → retorna None sin propagar excepcion."""
    _patch_redis(monkeypatch, "redis_error")

    result = await cache_service.check_hash("somehash")

    # Must not raise and must return None (fall-through to Capa 2)
    assert result is None


async def test_check_hash_unexpected_error_returns_none(monkeypatch):
    """Cualquier excepcion inesperada → retorna None (defensivo)."""
    _patch_redis(monkeypatch, "unexpected")

    result = await cache_service.check_hash("somehash")

    assert result is None


async def test_check_hash_key_format(monkeypatch):
    """CAP-03 Constraint: la clave debe ser exactamente `comp:hash:{sha256}`."""
    comp_id = uuid.UUID("aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb")
    sha256 = "cafebabe0000" * 5  # 60 chars (representativo)
    fake = _patch_redis(monkeypatch, "ok")

    # Capturamos la clave que se pasa a GET sobreescribiendo el metodo
    captured_keys: list[str] = []

    async def tracking_get(key: str) -> bytes | None:
        captured_keys.append(key)
        return str(comp_id).encode()

    fake.get = tracking_get  # type: ignore[method-assign]

    await cache_service.check_hash(sha256)

    assert len(captured_keys) == 1
    assert captured_keys[0] == f"comp:hash:{sha256}"


async def test_check_hash_decodes_bytes_value(monkeypatch):
    """El valor almacenado en Redis son bytes → debe decodificar correctamente."""
    comp_id = uuid.UUID("deadbeef-dead-beef-dead-beefdeadbeef")
    fake = _patch_redis(monkeypatch, "ok")
    # Valor como bytes (el patron real con decode_responses=False)
    fake.configure_get(str(comp_id).encode("utf-8"))

    result = await cache_service.check_hash("hashvalue")

    assert result == comp_id


# ---------------------------------------------------------------------------
# B1: set_hash — fire-and-forget con TTL
# ---------------------------------------------------------------------------


async def test_set_hash_success_calls_redis_set_with_correct_args(monkeypatch):
    """CAP-03 Scenario 4: set_hash almacena clave correcta con TTL 7 dias."""
    comp_id = uuid.UUID("11111111-2222-3333-4444-555566667777")
    sha256 = "deadbeef" * 8  # 64 chars
    fake = _patch_redis(monkeypatch, "ok")

    await cache_service.set_hash(sha256, comp_id)

    assert len(fake.set_calls) == 1
    key, value, ex = fake.set_calls[0]
    assert key == f"comp:hash:{sha256}"
    assert value == str(comp_id)
    assert ex == 7 * 86400  # 604800 segundos


async def test_set_hash_custom_ttl(monkeypatch):
    """set_hash acepta ttl_days personalizado."""
    comp_id = uuid.UUID("aaaabbbb-1111-2222-3333-ccccddddeeee")
    fake = _patch_redis(monkeypatch, "ok")

    await cache_service.set_hash("myhash", comp_id, ttl_days=3)

    assert len(fake.set_calls) == 1
    _, _, ex = fake.set_calls[0]
    assert ex == 3 * 86400


async def test_set_hash_redis_error_does_not_raise(monkeypatch):
    """CAP-03 Scenario 5: Redis caido → no propaga excepcion (fire-and-forget)."""
    comp_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    _patch_redis(monkeypatch, "redis_error")

    # Debe completar sin levantar
    await cache_service.set_hash("somehash", comp_id)
    # Si llegamos aqui, paso.


async def test_set_hash_unexpected_error_does_not_raise(monkeypatch):
    """Cualquier error inesperado en set_hash → swallowed silenciosamente."""
    comp_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    _patch_redis(monkeypatch, "unexpected")

    # Debe completar sin levantar
    await cache_service.set_hash("anyhash", comp_id)
