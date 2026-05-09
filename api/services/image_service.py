"""Servicio de preprocesamiento de imagen.

Funciones:
    - validate_mime: chequea tipo MIME contra whitelist (PDF, JPEG, PNG).
    - pdf_to_image: convierte la primera pagina de un PDF a PNG bytes (dpi=300).
    - preprocess: pipeline OpenCV (gray -> deskew -> threshold -> crop -> encode).
    - to_base64: codifica bytes en base64 ASCII para envio a llama-server.

Decision tecnica (plan 1.2.B vs implementacion):
    El plan_desarrollo.md pone los pasos en este orden:
        3) binarizacion adaptativa
        4) deskew (rotacion)
    Aca se invierten: deskew se aplica sobre la grayscale ANTES de binarizar.
    Razon: cv2.warpAffine usa interpolacion (bilineal/cubica) que produce
    valores intermedios entre 0 y 255. Rotar una imagen ya binarizada genera
    pixeles grises en los bordes del texto, rompiendo la binarizacion. El
    pipeline correcto para OCR es rotar antes de threshold.
"""

from __future__ import annotations

import base64
import io
from typing import Final

import cv2
import magic
import numpy as np
import pdf2image

ALLOWED_MIMES: Final[frozenset[str]] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "application/pdf",
    }
)

# Parametros del pipeline (centralizados para tunearlos sin tocar logica).
PDF_DPI: Final[int] = 300
ADAPTIVE_BLOCK_SIZE: Final[int] = 11  # vecindario para threshold (impar)
ADAPTIVE_C: Final[int] = 2  # constante restada de la media local
SKEW_MIN_ANGLE: Final[float] = 0.1  # grados; ignoramos rotaciones imperceptibles
CROP_PADDING_PX: Final[int] = 8  # margen de seguridad post-recorte
MIN_PIXELS_FOR_SKEW: Final[int] = 100  # debajo de este umbral no calculamos angulo


def validate_mime(file_bytes: bytes) -> str:
    """Detecta el MIME real (no la extension) y lo valida contra la whitelist.

    Levanta ValueError si el MIME no es image/jpeg, image/png o application/pdf.
    Importante: usamos libmagic, que mira los bytes magicos, no headers HTTP
    ni extensiones — un .pdf renombrado a .png es detectado correctamente.
    """
    if not file_bytes:
        raise ValueError("archivo vacio")
    mime = magic.from_buffer(file_bytes, mime=True)
    if mime not in ALLOWED_MIMES:
        allowed = ", ".join(sorted(ALLOWED_MIMES))
        raise ValueError(f"MIME no permitido: {mime!r}. Permitidos: {allowed}")
    return mime


def pdf_to_image(pdf_bytes: bytes) -> bytes:
    """Convierte la primera pagina de un PDF a PNG bytes.

    Usa pdf2image (poppler) a 300 dpi. Solo la primera pagina porque un
    comprobante bancario es siempre un documento corto y nos interesa la
    cabecera con monto/fecha/referencia.

    Levanta ValueError si el PDF es invalido o no tiene paginas.
    """
    images = pdf2image.convert_from_bytes(
        pdf_bytes,
        dpi=PDF_DPI,
        fmt="png",
        first_page=1,
        last_page=1,
    )
    if not images:
        raise ValueError("PDF sin paginas o ilegible")

    buf = io.BytesIO()
    images[0].save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def preprocess(img_bytes: bytes) -> bytes:
    """Pipeline OpenCV para mejorar legibilidad antes del OCR.

    Pasos:
        1. decode (BGR color)
        2. cvtColor BGR -> GRAY
        3. deskew (sobre grayscale, ver decision tecnica del modulo)
        4. adaptiveThreshold gaussiano -> imagen binaria
        5. crop de margenes blancos (boundingRect del contenido)
        6. encode PNG

    Levanta ValueError si los bytes no son una imagen decodificable.
    """
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("imagen ilegible o corrupta")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    angle = _detect_skew_angle(gray)
    if abs(angle) > SKEW_MIN_ANGLE:
        gray = _rotate(gray, angle)

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        ADAPTIVE_BLOCK_SIZE,
        ADAPTIVE_C,
    )

    cropped = _crop_whitespace(binary)

    ok, encoded = cv2.imencode(".png", cropped)
    if not ok:
        raise RuntimeError("falla al codificar PNG de salida")
    return encoded.tobytes()


def to_base64(img_bytes: bytes) -> str:
    """Codifica bytes en base64 ASCII (formato esperado por llama-server)."""
    return base64.b64encode(img_bytes).decode("ascii")


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _detect_skew_angle(gray: np.ndarray) -> float:
    """Calcula el angulo de inclinacion del texto en grados.

    Estrategia: Otsu para aislar el texto (mas robusto que threshold fijo) y
    minAreaRect sobre las coordenadas de los pixeles oscuros. Devuelve un
    angulo en (-45, 45]. 0.0 si no hay suficiente contenido para estimar.
    """
    _, thresh = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    coords = cv2.findNonZero(thresh)
    if coords is None or len(coords) < MIN_PIXELS_FOR_SKEW:
        return 0.0

    # minAreaRect devuelve angulo en [-90, 0). Lo normalizamos a (-45, 45].
    rect = cv2.minAreaRect(coords)
    angle = float(rect[-1])
    if angle < -45.0:
        angle = 90.0 + angle
    return angle


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    """Rota la imagen `angle` grados alrededor de su centro.

    BORDER_REPLICATE evita bordes negros que ensuciarian el threshold posterior.
    """
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, scale=1.0)
    return cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _crop_whitespace(binary: np.ndarray) -> np.ndarray:
    """Recorta margenes blancos basado en bounding box del contenido.

    `binary` viene del adaptiveThreshold: texto = 0, fondo = 255. Invertimos
    para que findNonZero detecte el texto. Si no hay contenido detectable
    devolvemos la imagen tal cual (no rompemos el pipeline).
    """
    inv = cv2.bitwise_not(binary)
    coords = cv2.findNonZero(inv)
    if coords is None:
        return binary

    x, y, w, h = cv2.boundingRect(coords)
    h_img, w_img = binary.shape[:2]
    x0 = max(0, x - CROP_PADDING_PX)
    y0 = max(0, y - CROP_PADDING_PX)
    x1 = min(w_img, x + w + CROP_PADDING_PX)
    y1 = min(h_img, y + h + CROP_PADDING_PX)
    return binary[y0:y1, x0:x1]


__all__ = [
    "ALLOWED_MIMES",
    "pdf_to_image",
    "preprocess",
    "to_base64",
    "validate_mime",
]
