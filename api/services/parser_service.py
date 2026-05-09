"""Servicio de parseo y normalizacion de campos crudos del OCR.

Responsabilidad UNICA: tomar los valores crudos que devolvio `ocr_service`
(que pueden ser str, int, float, None — tal como los emitio el LLM) y
convertirlos a tipos de dominio (Decimal, date, str canonico). NO toca
red, NO toca DB, NO conoce el modelo OCR.

Politica ante input invalido (decision del PROGRESO 1.5, opcion A):
- TODAS las funciones devuelven `None` (o "OTRO" en banco) ante input
  vacio/invalido en lugar de levantar excepcion. El endpoint de upload
  decide despues si la falta de campos criticos amerita marcar el
  comprobante como `error`.
- La unica excepcion deliberada es `compute_hash`: opera sobre bytes y
  no tiene nocion de "input invalido" — bytes vacios son hash valido.

Decisiones tecnicas (PROGRESO 1.5):
- `parse_monto`: asume formato US/MX bancario ("$1,234.56" — coma=miles,
  punto=decimal). Heuristicas europeas se evaluan en Fase 5 con dataset real.
- `normalize_banco`: fuzzy match con `Levenshtein.ratio` >= UMBRAL contra
  catalogo cerrado. GLM-OCR confunde caracteres (gotcha PROGRESO
  2026-05-08, MEXICO->MAXICO), un match exacto perderia ~10-15% segun
  pruebas informales.
- `parse_fecha`: `dateutil.parser` con `dayfirst=True` porque el prompt
  OCR pide DD/MM/YYYY explicitamente.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final

import Levenshtein
from dateutil import parser as date_parser

# ---------------------------------------------------------------------------
# parse_monto
# ---------------------------------------------------------------------------

# Conservamos digitos, punto, coma y signo `-`. El signo se preserva en
# la limpieza para que un input como "-100" llegue a Decimal con valor
# negativo y sea rechazado por el chequeo final (`value >= 0`). Si lo
# tirasemos aca, "-100" se convertiria silenciosamente en 100.
# El CHECK del modelo Comprobante (`monto >= 0 OR NULL`) refuerza esto
# en DB; aca lo cazamos antes para devolver `None` limpio.
_MONTO_CLEAN_RE: Final = re.compile(r"[^0-9.,\-]")


def parse_monto(raw: str | int | float | None) -> Decimal | None:
    """Convierte el monto crudo del OCR a `Decimal` con 2 decimales.

    Acepta numeros nativos (el LLM a veces devuelve `1234.56` directo) o
    strings con simbolos ("$1,234.56", "MXN 1.234,56" — pero ojo, ver
    docstring del modulo: solo soportamos US-style).

    Returns:
        `Decimal` con la cantidad, o `None` si el input es vacio /
        no contiene digitos / produce un Decimal invalido / es negativo.
    """
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        # Pasar via str evita problemas de precision binaria de float
        # (Decimal(1.1) -> 1.1000000000000000888...).
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            return None
        return value if value >= 0 else None

    if not isinstance(raw, str):
        return None

    cleaned = _MONTO_CLEAN_RE.sub("", raw).strip()
    if not cleaned:
        return None

    # US/MX-style: coma = separador de miles, descartar.
    cleaned = cleaned.replace(",", "")

    # Multiples puntos -> ambiguo, rechazar.
    if cleaned.count(".") > 1:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None

    return value if value >= 0 else None


# ---------------------------------------------------------------------------
# parse_fecha
# ---------------------------------------------------------------------------


# Detector de formato ISO (YYYY-MM-DD): si el LLM ignora el prompt y
# devuelve ISO, dayfirst=True lo interpreta mal (2026-05-01 -> 5 de enero
# porque toma "01" como dia). Para ISO usamos yearfirst=True.
_ISO_DATE_RE: Final = re.compile(r"^\s*\d{4}-\d{1,2}-\d{1,2}\s*$")


def parse_fecha(raw: str | None) -> date | None:
    """Parsea fecha cruda del OCR a `datetime.date`.

    Heuristica de formato:
        - Si el string parece ISO (`YYYY-MM-DD`) -> `yearfirst=True`.
        - En cualquier otro caso -> `dayfirst=True` (el prompt OCR pide
          DD/MM/YYYY, formato dominante en MX).

    Acepta tambien formatos sucios que el LLM puede devolver: "1 May 2026",
    "01-05-2026", etc. — `dateutil` los maneja con la heuristica anterior.
    """
    if raw is None or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None

    is_iso = bool(_ISO_DATE_RE.match(cleaned))

    try:
        # `fuzzy=False` a proposito: si llega "Fecha: 01/05/2026 ref X",
        # preferimos rechazar antes que adivinar. El OCR ya nos da el
        # campo aislado segun el prompt.
        parsed = date_parser.parse(
            cleaned,
            dayfirst=not is_iso,
            yearfirst=is_iso,
        )
    except (ValueError, OverflowError, date_parser.ParserError):
        return None

    return parsed.date()


# ---------------------------------------------------------------------------
# parse_referencia
# ---------------------------------------------------------------------------

_WHITESPACE_RE: Final = re.compile(r"\s+")


def parse_referencia(raw: str | None) -> str | None:
    """Normaliza la referencia: strip + uppercase + colapsa espacios internos.

    No quita simbolos: "REF-123/A" se preserva tal cual. La idea es no
    perder informacion estructural del comprobante; el matching de Fase 2
    usa similarity, no equality, asi que respetar el formato original
    ayuda al scoring.

    Returns:
        Referencia normalizada, o `None` si despues del strip queda vacia.
    """
    if raw is None or not isinstance(raw, str):
        return None

    cleaned = _WHITESPACE_RE.sub(" ", raw).strip().upper()
    return cleaned or None


# ---------------------------------------------------------------------------
# normalize_banco
# ---------------------------------------------------------------------------

# Catalogo cerrado del PROGRESO 1.5.4. La key es el nombre canonico
# (lo que se persiste en DB); los valores son aliases conocidos para el
# fuzzy match. Todos los aliases se comparan ya normalizados (lower,
# sin acentos, sin espacios, solo alfanumerico).
_BANCO_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "BBVA": ("bbva", "bbvabancomer", "bancomer"),
    "Citibanamex": ("citibanamex", "banamex", "citibanex", "citi"),
    "Banorte": ("banorte",),
    "HSBC": ("hsbc",),
    "Santander": ("santander",),
    "Hey Banco": ("heybanco", "hey"),
    "Nu Bank": ("nubank", "nu"),
}

# Umbral elegido empiricamente: 0.85 tolera 1 char de error en strings
# de 7+ caracteres ("santander" vs "santandar" -> 0.888) sin meter falsos
# positivos entre bancos del catalogo (la distancia minima entre 2 nombres
# del catalogo normalizados es bbva<->hsbc -> 0.0). Ajustable en Fase 5.
_BANCO_FUZZY_THRESHOLD: Final = 0.85

# Aliases >= a esta longitud se buscan tambien como SUBSTRING dentro del
# input normalizado. Cubre casos donde el LLM devuelve frases como
# "BBVA Mexico" o "Santander Banco SA": el ratio Levenshtein contra el
# alias corto cae por la diferencia de longitud, pero el alias aparece
# textualmente dentro. Aliases mas cortos (`hey`, `nu`, `citi`) NO usan
# substring para evitar falsos positivos en palabras que los contengan
# casualmente (ej: "nuevo", "heroe").
_BANCO_SUBSTRING_MIN_LEN: Final = 4

_NON_ALPHANUM_RE: Final = re.compile(r"[^a-z0-9]")


def _normalize_for_match(s: str) -> str:
    """Lower + sin acentos + sin espacios + solo alfanumerico.

    NFKD descompone "é" en "e" + acento combinante, ascii() descarta los
    no-ascii. Es la forma mas portable sin pulling `unidecode`.
    """
    decomposed = unicodedata.normalize("NFKD", s)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return _NON_ALPHANUM_RE.sub("", ascii_only.lower())


def normalize_banco(raw: str | None) -> str:
    """Mapea el banco crudo del OCR al catalogo canonico via fuzzy match.

    Algoritmo:
        1. Normalizar input (lower, sin acentos/espacios/simbolos).
        2. Si vacio -> "OTRO".
        3. Por cada banco del catalogo, calcular `ratio` contra TODOS sus
           aliases y quedarse con el mejor.
        4. El banco con mejor ratio gana, siempre que supere el umbral.
        5. Sin ganador -> "OTRO".

    Returns:
        Nombre canonico del banco (ej: "BBVA"), o "OTRO" si no hay match
        confiable. NUNCA devuelve `None` — `OTRO` es el fallback explicito
        del catalogo.
    """
    if raw is None or not isinstance(raw, str):
        return "OTRO"

    normalized = _normalize_for_match(raw)
    if not normalized:
        return "OTRO"

    best_banco = "OTRO"
    best_ratio = 0.0

    for banco, aliases in _BANCO_ALIASES.items():
        for alias in aliases:
            # Substring match: forzar ratio=1.0 si el alias (>=4 chars)
            # esta contenido en el input. Cubre "BBVA Mexico" -> BBVA.
            if len(alias) >= _BANCO_SUBSTRING_MIN_LEN and alias in normalized:
                return banco
            ratio = Levenshtein.ratio(normalized, alias)
            if ratio > best_ratio:
                best_ratio = ratio
                best_banco = banco

    return best_banco if best_ratio >= _BANCO_FUZZY_THRESHOLD else "OTRO"


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------


def compute_hash(image_bytes: bytes) -> str:
    """SHA-256 hex de los bytes ORIGINALES del archivo (pre-preprocess).

    Esto es la Capa 1 de deduplicacion (PROGRESO 2.1): si dos uploads
    tienen exactamente el mismo hash, son el mismo archivo binario y
    podemos cortocircuitar sin pasar por OCR.

    IMPORTANTE: hashear ANTES de cualquier procesamiento de imagen. El
    pipeline de `image_service.preprocess` es deterministico pero
    introduce variaciones (compresion PNG, padding del crop) que romperian
    la equivalencia de hash entre el upload original y un re-upload.
    """
    if not isinstance(image_bytes, (bytes, bytearray, memoryview)):
        raise TypeError("compute_hash espera bytes-like")
    return hashlib.sha256(image_bytes).hexdigest()
