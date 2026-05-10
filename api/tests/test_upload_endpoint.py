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

Casos Fase 1:
1. happy path → 201, body bien armado, fila en DB.
2. MIME no soportado → 400.
3. >10MB → 413 (size se valida ANTES que MIME).
4. hash ya existe → 409 con `id_comprobante` existente.
5. OCR cae con 503 → propaga 503.
6. archivo vacio → 400.

Casos Fase 2 B4 — cascade de deteccion:
7. Capa 1 Redis hit → 409 (check_hash retorna UUID)
8. Capa 2 exact match → response tiene estado_actual=duplicado
9. Capa 3 score sospechoso → estado_actual=sospechoso (o en_revision post-auto)
10. Capa 3 score valido → estado_actual=valido, 201
"""

from __future__ import annotations

import io
import uuid
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B4 Fase 2: happy path ahora corre la cascade completa.

    Sin candidatos en DB y Redis silenciado (fire-and-forget) →
    Capa 3 retorna 'valido'. Estado final: 'valido', 201 Created.

    check_hash y set_hash se mockean para aislar el test de Redis real.
    """

    # Aislar Capa 1 Redis: no hay nada en cache.
    async def fake_check_hash(_sha256: str) -> None:
        return None

    async def fake_set_hash(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)
    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

    png = _make_png_bytes()
    expected_hash = compute_hash(png)

    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["hash_documento"] == expected_hash
    # Fase 2 B4: el pipeline completo corre — sin candidatos → estado=valido
    assert body["estado_actual"] == "valido"
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
    assert row.estado_actual == "valido"
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

    # Aislar Capa 1 Redis
    async def fake_check_hash(_sha256: str) -> None:
        return None

    async def fake_set_hash(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)
    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

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


# ---------------------------------------------------------------------------
# B4: Cascade de deteccion — Capa 1 (Redis), Capa 2 (Postgres), Capa 3 (scoring)
# ---------------------------------------------------------------------------


async def test_upload_capa1_redis_hit_returns_409(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    """B4: Capa 1 Redis hit → 409 antes de OCR (check_hash retorna UUID)."""
    existing_id = uuid.UUID("11111111-2222-3333-4444-555566667777")

    async def fake_check_hash(_sha256: str) -> uuid.UUID:
        return existing_id

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)

    png = _make_png_bytes(color="cyan")
    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_409_CONFLICT
    detail = resp.json()["detail"]
    assert detail["id_comprobante"] == str(existing_id)


async def test_upload_capa2_duplicate_returns_estado_duplicado(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    """B4: Capa 2 exact match → response con estado_actual=duplicado."""

    # Capa 1 Redis: miss (no Redis)
    async def fake_check_hash(_sha256: str) -> None:
        return None

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)

    # set_hash: no-op
    async def fake_set_hash(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

    # Capa 2: siempre retorna un comprobante existente
    existing = Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path="/tmp/existing.png",
        hash_documento="existing_hash_" + "x" * 50,
        estado_actual="comparando",
    )
    db_session.add(existing)
    await db_session.flush()

    async def fake_run_capa2(_session, _nuevo):
        return existing

    monkeypatch.setattr(upload_module, "run_capa2", fake_run_capa2)

    png = _make_png_bytes(color="magenta")
    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    # Duplicate found → response must reflect duplicado state
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    body = resp.json()
    assert body["estado_actual"] == "duplicado"


async def test_upload_capa3_sospechoso_returns_correct_estado(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    """B4: Capa 3 score sospechoso → estado_actual en sospechoso o en_revision."""

    # Capa 1: miss
    async def fake_check_hash(_sha256: str) -> None:
        return None

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)

    async def fake_set_hash(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

    # Capa 2: miss
    async def fake_run_capa2(_session, _nuevo):
        return None

    monkeypatch.setattr(upload_module, "run_capa2", fake_run_capa2)

    # Capa 3: sospechoso
    existing = Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path="/tmp/existing2.png",
        hash_documento="sospechoso_hash_" + "x" * 48,
        estado_actual="comparando",
    )
    db_session.add(existing)
    await db_session.flush()

    async def fake_run_capa3(_session, _nuevo):
        return (existing, 0.80, "sospechoso")

    monkeypatch.setattr(upload_module, "run_capa3", fake_run_capa3)

    png = _make_png_bytes(color="yellow")
    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    body = resp.json()
    # sospechoso auto-transitions to en_revision
    assert body["estado_actual"] in ("sospechoso", "en_revision")


async def test_upload_capa3_valido_returns_201_and_valido_estado(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    patched_save: list[str],
    patched_ocr_ok: dict[str, Any],
) -> None:
    """B4: Capa 3 score valido → estado_actual=valido, 201 Created."""

    # Capa 1: miss
    async def fake_check_hash(_sha256: str) -> None:
        return None

    monkeypatch.setattr(upload_module, "check_hash", fake_check_hash)

    async def fake_set_hash(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(upload_module, "set_hash", fake_set_hash)

    # Capa 2: miss
    async def fake_run_capa2(_session, _nuevo):
        return None

    monkeypatch.setattr(upload_module, "run_capa2", fake_run_capa2)

    # Capa 3: valido (score bajo, no hay match)
    async def fake_run_capa3(_session, _nuevo):
        return (None, 0.30, "valido")

    monkeypatch.setattr(upload_module, "run_capa3", fake_run_capa3)

    png = _make_png_bytes(color="green")
    resp = await client.post(
        "/upload-slip",
        files={"file": ("comp.png", png, "image/png")},
    )

    assert resp.status_code == status.HTTP_201_CREATED
    body = resp.json()
    assert body["estado_actual"] == "valido"
