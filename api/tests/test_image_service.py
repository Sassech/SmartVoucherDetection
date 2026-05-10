"""Tests del servicio de imagen (PROGRESO 1.3.1 - 1.3.4)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from services.image_service import (
    ALLOWED_MIMES,
    pdf_to_image,
    preprocess,
    to_base64,
    validate_mime,
)

# Fixture compartida con el smoke test de OCR (Fase 0.5.2). No duplicamos.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PNG = REPO_ROOT / "infra" / "scripts" / "fixtures" / "sample_comprobante.png"


@pytest.fixture(scope="module")
def png_bytes() -> bytes:
    assert SAMPLE_PNG.exists(), (
        f"fixture faltante: {SAMPLE_PNG}. "
        "Regenerar con: uv run --project api python infra/scripts/generate_sample.py"
    )
    return SAMPLE_PNG.read_bytes()


def _build_pdf_bytes(width: int = 400, height: int = 400) -> bytes:
    """Genera un PDF sintetico de una pagina con texto, en memoria."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=72)
    return buf.getvalue()


def _rotate_png(png: bytes, degrees: float) -> bytes:
    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), degrees, 1.0)
    rotated = cv2.warpAffine(img, matrix, (w, h), borderValue=(255, 255, 255))
    ok, encoded = cv2.imencode(".png", rotated)
    assert ok
    return encoded.tobytes()


# ---------------------------------------------------------------------------
# validate_mime (1.3.2)
# ---------------------------------------------------------------------------


def test_validate_mime_detects_png(png_bytes: bytes) -> None:
    assert validate_mime(png_bytes) == "image/png"


def test_validate_mime_detects_jpeg() -> None:
    img = Image.new("RGB", (50, 50), color=(180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    assert validate_mime(buf.getvalue()) == "image/jpeg"


def test_validate_mime_detects_pdf() -> None:
    pdf = _build_pdf_bytes()
    assert validate_mime(pdf) == "application/pdf"


def test_validate_mime_rejects_text() -> None:
    with pytest.raises(ValueError, match="MIME no permitido"):
        validate_mime(b"definitely not an image")


def test_validate_mime_rejects_empty() -> None:
    with pytest.raises(ValueError, match="vacio"):
        validate_mime(b"")


def test_allowed_mimes_constant_matches_plan() -> None:
    # Contrato: el plan_desarrollo.md fija exactamente estos tres tipos.
    assert ALLOWED_MIMES == {"image/jpeg", "image/png", "application/pdf"}


# ---------------------------------------------------------------------------
# pdf_to_image (1.3.1)
# ---------------------------------------------------------------------------


def test_pdf_to_image_returns_decodable_png() -> None:
    pdf = _build_pdf_bytes(width=200, height=200)

    out = pdf_to_image(pdf)

    # Bytes magicos PNG.
    assert out[:8] == b"\x89PNG\r\n\x1a\n"

    arr = np.frombuffer(out, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert img is not None
    # 200px @ 72dpi -> ~2.78", a 300dpi -> ~833px. No fijamos exacto para
    # no atarse a la version de poppler.
    assert img.shape[0] > 100
    assert img.shape[1] > 100


def test_pdf_to_image_rejects_garbage() -> None:
    with pytest.raises(Exception):  # pdf2image lanza varias subclases
        pdf_to_image(b"not a pdf at all")


# ---------------------------------------------------------------------------
# preprocess (1.3.3)
# ---------------------------------------------------------------------------


def test_preprocess_returns_binary_png(png_bytes: bytes) -> None:
    out = preprocess(png_bytes)

    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    arr = np.frombuffer(out, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    assert img is not None
    assert img.ndim == 2

    # Salida de adaptiveThreshold: mayoria de pixeles son 0 o 255. Tolerancia
    # por encoding PNG y eventuales 1-2 valores intermedios en el crop.
    unique = np.unique(img)
    extremes = np.sum((img == 0) | (img == 255))
    ratio = extremes / img.size
    assert ratio > 0.99, f"esperado >99% pixeles binarios, obtenido {ratio:.4f}"
    assert len(unique) <= 5


def test_preprocess_handles_rotated_image(png_bytes: bytes) -> None:
    rotated = _rotate_png(png_bytes, 5.0)

    out = preprocess(rotated)

    arr = np.frombuffer(out, np.uint8)
    result = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    assert result is not None
    assert result.ndim == 2
    # Tras deskew + crop, el output deberia ser mas chico que el rotado
    # (el crop elimina los triangulos blancos que aparecen al rotar).
    assert result.size > 0


def test_preprocess_crops_whitespace(png_bytes: bytes) -> None:
    # Padding artificial: ponemos el sample dentro de un canvas mas grande.
    arr = np.frombuffer(png_bytes, np.uint8)
    sample = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    h, w = sample.shape[:2]
    padded = np.full((h + 400, w + 400, 3), 255, dtype=np.uint8)
    padded[200 : 200 + h, 200 : 200 + w] = sample
    ok, encoded = cv2.imencode(".png", padded)
    assert ok

    out = preprocess(encoded.tobytes())
    arr2 = np.frombuffer(out, np.uint8)
    result = cv2.imdecode(arr2, cv2.IMREAD_GRAYSCALE)
    assert result is not None
    # El output debe ser sustancialmente mas chico que el padded (margenes
    # blancos recortados). Tolerancia: al menos 25% mas chico.
    assert result.size < padded.shape[0] * padded.shape[1] * 0.75


def test_preprocess_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="ilegible"):
        preprocess(b"not an image at all")


# ---------------------------------------------------------------------------
# to_base64 (1.3.4)
# ---------------------------------------------------------------------------


def test_to_base64_roundtrip(png_bytes: bytes) -> None:
    encoded = to_base64(png_bytes)

    assert isinstance(encoded, str)
    # Solo ASCII (sin newlines tampoco).
    assert encoded.isascii()
    assert "\n" not in encoded
    # Equivalencia con base64.b64encode estandar.
    assert encoded == base64.b64encode(png_bytes).decode("ascii")
    # Decodifica de vuelta a los bytes originales.
    assert base64.b64decode(encoded) == png_bytes


def test_to_base64_empty() -> None:
    assert to_base64(b"") == ""
