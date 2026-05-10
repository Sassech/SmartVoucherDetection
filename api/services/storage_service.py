"""Servicio de storage — persiste los bytes originales del upload a disco.

Responsabilidad UNICA: tomar (bytes, hash, ext) y devolver la ruta absoluta
donde quedo el archivo. NO valida MIME (eso es `image_service.validate_mime`),
NO calcula hash (eso es `parser_service.compute_hash`).

Layout en disco: `{UPLOAD_DIR}/{yyyy}/{mm}/{hash}.{ext}`
- Particionar por anio/mes evita el clasico "carpeta con 100k archivos
  que tarda 30s en listar". El primer cliente real va a estar lejos de
  ese numero, pero el costo de partir es cero.
- Filename = hash garantiza unicidad (SHA-256 colision = problema mundial,
  no nuestro) y es idempotente: re-upload del mismo archivo escribe en la
  misma ruta. El INSERT en DB falla por UNIQUE en `hash_documento` y eso
  es lo correcto — el storage no necesita su propio control.

Async via `asyncio.to_thread`:
File I/O bloquea. Si lo hicieramos sincrono dentro del event loop de
FastAPI, congelariamos OTROS requests durante los ~10ms que tarda el
write. `to_thread` lo manda al threadpool default (8 workers en CPython
3.12) — para Fase 1 (concurrencia baja) sobra. Si en el futuro queremos
async nativo, migrar a `aiofiles` o directamente a `aioboto3` para S3 es
un cambio aislado a este modulo.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from config import settings

# Whitelist de extensiones aceptadas. Espeja `image_service.ALLOWED_MIMES`
# pero del lado de filesystem (la extension la elige el caller, no el byte
# stream). Centralizado aca para que cualquier cambio sea atomico.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"png", "jpg", "jpeg", "pdf"})

# Hash SHA-256 = 64 hex chars lowercase. Defensa en profundidad: aunque
# `compute_hash` siempre emite eso, validamos antes de tocar disco para
# que un caller buggeado no pueda escribir en `../../../etc/passwd.png`.
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class StorageError(RuntimeError):
    """Error generico de storage. El caller decide si traduce a 5xx HTTP."""


def _build_path(hash_documento: str, ext: str, fecha_iso_year: int, mes: int) -> Path:
    """Arma la ruta destino y crea los directorios padres si no existen.

    Funcion interna pura (no toca filesystem) — el `mkdir` se hace en el
    sync helper para no duplicar la logica de path-building en tests.
    """
    return (
        settings.upload_dir
        / f"{fecha_iso_year:04d}"
        / f"{mes:02d}"
        / f"{hash_documento}.{ext}"
    )


def _save_sync(data: bytes, path: Path) -> None:
    """Escritura sincrona — pensada para correr en threadpool.

    Usa write atomic: escribe a `path.tmp` y hace rename. `os.replace` es
    atomico en POSIX, asi que un crash a mitad de write deja la version
    vieja (o nada) en `path`, nunca un archivo a medias. Importante porque
    el endpoint commitea la fila DB DESPUES del write — si el server muere
    entre write y commit, el archivo huerfano no rompe el sistema.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic en POSIX, "best effort" en Windows
    except OSError as exc:
        # Limpieza best-effort del .tmp si quedo colgado.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise StorageError(f"no se pudo escribir el upload: {exc}") from exc


async def save_upload(
    data: bytes,
    *,
    hash_documento: str,
    ext: str,
    year: int,
    month: int,
) -> Path:
    """Persiste `data` en disco y devuelve la ruta absoluta.

    Args:
        data: bytes ORIGINALES del upload (no preprocessed). El hash debe
            ser sobre estos mismos bytes (D-09 / gotcha 2026-05-09).
        hash_documento: SHA-256 hex lowercase (64 chars). Se usa como
            filename. Si no matchea el regex, levanta `ValueError` SIN
            tocar disco.
        ext: extension SIN punto (`png`, `jpg`, `jpeg`, `pdf`). Whitelist
            estricta — cualquier otra cosa es `ValueError`.
        year: anio del comprobante (typically `datetime.utcnow().year` al
            momento del upload — NO la fecha del comprobante en si, que
            puede no haberse parseado todavia).
        month: idem, 1-12.

    Returns:
        `Path` absoluto al archivo escrito.

    Raises:
        ValueError: hash invalido, ext fuera de whitelist, o data vacio.
        StorageError: error de I/O al escribir.
    """
    if not data:
        raise ValueError("data vacio: no hay bytes que persistir")
    if not _HASH_RE.fullmatch(hash_documento):
        raise ValueError(
            f"hash_documento invalido: esperado SHA-256 hex lowercase, recibi "
            f"{hash_documento!r}"
        )
    ext_lower = ext.lower().lstrip(".")
    if ext_lower not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"ext invalida: {ext!r}. Permitidas: {sorted(ALLOWED_EXTENSIONS)}"
        )
    if not (1 <= month <= 12):
        raise ValueError(f"month fuera de rango [1,12]: {month}")

    path = _build_path(hash_documento, ext_lower, year, month)
    await asyncio.to_thread(_save_sync, data, path)
    return path


def mime_to_ext(mime: str) -> str:
    """Mapea un MIME del whitelist a su extension canonica.

    El caller tipico ya valido el MIME con `image_service.validate_mime`,
    asi que aca asumimos input controlado y rompemos fuerte si algo no
    matchea (defensivo contra futuros cambios en `ALLOWED_MIMES` que se
    olviden de actualizar este mapeo).
    """
    mapping = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "application/pdf": "pdf",
    }
    try:
        return mapping[mime]
    except KeyError as exc:
        raise ValueError(
            f"MIME sin mapeo a extension: {mime!r}. Actualizar `mime_to_ext`."
        ) from exc
