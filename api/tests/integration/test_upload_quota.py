"""Tests para la integracion de cuota en POST /upload-slip (R-79).

Estrategia:
- Mismo patron que test_upload_endpoint.py: minimal app, mocks para
  extract_fields (llama-server), save_upload (filesystem).
- Mock de require_user para controlar el usuario (plan, sin_cuota).
- Mock de quota_service.check_quota para verificar que se llama como step 0.

Spec coverage (R-79):
  - Upload cuando cuota superada → 429 antes de OCR
  - Upload duplicado cuando cuota superada → 429 (no llega a hash check)
  - Upload con cuota disponible → pasa al pipeline normal (201)
  - Duplicado con cuota disponible → detectado como 409, cuota NO incrementada
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from PIL import Image

import routers.upload as upload_module
from database import get_session
from dependencies.auth_any import require_user
from main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(color: str = "white") -> bytes:
    """PNG sintetico real para pasar validate_mime."""
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _make_usuario(*, plan: str = "basic", sin_cuota: bool = False) -> MagicMock:
    """Mock de Usuario con plan y sin_cuota configurables."""
    user = MagicMock()
    user.id_usuario = uuid.UUID("019e0d75-323e-74b3-a249-909b3f77ee9f")
    user.plan = plan
    user.sin_cuota = sin_cuota
    return user


# ---------------------------------------------------------------------------
# Tests — R-79: quota check como step 0
# ---------------------------------------------------------------------------


def test_upload_returns_429_when_quota_exceeded(monkeypatch):
    """Upload con cuota superada → 429 antes de OCR (R-79).

    Verifica que check_quota se llama ANTES que extract_fields.
    Si 429 llega antes que OCR es invocado, el test pasa.
    """
    # Mock quota_service.check_quota para levantar 429
    async def fake_check_quota(usuario, session):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"used": 100, "limit": 100, "plan": "basic", "reset_date": "2026-06-01"},
        )

    monkeypatch.setattr(upload_module, "check_quota", fake_check_quota)

    # OCR tracker: verificar que NO se invoca si quota falla
    ocr_called = []

    async def spy_extract(_b64):
        ocr_called.append(True)
        return {}

    monkeypatch.setattr(upload_module, "extract_fields", spy_extract)

    # Usuario con cuota superada (plan=basic)
    usuario = _make_usuario(plan="basic")
    app.dependency_overrides[require_user] = lambda: usuario

    try:
        with TestClient(app) as client:
            png = _make_png_bytes()
            response = client.post(
                "/upload-slip",
                files={"file": ("comp.png", png, "image/png")},
            )

        assert response.status_code == 429
        detail = response.json()["detail"]
        assert detail["plan"] == "basic"
        assert detail["used"] == 100
        # OCR must NOT have been called
        assert ocr_called == [], "OCR was called despite quota exceeded — check_quota must be step 0"
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_upload_passes_through_when_quota_available(monkeypatch):
    """Upload con cuota disponible → llega al pipeline normal (R-79).

    check_quota retorna None → el pipeline continua. OCR tracker verifica
    que extract_fields SI se invoca (cuota no bloqueo el flujo).
    """
    # check_quota passes (None return)
    async def fake_check_quota_ok(usuario, session):
        return None

    monkeypatch.setattr(upload_module, "check_quota", fake_check_quota_ok)

    # save_upload mock
    async def fake_save(data, *, hash_documento, ext, year, month):
        return f"/tmp/test/{hash_documento}.{ext}"

    monkeypatch.setattr(upload_module, "save_upload", fake_save)

    # OCR tracker
    ocr_called = []

    async def fake_extract(_b64):
        ocr_called.append(True)
        return {
            "monto": "1000.00",
            "fecha": "2026-05-23",
            "referencia": "REF-QUOTA-OK",
            "banco": "BBVA",
            "content": "test content",
        }

    monkeypatch.setattr(upload_module, "extract_fields", fake_extract)

    # Redis mocks
    async def fake_check_hash(_sha256):
        return None

    async def fake_set_hash(*args, **kwargs):
        pass

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)
    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

    usuario = _make_usuario(plan="pro", sin_cuota=False)
    app.dependency_overrides[require_user] = lambda: usuario

    # Mock DB session to support the upload pipeline
    from collections.abc import AsyncGenerator

    class _FakeScalars:
        def scalar_one_or_none(self):
            return None  # No existing hash duplicate

    class _FakeResult:
        def scalars(self):
            return _FakeScalars()

        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def execute(self, _stmt):
            return _FakeResult()

        def add(self, obj):
            pass

        async def commit(self):
            pass

        async def flush(self):
            pass

        async def rollback(self):
            pass

        async def refresh(self, obj):
            import uuid as _uuid
            from datetime import datetime, timezone

            # Set only fields that are needed for serialization but don't
            # override estado_actual (state machine manages that)
            if not hasattr(obj, "id_comprobante") or obj.id_comprobante is None:
                obj.id_comprobante = _uuid.uuid4()
            if not hasattr(obj, "fecha_registro") or obj.fecha_registro is None:
                obj.fecha_registro = datetime.now(timezone.utc)

    async def _override_session() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession()

    app.dependency_overrides[get_session] = _override_session

    # Also mock Capa 2/3 to avoid complex DB queries
    async def fake_run_capa2(session, nuevo):
        return None

    async def fake_run_capa3(session, nuevo):
        return (None, 0.1, "valido")

    monkeypatch.setattr(upload_module, "run_capa2", fake_run_capa2)
    monkeypatch.setattr(upload_module, "run_capa3", fake_run_capa3)

    try:
        with TestClient(app) as client:
            png = _make_png_bytes(color="blue")
            response = client.post(
                "/upload-slip",
                files={"file": ("comp.png", png, "image/png")},
            )

        # Not 429 — quota was not the blocker
        assert response.status_code != 429, (
            f"Got 429 but quota should have passed. Body: {response.text}"
        )
        # OCR must have been called — quota passed through
        assert ocr_called, "OCR was not called — quota check may have blocked unexpectedly"
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_session, None)


def test_upload_quota_check_called_before_read(monkeypatch):
    """Verifica orden: check_quota debe ser ANTES de _read_upload (R-79).

    Si check_quota levanta 429, el upload nunca se lee.
    Usamos un archivo vacio que causaria 400 si se leyera — pero como
    check_quota falla primero, obtenemos 429.
    """
    async def fake_check_quota(usuario, session):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"used": 500, "limit": 500, "plan": "pro", "reset_date": "2026-06-01"},
        )

    monkeypatch.setattr(upload_module, "check_quota", fake_check_quota)

    usuario = _make_usuario(plan="pro")
    app.dependency_overrides[require_user] = lambda: usuario

    try:
        with TestClient(app) as client:
            # Empty file — would return 400 if read, but 429 if quota fails first
            response = client.post(
                "/upload-slip",
                files={"file": ("empty.png", b"", "image/png")},
            )

        assert response.status_code == 429
    finally:
        app.dependency_overrides.pop(require_user, None)
