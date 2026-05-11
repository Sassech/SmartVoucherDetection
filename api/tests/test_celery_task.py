"""Tests for Celery async upload pipeline (D5).

Tests D1 (celery_app imports), D3 (async endpoints), plus Celery task mocking.

Strategy:
- No real broker needed — mock celery_app.send_task and AsyncResult.
- Tests verify endpoint behavior, not Celery internals.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import status
from PIL import Image

from dependencies.auth_api_key import require_api_key
from main import app
from models.seed import SYSTEM_USER_ID


def _make_png(size: tuple[int, int] = (50, 50)) -> bytes:
    """Generate a minimal valid PNG in memory."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(200, 200, 200))
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def async_client():
    """Async client with require_api_key overridden — no DB needed for Celery tests."""
    mock_usuario = MagicMock()
    mock_usuario.id_usuario = SYSTEM_USER_ID
    app.dependency_overrides[require_api_key] = lambda: mock_usuario
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.pop(require_api_key, None)


# ---------------------------------------------------------------------------
# D5-T1: POST /upload-slip/async — valid file → 202 + task_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_async_enqueues_task(async_client):
    """Valid PNG upload → 202 Accepted with task_id and status='queued'."""
    png_bytes = _make_png()
    mock_task = MagicMock()
    mock_task.id = "test-task-uuid-1234"

    with patch("routers.upload_async.celery_app") as mock_celery:
        mock_celery.send_task.return_value = mock_task
        async with async_client as c:
            resp = await c.post(
                "/upload-slip/async",
                files={"file": ("test.png", png_bytes, "image/png")},
            )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    body = resp.json()
    assert body["task_id"] == "test-task-uuid-1234"
    assert body["status"] == "queued"
    mock_celery.send_task.assert_called_once()
    # Verify the task name
    call_args = mock_celery.send_task.call_args
    assert call_args[0][0] == "tasks.process_slip"


# ---------------------------------------------------------------------------
# D5-T2: POST /upload-slip/async — empty file → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_async_empty_file_returns_400(async_client):
    """Empty file body → HTTP 400 before hitting Celery."""
    async with async_client as c:
        resp = await c.post(
            "/upload-slip/async",
            files={"file": ("empty.png", b"", "image/png")},
        )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# D5-T3: POST /upload-slip/async — file > 10MB → 413
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_async_too_large_returns_413(async_client):
    """File larger than 10MB → HTTP 413 before hitting Celery."""
    large_bytes = b"x" * (10 * 1024 * 1024 + 1)
    async with async_client as c:
        resp = await c.post(
            "/upload-slip/async",
            files={"file": ("big.png", large_bytes, "image/png")},
        )

    assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


# ---------------------------------------------------------------------------
# D5-T4: GET /status/{task_id} — unknown task → PENDING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_pending(async_client):
    """Unknown task_id → status=PENDING (Celery default for unknown tasks)."""
    with patch("routers.upload_async.AsyncResult") as mock_ar:
        mock_result = MagicMock()
        mock_result.state = "PENDING"
        mock_result.result = None
        mock_ar.return_value = mock_result
        async with async_client as c:
            resp = await c.get("/status/unknown-task-id-9999")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["task_id"] == "unknown-task-id-9999"
    assert body["status"] == "PENDING"
    assert "result" not in body
    assert "error" not in body


# ---------------------------------------------------------------------------
# D5-T5: GET /status/{task_id} — SUCCESS → result in body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_success(async_client):
    """Completed task → status=SUCCESS with result dict in body."""
    fake_result = {
        "id_comprobante": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        "estado_actual": "valido",
    }
    with patch("routers.upload_async.AsyncResult") as mock_ar:
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.get.return_value = fake_result
        mock_ar.return_value = mock_result
        async with async_client as c:
            resp = await c.get("/status/success-task-id")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "SUCCESS"
    assert body["result"] == fake_result
    assert "error" not in body


# ---------------------------------------------------------------------------
# D5-T6: GET /status/{task_id} — FAILURE → error in body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_failure(async_client):
    """Failed task → status=FAILURE with error message in body."""
    with patch("routers.upload_async.AsyncResult") as mock_ar:
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.result = Exception("OCR service unavailable")
        mock_ar.return_value = mock_result
        async with async_client as c:
            resp = await c.get("/status/failed-task-id")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "FAILURE"
    assert "error" in body
    assert "OCR service unavailable" in body["error"]
    assert "result" not in body


# ---------------------------------------------------------------------------
# D5-T7: celery_app imports without errors (D1 structural test)
# ---------------------------------------------------------------------------


def test_celery_app_imports_and_has_correct_config():
    """celery_app.py imports without errors and has expected config values."""
    from celery_app import celery_app

    assert celery_app.main == "smartvoucher"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert "json" in celery_app.conf.accept_content
    assert celery_app.conf.task_track_started is True
