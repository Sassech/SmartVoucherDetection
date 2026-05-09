"""Tests de api/services/parser_service.py.

Estrategia: parametrize-heavy. El parser es codigo puro (sin red, sin DB,
sin async), asi que la cobertura se hace con tablas de casos sucios
(input crudo del LLM) -> salida esperada. El objetivo es atrapar
regresiones cuando alguien toque las regex / umbrales.
"""

from datetime import date
from decimal import Decimal

import pytest

from services.parser_service import (
    compute_hash,
    normalize_banco,
    parse_fecha,
    parse_monto,
    parse_referencia,
)


# ---------------------------------------------------------------------------
# parse_monto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Tipos numericos nativos del LLM (prompt pide "numero decimal")
        (1234.56, Decimal("1234.56")),
        (1234, Decimal("1234")),
        (0, Decimal("0")),
        (0.0, Decimal("0.0")),
        # Strings US/MX-style
        ("1234.56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("MXN 1,234.56", Decimal("1234.56")),
        ("$ 1,234.56 MXN", Decimal("1234.56")),
        ("1234", Decimal("1234")),
        # Whitespace y separadores raros
        ("  1234.56  ", Decimal("1234.56")),
        ("1,000,000.00", Decimal("1000000.00")),
        # Casos "solo coma" (interpretacion: separador de miles, no decimal)
        ("1,234", Decimal("1234")),
    ],
)
def test_parse_monto_happy_paths(raw, expected):
    assert parse_monto(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "abc",
        "$",
        "MXN",
        "1.2.3",  # multiples puntos -> ambiguo
        "-100",  # negativos no validos (CHECK constraint en DB)
        -100,
        -0.01,
        [1, 2, 3],  # tipo no soportado
        {"monto": 100},
    ],
)
def test_parse_monto_returns_none_on_invalid(raw):
    assert parse_monto(raw) is None


def test_parse_monto_avoids_float_precision_artifacts():
    """`Decimal(0.1)` da `0.1000000000000000055...`. Pasamos por str para evitarlo."""
    result = parse_monto(0.1)
    assert result == Decimal("0.1")


# ---------------------------------------------------------------------------
# parse_fecha
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Formato canonico del prompt OCR
        ("01/05/2026", date(2026, 5, 1)),
        ("31/12/2025", date(2025, 12, 31)),
        # ISO (a veces el LLM ignora el formato pedido)
        ("2026-05-01", date(2026, 5, 1)),
        # Variantes con guion
        ("01-05-2026", date(2026, 5, 1)),
        # Espacios externos
        ("  01/05/2026  ", date(2026, 5, 1)),
        # Mes nombrado en ingles (dateutil lo entiende)
        ("1 May 2026", date(2026, 5, 1)),
    ],
)
def test_parse_fecha_happy_paths(raw, expected):
    assert parse_fecha(raw) == expected


def test_parse_fecha_dayfirst_resolves_ambiguity():
    """01/02/2026 con dayfirst=True -> 1 de febrero (no 2 de enero)."""
    assert parse_fecha("01/02/2026") == date(2026, 2, 1)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "no es fecha",
        "32/13/2026",  # dia/mes invalidos
        "abc/def/ghi",
        12345,  # tipo no soportado
    ],
)
def test_parse_fecha_returns_none_on_invalid(raw):
    assert parse_fecha(raw) is None


# ---------------------------------------------------------------------------
# parse_referencia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ref-123", "REF-123"),
        ("  pago-987  ", "PAGO-987"),
        ("REF   456", "REF 456"),  # colapsa espacios internos
        ("ref\t\n789", "REF 789"),  # otros whitespace
        ("REF-123/A", "REF-123/A"),  # preserva simbolos
        ("a", "A"),
    ],
)
def test_parse_referencia_happy_paths(raw, expected):
    assert parse_referencia(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "\n\t  ", 123])
def test_parse_referencia_returns_none_on_empty_or_invalid(raw):
    assert parse_referencia(raw) is None


# ---------------------------------------------------------------------------
# normalize_banco
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Match exacto contra nombre canonico
        ("BBVA", "BBVA"),
        ("Banorte", "Banorte"),
        ("HSBC", "HSBC"),
        ("Santander", "Santander"),
        # Aliases
        ("Bancomer", "BBVA"),
        ("BBVA Bancomer", "BBVA"),
        ("Banamex", "Citibanamex"),
        ("Citibanamex", "Citibanamex"),
        ("Hey Banco", "Hey Banco"),
        ("Nu Bank", "Nu Bank"),
        ("nubank", "Nu Bank"),
        # Variaciones de caso/acentos/espacios
        ("BANORTE", "Banorte"),
        ("  santander  ", "Santander"),
        ("BBVA México", "BBVA"),
        # Errores tipicos del OCR (gotcha: GLM-OCR confunde caracteres)
        ("Santandar", "Santander"),  # 1 char de error
        ("Banortte", "Banorte"),  # char extra
    ],
)
def test_normalize_banco_happy_paths(raw, expected):
    assert normalize_banco(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "Banco Inventado",
        "Wells Fargo",  # banco real pero fuera del catalogo MX
        "xxxxxxxxxxxx",
        12345,
    ],
)
def test_normalize_banco_falls_back_to_otro(raw):
    assert normalize_banco(raw) == "OTRO"


def test_normalize_banco_does_not_confuse_short_aliases():
    """`hey` y `nu` son aliases cortos: input "hello" no debe matchear `hey`."""
    # "hello" normalizado = "hello"; ratio contra "hey" = 0.5, bajo umbral.
    assert normalize_banco("hello") == "OTRO"


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------


def test_compute_hash_deterministic():
    payload = b"hola mundo"
    assert compute_hash(payload) == compute_hash(payload)


def test_compute_hash_different_for_different_inputs():
    assert compute_hash(b"a") != compute_hash(b"b")


def test_compute_hash_known_value():
    """Sanity check contra valor conocido de SHA-256."""
    # echo -n "" | sha256sum
    assert (
        compute_hash(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_compute_hash_returns_hex_lowercase_64chars():
    h = compute_hash(b"x")
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_hash_accepts_bytearray_and_memoryview():
    """Aceptar bytes-like generales — un upload puede llegar como bytearray."""
    payload = b"comprobante"
    assert compute_hash(bytearray(payload)) == compute_hash(payload)
    assert compute_hash(memoryview(payload)) == compute_hash(payload)


def test_compute_hash_rejects_non_bytes():
    with pytest.raises(TypeError):
        compute_hash("no soy bytes")  # type: ignore[arg-type]
