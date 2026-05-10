"""Endpoint `POST /upload-slip` — pipeline sincrono completo de Fase 1.

Orquesta:
    bytes -> validate_mime -> compute_hash -> save_upload (filesystem)
        -> [if pdf] pdf_to_image
        -> preprocess -> to_base64
        -> ocr_service.extract_fields  (red a llama-server)
        -> parser_service.{parse_monto, parse_fecha, parse_referencia,
                           normalize_banco}
        -> ComprobanteCreate -> INSERT
        -> ComprobanteResponse

Decisiones explicitas:
- HASH ANTES DE PREPROCESS (D-09 / gotcha 2026-05-09): se calcula sobre los
  bytes ORIGINALES del upload. Si lo hicieramos sobre el PNG normalizado,
  re-uploads del mismo archivo darian hashes distintos por variabilidad
  del crop/encoding, rompiendo Capa 1 de Fase 2.

- 409 EN HASH DUPLICADO (decision sesion 2026-05-09): hacemos query previa
  por hash y devolvemos 409 con `id_comprobante` existente. Esto:
    1. Hace el endpoint estable hacia Fase 2.1 (alli solo se agrega un
       INSERT en `Validacion`; el contrato HTTP no cambia).
    2. Evita la race minima entre query y INSERT cazando tambien la
       `IntegrityError` de Postgres al final.

- USUARIO HARDCODED (decision sesion 2026-05-09, opcion C1): toda fila se
  crea con `SYSTEM_USER_ID`. Auth real llega en Fase 4. NO usar `request.state`
  ni headers — eso seria deuda silenciosa.

- ESTADO INICIAL: la fila se inserta con `estado_actual="recibido"`. La
  maquina de estados completa (transiciones a `valido`/`error`) llega en
  Fase 2.6. En Fase 1 dejamos todo en `recibido`.

- TRANSACCIONALIDAD: write a disco PRIMERO, INSERT despues. Si el INSERT
  falla, el archivo queda huerfano — es preferible a tener una fila DB
  apuntando a un path que no existe. Cleanup de huerfanos: cron de Fase 5.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID
from schemas.comprobante import CamposExtraidos, ComprobanteResponse
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
from services.storage_service import mime_to_ext, save_upload

router = APIRouter(tags=["comprobantes"])

# Limite duro de tamanio para Fase 1 — defensa contra uploads enormes que
# revientan memoria del worker. 10MB cubre PDFs multipage de comprobantes
# bancarios reales con margen. Se valida DESPUES de leer el archivo en
# memoria (FastAPI usa SpooledTemporaryFile, no carga todo si es grande,
# pero igual queremos un techo explicito).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_upload(file: UploadFile) -> bytes:
    """Lee el upload completo aplicando el limite de tamanio.

    FastAPI/Starlette no impone un cap por defecto: hay que verificarlo a
    mano. Leemos en una sola pasada (los archivos de Fase 1 son chicos);
    si en Fase 5+ recibimos PDFs gigantes, migrar a streaming chunked.
    """
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="archivo vacio",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"archivo excede el limite ({MAX_UPLOAD_BYTES} bytes)",
        )
    return data


async def _find_existing_by_hash(
    session: AsyncSession, hash_documento: str
) -> Comprobante | None:
    """Busca un comprobante previo con el mismo hash (Capa 1 de duplicados).

    En Fase 1 NO hay logica de Validacion asociada; solo devolvemos el
    existente para que el handler pueda responder 409 con su id. Fase 2.1
    movera esto a `services/cache_service.py` con cache Redis.
    """
    stmt = select(Comprobante).where(Comprobante.hash_documento == hash_documento)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@router.post(
    "/upload-slip",
    response_model=ComprobanteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "MIME invalido o archivo vacio"},
        409: {"description": "Comprobante con mismo hash ya existe"},
        413: {"description": "Archivo excede limite de tamanio"},
        502: {"description": "llama-server rechazo el request"},
        503: {"description": "llama-server no disponible o devolvio basura"},
    },
)
async def upload_slip(
    file: UploadFile = File(..., description="Imagen (PNG/JPEG) o PDF del comprobante"),
    session: AsyncSession = Depends(get_session),
) -> ComprobanteResponse:
    """Procesa un comprobante: OCR + normalizacion + persistencia.

    Sin deteccion de duplicados de Fase 2: solo Capa 1 implicita por el
    UNIQUE en `hash_documento`. Si ya existe, 409 con el id existente.
    """
    # 1. Leer bytes del upload (con cap de tamanio).
    raw_bytes = await _read_upload(file)

    # 2. MIME via libmagic (NO confiar en `file.content_type`: el cliente
    #    puede mentir; libmagic mira los bytes).
    try:
        mime = validate_mime(raw_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # 3. Hash sobre bytes ORIGINALES (D-09).
    hash_documento = compute_hash(raw_bytes)

    # 4. Capa 1 implicita: si ya existe, 409 antes de gastar OCR/disco.
    existing = await _find_existing_by_hash(session, hash_documento)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "comprobante con mismo hash ya existe",
                "id_comprobante": str(existing.id_comprobante),
                "hash_documento": hash_documento,
            },
        )

    # 5. Persistir bytes originales en filesystem (idempotente por hash).
    now = datetime.now(timezone.utc)
    ext = mime_to_ext(mime)
    imagen_path = await save_upload(
        raw_bytes,
        hash_documento=hash_documento,
        ext=ext,
        year=now.year,
        month=now.month,
    )

    # 6. PDF -> primera pagina como PNG. Imagenes pasan derecho.
    if mime == "application/pdf":
        img_bytes = pdf_to_image(raw_bytes)
    else:
        img_bytes = raw_bytes

    # 7. Pipeline OpenCV (deskew + adaptiveThreshold + crop) y base64.
    processed = preprocess(img_bytes)
    img_b64 = to_base64(processed)

    # 8. OCR — puede levantar 502/503; el handler global de FastAPI los
    #    propaga tal cual (ocr_service ya construye HTTPException correcto).
    crudos = await extract_fields(img_b64)

    # 9. Normalizacion. Cada parser devuelve None ante input invalido (D-10);
    #    el endpoint NO bloquea por campo faltante en Fase 1.
    campos = CamposExtraidos(
        monto=parse_monto(crudos.get("monto")),
        fecha=parse_fecha(crudos.get("fecha")),
        referencia=parse_referencia(crudos.get("referencia")),
        # numero_operacion: passthrough crudo, sin normalizar (decision 1.6.1).
        numero_operacion=(crudos.get("numero_operacion") or None),
        banco=normalize_banco(crudos.get("banco")),
    )

    # 10. INSERT. NO usamos ComprobanteCreate aca porque tendriamos que
    #     re-mappear todos los campos a columnas planas — el ORM ya espera
    #     columnas, asi que las pasamos directo. ComprobanteCreate queda
    #     util para repos/factories de tests, no para este endpoint.
    comprobante = Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path=str(imagen_path),
        texto_extraido=crudos.get(
            "content"
        ),  # A1 Fase 2: persiste el texto raw del OCR
        referencia=campos.referencia,
        monto=campos.monto,
        fecha_deposito=campos.fecha,
        numero_operacion=campos.numero_operacion,
        banco=campos.banco,
        hash_documento=hash_documento,
        estado_actual="recibido",
    )
    session.add(comprobante)
    try:
        await session.commit()
    except IntegrityError:
        # Race: alguien insertó el mismo hash entre nuestro SELECT y el
        # INSERT. Re-consultar y devolver 409 con el id que gano.
        await session.rollback()
        existing = await _find_existing_by_hash(session, hash_documento)
        if existing is None:
            # Caso patologico: IntegrityError sin fila reaparecida (FK?)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="error de integridad inesperado al insertar comprobante",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "comprobante con mismo hash ya existe",
                "id_comprobante": str(existing.id_comprobante),
                "hash_documento": hash_documento,
            },
        )

    await session.refresh(comprobante)
    return ComprobanteResponse.from_orm_model(comprobante)
