"""Tests de `services/storage_service.py`.

Estrategia de aislamiento: monkeypatcheamos `settings.upload_dir` a un
`tmp_path` por test para no contaminar el filesystem real ni colisionar
entre runs paralelos. NO usamos un fixture autouse global porque algunos
tests (validacion pura) no escriben a disco y no necesitan tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services import storage_service
from services.storage_service import (
    ALLOWED_EXTENSIONS,
    StorageError,
    mime_to_ext,
    save_upload,
)

# Hash de prueba — SHA-256 hex valido, no calculado sobre nada en particular.
VALID_HASH = "a" * 64
VALID_DATA = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # bytes que no parsean nada
VALID_EXT = "png"
VALID_YEAR = 2026
VALID_MONTH = 5


@pytest.fixture
def upload_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aisla `upload_dir` por test usando tmp_path."""
    monkeypatch.setattr(storage_service.settings, "upload_dir", tmp_path)
    return tmp_path


# --- Validaciones puras (no requieren filesystem) ----------------------------


@pytest.mark.parametrize(
    "bad_hash",
    [
        "",
        "not_hex",
        "A" * 64,  # uppercase no permitido
        "a" * 63,
        "a" * 65,
        "g" * 64,  # 'g' no es hex
    ],
)
async def test_save_upload_rejects_invalid_hash(
    upload_root: Path, bad_hash: str
) -> None:
    with pytest.raises(ValueError, match="hash_documento invalido"):
        await save_upload(
            VALID_DATA,
            hash_documento=bad_hash,
            ext=VALID_EXT,
            year=VALID_YEAR,
            month=VALID_MONTH,
        )


@pytest.mark.parametrize("bad_ext", ["exe", "gif", "tiff", "", "PNG.jpg"])
async def test_save_upload_rejects_invalid_ext(upload_root: Path, bad_ext: str) -> None:
    with pytest.raises(ValueError, match="ext invalida"):
        await save_upload(
            VALID_DATA,
            hash_documento=VALID_HASH,
            ext=bad_ext,
            year=VALID_YEAR,
            month=VALID_MONTH,
        )


async def test_save_upload_rejects_empty_data(upload_root: Path) -> None:
    with pytest.raises(ValueError, match="data vacio"):
        await save_upload(
            b"",
            hash_documento=VALID_HASH,
            ext=VALID_EXT,
            year=VALID_YEAR,
            month=VALID_MONTH,
        )


@pytest.mark.parametrize("bad_month", [0, 13, -1, 100])
async def test_save_upload_rejects_invalid_month(
    upload_root: Path, bad_month: int
) -> None:
    with pytest.raises(ValueError, match="month fuera de rango"):
        await save_upload(
            VALID_DATA,
            hash_documento=VALID_HASH,
            ext=VALID_EXT,
            year=VALID_YEAR,
            month=bad_month,
        )


# --- Happy path + estructura del filesystem ----------------------------------


async def test_save_upload_creates_partitioned_path(upload_root: Path) -> None:
    path = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext=VALID_EXT,
        year=2026,
        month=5,
    )
    expected = upload_root / "2026" / "05" / f"{VALID_HASH}.png"
    assert path == expected
    assert path.exists()
    assert path.read_bytes() == VALID_DATA


async def test_save_upload_pads_month_to_two_digits(upload_root: Path) -> None:
    path = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext=VALID_EXT,
        year=2026,
        month=1,
    )
    # Verifica zero-padding: "01" no "1".
    assert "01" in path.parts
    assert "1" not in (p for p in path.parts if len(p) == 1)


async def test_save_upload_lowercases_extension(upload_root: Path) -> None:
    path = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext="PNG",
        year=2026,
        month=5,
    )
    assert path.suffix == ".png"


async def test_save_upload_strips_leading_dot(upload_root: Path) -> None:
    path = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext=".png",
        year=2026,
        month=5,
    )
    assert path.suffix == ".png"
    assert path.exists()


async def test_save_upload_idempotent_on_same_hash(upload_root: Path) -> None:
    """Re-upload del mismo archivo escribe en la misma ruta (overwrite atomico).

    Es deseable: el INSERT en DB con UNIQUE en hash_documento es la barrera
    de deduplicacion, no el filesystem.
    """
    path1 = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext=VALID_EXT,
        year=2026,
        month=5,
    )
    path2 = await save_upload(
        b"contenido distinto pero mismo hash (caso teorico)",
        hash_documento=VALID_HASH,
        ext=VALID_EXT,
        year=2026,
        month=5,
    )
    assert path1 == path2
    # El segundo write gana (replace atomico).
    assert path1.read_bytes() == b"contenido distinto pero mismo hash (caso teorico)"


async def test_save_upload_no_tmp_files_left(upload_root: Path) -> None:
    """El `.tmp` intermedio debe desaparecer tras un write exitoso."""
    path = await save_upload(
        VALID_DATA,
        hash_documento=VALID_HASH,
        ext=VALID_EXT,
        year=2026,
        month=5,
    )
    tmps = list(path.parent.glob("*.tmp"))
    assert tmps == [], f"quedaron .tmp huerfanos: {tmps}"


async def test_save_upload_supports_pdf(upload_root: Path) -> None:
    pdf_bytes = b"%PDF-1.4\n%fake pdf for testing"
    path = await save_upload(
        pdf_bytes,
        hash_documento=VALID_HASH,
        ext="pdf",
        year=2026,
        month=5,
    )
    assert path.suffix == ".pdf"
    assert path.read_bytes() == pdf_bytes


# --- I/O error handling ------------------------------------------------------


async def test_save_upload_wraps_oserror_as_storage_error(
    monkeypatch: pytest.MonkeyPatch, upload_root: Path
) -> None:
    """Si el filesystem falla, el caller ve `StorageError`, no `OSError` raw.

    Asi el endpoint puede traducir uniformemente a 503 sin acoplarse a la
    jerarquia de excepciones de stdlib.
    """

    def boom(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(Path, "write_bytes", boom)

    with pytest.raises(StorageError, match="no se pudo escribir"):
        await save_upload(
            VALID_DATA,
            hash_documento=VALID_HASH,
            ext=VALID_EXT,
            year=VALID_YEAR,
            month=VALID_MONTH,
        )


# --- mime_to_ext -------------------------------------------------------------


@pytest.mark.parametrize(
    "mime, expected",
    [
        ("image/png", "png"),
        ("image/jpeg", "jpg"),
        ("application/pdf", "pdf"),
    ],
)
def test_mime_to_ext_happy_path(mime: str, expected: str) -> None:
    assert mime_to_ext(mime) == expected


@pytest.mark.parametrize("bad_mime", ["image/gif", "text/plain", "", "image/PNG"])
def test_mime_to_ext_rejects_unknown(bad_mime: str) -> None:
    with pytest.raises(ValueError, match="MIME sin mapeo"):
        mime_to_ext(bad_mime)


def test_mime_to_ext_returns_value_in_allowed_extensions() -> None:
    """Defensa: todo lo que devuelve mime_to_ext debe ser valido para save_upload."""
    for mime in ["image/png", "image/jpeg", "application/pdf"]:
        assert mime_to_ext(mime) in ALLOWED_EXTENSIONS
