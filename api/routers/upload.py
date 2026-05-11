"""Endpoint `POST /upload-slip` — pipeline sincrono completo de Fase 2.

Orquesta:
    bytes -> validate_mime -> compute_hash
        -> [Capa 1 DB] _find_existing_by_hash → 409 si hit
        -> [Capa 1 Redis] check_hash → 409 si hit
        -> save_upload (filesystem)
        -> [if pdf] pdf_to_image
        -> preprocess -> to_base64
        -> ocr_service.extract_fields  (red a llama-server)
        -> parser_service.{parse_monto, parse_fecha, parse_referencia,
                           normalize_banco}
        -> apply_transition("recibido" → "procesando")
        -> INSERT Comprobante(estado_actual="procesando", texto_extraido=content)
        -> await session.commit()
        -> set_hash(sha256, comp.id) [fire-and-forget]
        -> apply_transition("procesando" → "comparando")
        -> [Capa 2] run_capa2 → si hit: duplicado + INSERT Validacion + 200
        -> [Capa 3] run_capa3 → transicion al estado resultante + INSERT Validacion
        -> await session.commit()
        -> ComprobanteResponse (201 si valido/sospechoso, 200 si duplicado)

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

- ESTADO INICIAL: la fila se inserta con `estado_actual="procesando"` tras
  la transicion recibido→procesando via apply_transition (Fase 2 B4).

- TRANSACCIONALIDAD: write a disco PRIMERO, INSERT despues. Si el INSERT
  falla, el archivo queda huerfano — es preferible a tener una fila DB
  apuntando a un path que no existe. Cleanup de huerfanos: cron de Fase 5.

- CASCADE CAPA 1 REDIS: se ejecuta DESPUES del check DB (paso 4) y ANTES
  de OCR. Si Redis esta caido, check_hash retorna None y el pipeline sigue
  a Capa 2 normalmente.

- SOSPECHOSO AUTO-TRANSICION: sospechoso → en_revision es automatico.
  La maquina de estados lo requiere (sospechoso no es terminal).

- set_hash FIRE-AND-FORGET: se llama despues del primer commit. Si falla,
  se ignora — la Capa 2 DB sigue funcionando como fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from dependencies.auth_api_key import require_api_key
from models.comprobante import Comprobante
from models.usuario import Usuario
from models.validacion import Validacion
from schemas.comprobante import CamposExtraidos, ComprobanteResponse
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
    """Busca un comprobante previo con el mismo hash (Capa 1 DB de duplicados).

    Mantiene el comportamiento de Fase 1. Capa 1 Redis (check_hash) es un
    fast-path adicional introducido en Fase 2 B4.
    """
    stmt = select(Comprobante).where(Comprobante.hash_documento == hash_documento)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@router.post(
    "/upload-slip",
    response_model=ComprobanteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Comprobante duplicado detectado (Capa 2 o Capa 3)"},
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
    usuario: Usuario = Depends(require_api_key),
) -> ComprobanteResponse:
    """Procesa un comprobante: OCR + normalizacion + deteccion de duplicados.

    Cascade de deteccion (Fase 2):
    - Capa 1 DB: hash UNIQUE en tabla comprobantes (pre-OCR fast-path)
    - Capa 1 Redis: check_hash (pre-OCR, fire-and-forget fallback)
    - Capa 2: exact match (referencia + monto + fecha) via indice compuesto
    - Capa 3: scoring ponderado (Levenshtein + TF-IDF + monto + fecha)
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

    # 4. Capa 1 implicita DB: si ya existe, 409 antes de gastar OCR/disco.
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

    # 4b. Capa 1 Redis fast-path: check_hash — si hit, 409 sin OCR ni disco.
    cached_id = await check_hash(hash_documento)
    if cached_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "comprobante con mismo hash ya existe (cache)",
                "id_comprobante": str(cached_id),
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

    # 10. Crear comprobante con estado inicial "recibido", luego transicionar
    #     a "procesando" via apply_transition antes del INSERT.
    comprobante = Comprobante(
        id_usuario=usuario.id_usuario,
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
    # 10b. Transicion recibido → procesando (state machine).
    apply_transition(comprobante, "procesando")

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

    # 10c. Cache hash en Redis fire-and-forget (post-commit exitoso).
    await set_hash(hash_documento, comprobante.id_comprobante)

    # 11. Transicion procesando → comparando (pre-deteccion).
    apply_transition(comprobante, "comparando")

    # -----------------------------------------------------------------------
    # 12. Capa 2 — exact match (referencia + monto + fecha_deposito)
    # -----------------------------------------------------------------------
    match_capa2 = await run_capa2(session, comprobante)
    if match_capa2 is not None:
        apply_transition(comprobante, "duplicado")
        validacion_c2 = Validacion(
            id_comprobante=comprobante.id_comprobante,
            id_comprobante_original=match_capa2.id_comprobante,
            clasificacion="duplicado",
            metodo_deteccion="campos_exactos",
            score_similitud=None,
        )
        session.add(validacion_c2)
        await session.commit()
        await session.refresh(comprobante)
        return ComprobanteResponse.from_orm_model(comprobante)

    # -----------------------------------------------------------------------
    # 13. Capa 3 — scoring ponderado
    # -----------------------------------------------------------------------
    best_comp, score, clasificacion = await run_capa3(session, comprobante)

    apply_transition(comprobante, clasificacion)

    # sospechoso es estado intermedio — auto-transicion a en_revision.
    if clasificacion == "sospechoso":
        apply_transition(comprobante, "en_revision")

    id_original = best_comp.id_comprobante if best_comp is not None else None
    validacion_c3 = Validacion(
        id_comprobante=comprobante.id_comprobante,
        id_comprobante_original=id_original,
        clasificacion=clasificacion,
        metodo_deteccion="scoring_ponderado",
        score_similitud=score,
    )
    session.add(validacion_c3)
    await session.commit()
    await session.refresh(comprobante)

    return ComprobanteResponse.from_orm_model(comprobante)
