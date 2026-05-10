"""Celery task: full async processing pipeline for a comprobante upload.

Mirrors the synchronous logic in routers/upload.py but runs in a Celery worker.
The task serializes file bytes as base64 (JSON-compatible) and runs the async
pipeline inside asyncio.run(...) since Celery workers are synchronous.

Design decisions:
- base64 encoding: Celery task args must be JSON-serializable. File bytes are
  not — so we encode on the API side and decode here.
- asyncio.run: Celery workers are sync. The underlying pipeline (DB, Redis, OCR)
  is async, so we run it in a fresh event loop per task invocation.
- No broker in CI: set CELERY_TASK_ALWAYS_EAGER=True via conftest / monkeypatch
  to run tasks synchronously in-process without a Redis broker.
- max_retries=3: transient errors (network glitches, Redis hiccups) are retried
  with 60s delay. Validation errors (bad MIME, etc.) raise ValueError and do NOT
  trigger retries (Celery only retries on self.retry() calls).
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from celery_app import celery_app


@celery_app.task(
    bind=True,
    name="tasks.process_slip",
    max_retries=3,
    default_retry_delay=60,
)
def process_slip(
    self,
    file_bytes_b64: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    """Process a comprobante upload asynchronously.

    Args:
        file_bytes_b64: base64-encoded file bytes.
        filename: original filename (for extension detection).
        content_type: MIME type hint from HTTP header (libmagic validates real type).

    Returns:
        dict with ComprobanteResponse fields (JSON-serializable).

    Raises:
        ValueError: For invalid base64 or structural input errors (no retry).
        self.retry(): On transient errors (max 3 times, 60s delay).
    """
    try:
        file_bytes = base64.b64decode(file_bytes_b64)
    except Exception as exc:
        raise ValueError(f"Invalid base64 file data: {exc}") from exc

    return asyncio.run(_run_pipeline(file_bytes, filename, content_type))


async def _run_pipeline(
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    """Internal async pipeline — mirrors upload.py logic.

    Runs inside asyncio.run() from the sync Celery task.
    """
    from datetime import datetime, timezone

    from database import SessionLocal
    from models.comprobante import Comprobante
    from models.seed import SYSTEM_USER_ID
    from models.validacion import Validacion
    from schemas.comprobante import ComprobanteResponse
    from services.cache_service import check_hash, set_hash
    from services.duplicate_service import run_capa2, run_capa3
    from services.image_service import (
        pdf_to_image,
        preprocess,
        to_base64,
        validate_mime,
    )
    from services.ocr_service import extract_fields
    from services.parser_service import (
        compute_hash,
        normalize_banco,
        parse_fecha,
        parse_monto,
        parse_referencia,
    )
    from services.state_machine import apply_transition
    from services.storage_service import mime_to_ext, save_upload

    # 1. Validate MIME via libmagic
    try:
        mime = validate_mime(file_bytes)
    except ValueError as exc:
        raise ValueError(f"Invalid MIME type: {exc}") from exc

    # 2. Hash on original bytes (D-09)
    sha256 = compute_hash(file_bytes)

    # 3. Capa 1 Redis check — if hit, return conflict marker
    cached_id = await check_hash(sha256)
    if cached_id:
        return {"conflict": True, "id_comprobante": str(cached_id)}

    # 4. Save file
    now = datetime.now(timezone.utc)
    ext = mime_to_ext(mime)
    path = await save_upload(
        file_bytes,
        hash_documento=sha256,
        ext=ext,
        year=now.year,
        month=now.month,
    )

    # 5. Convert PDF → PNG if needed
    img_bytes = pdf_to_image(file_bytes) if mime == "application/pdf" else file_bytes

    # 6. Preprocess + base64
    processed = preprocess(img_bytes)
    img_b64 = to_base64(processed)

    # 7. OCR
    crudos = await extract_fields(img_b64)

    # 8. Parse fields
    monto = parse_monto(crudos.get("monto"))
    fecha = parse_fecha(crudos.get("fecha"))
    referencia = parse_referencia(crudos.get("referencia"))
    banco = normalize_banco(crudos.get("banco", ""))
    texto = crudos.get("content")

    # 9. Persist comprobante
    async with SessionLocal() as session:
        comp = Comprobante(
            id_usuario=SYSTEM_USER_ID,
            imagen_path=str(path),
            hash_documento=sha256,
            estado_actual="recibido",
            monto=monto,
            fecha_deposito=fecha,
            referencia=referencia,
            banco=banco,
            texto_extraido=texto,
        )
        apply_transition(comp, "procesando")
        session.add(comp)
        await session.flush()

        # Fire-and-forget hash cache (post-flush, pre-capa2)
        await set_hash(sha256, comp.id_comprobante)

        # Capa 2 — exact match
        apply_transition(comp, "comparando")
        match2 = await run_capa2(session, comp)
        if match2:
            apply_transition(comp, "duplicado")
            val = Validacion(
                id_comprobante=comp.id_comprobante,
                id_comprobante_original=match2.id_comprobante,
                id_usuario=SYSTEM_USER_ID,
                clasificacion="duplicado",
                metodo_deteccion="campos_exactos",
                score_similitud=None,
            )
            session.add(val)
            await session.commit()
            await session.refresh(comp)
            return ComprobanteResponse.from_orm_model(comp).model_dump(mode="json")

        # Capa 3 — scoring ponderado
        best, score, clasif = await run_capa3(session, comp)
        apply_transition(comp, clasif)

        # sospechoso auto-transitions to en_revision
        if clasif == "sospechoso":
            apply_transition(comp, "en_revision")

        id_original = best.id_comprobante if best is not None else None
        val = Validacion(
            id_comprobante=comp.id_comprobante,
            id_comprobante_original=id_original,
            id_usuario=SYSTEM_USER_ID,
            clasificacion=clasif,
            metodo_deteccion="scoring_ponderado",
            score_similitud=score,
        )
        session.add(val)
        await session.commit()
        await session.refresh(comp)
        return ComprobanteResponse.from_orm_model(comp).model_dump(mode="json")
