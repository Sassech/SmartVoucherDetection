"""Tests E2E del endpoint `POST /upload-slip` (task 1.8.2).

Estrategia:
- Postgres REAL via fixtures `db_session` + `client` del conftest
  (transaccion que rollbackea, no contamina la DB local).
- llama-server MOCKEADO: monkeypatch de `routers.upload.extract_fields` —
  no queremos que la suite dependa de un servicio externo. Suficientemente
  E2E porque el resto del pipeline (validate_mime / preprocess / parser /
  ORM / commit) corre real.
- Filesystem MOCKEADO: monkeypatch de `routers.upload.save_upload` — los
  tests no deben dejar archivos en `data/uploads/`. La integracion real
  con storage_service se cubre en `test_storage_service.py`.

Casos:
1. happy path → 201, body bien armado, fila en DB.
2. MIME no soportado → 400.
3. >10MB → 413 (size se valida ANTES que MIME).
4. hash ya existe → 409 con `id_comprobante` existente.
5. OCR cae con 503 → propaga 503.
6. archivo vacio → 400.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest
from fastapi import HTTPException, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import routers.upload as upload_module
from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID
from services.parser_service import compute_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(
    *, color: str = "white", size: tuple[int, int] = (200, 100)
) -> bytes:
    """PNG sintetico — bytes reales que pasan validate_mime (libmagic)
    y son procesables por OpenCV. No importa el contenido: el OCR se mockea."""
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _ocr_payload(**overrides: Any) -> dict[str, Any]:
    """Dict crudo que normalmente devolveria `extract_fields`. Sobrescribible."""
    base = {
        "monto": "1234.56",
        "fecha": "2026-05-01",
        "referencia": "REF-TEST-001",
        "numero_operacion": "OP-9999",
        "banco": "BBVA",
        "content": "Texto OCR extraido del comprobante de prueba",
    }
    base.update(overrides)
    return base


@pytest.fixture
def patched_save(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Reemplaza `save_upload` por una funcion async que NO toca disco.

    Devuelve la lista de paths "guardados" para inspeccion en asserts.
    """
    saved: list[str] = []

    async def fake_save(
        data: bytes,
        *,
        hash_documento: str,
        ext: str,
        year: int,
        month: int,
    ) -> str:
        path = f"/tmp/test-uploads/{year}/{month:02d}/{hash_documento}.{ext}"
        saved.append(path)
        return path

    monkeypatch.setattr(upload_module, "save_upload", fake_save)
    return saved


@pytest.fixture
def patched_ocr_ok(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`extract_fields` devuelve un payload feliz. Mutable para que el
    test pueda alterar campos antes del request si quisiera."""
    payload = _ocr_payload()

    async def fake_extract(_b64: str) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(upload_module, "extract_fields", fake_extract)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_upload_happy_path_returns_201_and_persists_row(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    png = _make_png_bytes()
    expected_hash = compute_hash(png)

    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["hash_documento"] == expected_hash
    assert body["estado_actual"] == "recibido"
    assert body["campos_extraidos"]["banco"] == "BBVA"
    assert body["campos_extraidos"]["referencia"] == "REF-TEST-001"
    # save_upload mock recibio la llamada
    assert len(patched_save) == 1 and expected_hash in patched_save[0]

    # Fila persistida en la transaccion del test
    row = (
        await db_session.execute(
            select(Comprobante).where(Comprobante.hash_documento == expected_hash)
        )
    ).scalar_one()
    assert row.id_usuario == SYSTEM_USER_ID
    assert row.estado_actual == "recibido"
    assert row.banco == "BBVA"
    # A1: texto_extraido debe persistirse desde crudos["content"].
    assert row.texto_extraido == "Texto OCR extraido del comprobante de prueba"


async def test_upload_rejects_invalid_mime_with_400(
    client: httpx.AsyncClient,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    # Texto plano: libmagic lo detecta como text/plain → fuera del whitelist.
    resp = await client.post(
        "/upload-slip",
        files={"file": ("notes.txt", b"hello world from a not-image", "text/plain")},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    # No debio invocarse save_upload (la validacion corta antes).
    assert patched_save == []


async def test_upload_rejects_files_over_size_limit_with_413(
    client: httpx.AsyncClient,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    # 11MB de junk — el cap (10MB) se chequea antes que el MIME.
    huge = b"\x00" * (11 * 1024 * 1024)
    resp = await client.post(
        "/upload-slip",
        files={"file": ("huge.bin", huge, "application/octet-stream")},
    )
    assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert patched_save == []


async def test_upload_rejects_empty_file_with_400(
    client: httpx.AsyncClient,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    resp = await client.post(
        "/upload-slip",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert patched_save == []


async def test_upload_returns_409_when_hash_already_exists(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    png = _make_png_bytes(color="black")  # color distinto = hash distinto al happy
    h = compute_hash(png)

    # Pre-insert: una fila con el mismo hash.
    existing = Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path="/tmp/preexisting.png",
        hash_documento=h,
        estado_actual="recibido",
        banco="BBVA",
    )
    db_session.add(existing)
    await db_session.flush()
    existing_id = str(existing.id_comprobante)

    resp = await client.post(
        "/upload-slip",
        files={"file": ("dup.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_409_CONFLICT
    detail = resp.json()["detail"]
    assert detail["id_comprobante"] == existing_id
    assert detail["hash_documento"] == h
    # No se intento guardar a disco (cortocircuito antes del save).
    assert patched_save == []


async def test_upload_propagates_503_when_ocr_fails(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    patched_save: list[str],
) -> None:
    """`extract_fields` puede levantar HTTPException(503) tras agotar retries
    o cuando llama-server devuelve JSON invalido (D-09)."""

    async def boom(_b64: str) -> dict[str, Any]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llama-server no disponible",
        )

    monkeypatch.setattr(upload_module, "extract_fields", boom)

    png = _make_png_bytes(color="red")
    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    # save_upload SI se llamo (es paso 5, antes del OCR que es paso 8).
    # El archivo huerfano lo limpia el cron de Fase 5 — gotcha documentado.
    assert len(patched_save) == 1


async def test_upload_persists_null_texto_extraido_when_ocr_omits_content(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    patched_save: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1 (Spec CAP-01 Scenario 2): OCR sin campo 'content' → texto_extraido=NULL.

    El upload debe seguir teniendo exito (201) y la fila debe quedar
    con texto_extraido=NULL (no levantar error por campo faltante).
    """
    # OCR payload SIN la clave 'content'.
    payload_sin_content: dict[str, Any] = {
        "monto": "500.00",
        "fecha": "2026-05-03",
        "referencia": "REF-NULL-CONTENT",
        "numero_operacion": "OP-0001",
        "banco": "Santander",
    }

    async def fake_extract_no_content(_b64: str) -> dict[str, Any]:
        return payload_sin_content

    monkeypatch.setattr(upload_module, "extract_fields", fake_extract_no_content)

    png = _make_png_bytes(color="blue")
    expected_hash = compute_hash(png)

    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp_no_content.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_201_CREATED, resp.text

    row = (
        await db_session.execute(
            select(Comprobante).where(Comprobante.hash_documento == expected_hash)
        )
    ).scalar_one()
    # Cuando el OCR no devuelve 'content', texto_extraido debe ser NULL.
    assert row.texto_extraido is None
    assert row.banco == "Santander"
