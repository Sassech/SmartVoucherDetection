"""Generador de datos financieros mexicanos sintéticos para vouchers.

No es un Faker custom provider — es un módulo con funciones que usan
random y Faker('es_MX') internamente.

Uso:
    from scripts.augment.faker_mx import generate_voucher_data
    data = generate_voucher_data("bbva", rng=random.Random(42))
"""

from __future__ import annotations

import random
import string
from datetime import date, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Constantes de banco
# ---------------------------------------------------------------------------

BANCO_SLUGS = [
    "bbva",
    "banorte",
    "santander",
    "banamex",
    "mercadopago",
    "oxxo",
    "bancoppel",
    "banco-azteca",
]

# Prefijos CLABE por banco (primeros 3 dígitos)
_CLABE_PREFIXES: dict[str, str] = {
    "bbva": "012",
    "banorte": "072",
    "santander": "014",
    "banamex": "002",
    "bancoppel": "137",
    "bancoppel-spei": "137",
    "scotiabank": "044",
    "banco-azteca": "127",
    # MP no tiene CLABE
}

_BANK_DISPLAY_NAMES: dict[str, str] = {
    "bbva": "BBVA",
    "banorte": "Banorte",
    "santander": "Santander",
    "banamex": "Banamex",
    "mercadopago": "Mercado Pago",
    "oxxo": "OXXO Pay",
    "bancoppel": "BanCoppel",
    "banco-azteca": "Banco Azteca",
}

_FORMATO_ORIGEN: dict[str, str] = {
    "bbva": "pdf_digital",
    "banorte": "screenshot_movil",
    "santander": "pdf_digital",
    "banamex": "pdf_digital",
    "mercadopago": "screenshot_movil",
    "oxxo": "ticket_impreso",
    "bancoppel": "pdf_digital",
    "banco-azteca": "email_html",
}

_TIPO_OPERACION_OPTIONS = [
    "Transferencia a otros bancos",
    "Transferencia entre cuentas propias",
    "Pago de servicios",
    "Pago de nómina",
    "Depósito de efectivo",
]

_CONCEPTOS = [
    "Pago de servicio",
    "Transferencia",
    "Nómina",
    "Renta",
    "Préstamo personal",
    "Pago de factura",
    "Ahorro",
    "Compra en línea",
    "Reembolso",
    "Pago de deuda",
    "Mantenimiento",
    "Honorarios",
    "Dividendos",
    "Anticipo",
    "Liquidación",
]

_TIPO_VALUES = [
    "spei_recibido",
    "spei_enviado",
    "deposito_efectivo",
    "transferencia_interna",
    "pago_servicio",
    "retiro_cajero",
    "deposito_cheque",
]

_ESTATUS_OPTIONS = ["Liquidada", "Procesada", "Exitosa", "Completada", "Aplicada"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _faker_instance():
    """Lazy-import Faker to avoid startup cost when not needed."""
    try:
        from faker import Faker  # type: ignore[import-untyped]
        return Faker("es_MX")
    except ImportError as exc:
        raise ImportError(
            "faker is required. Install with: uv add --optional scripts faker"
        ) from exc


def _calc_clabe_check_digit(clabe17: str) -> str:
    """Calcula el dígito verificador de una CLABE de 17 dígitos."""
    weights = [3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7]
    total = sum(int(d) * w for d, w in zip(clabe17, weights))
    return str((10 - (total % 10)) % 10)


def _generate_clabe(banco_slug: str, rng: random.Random) -> str:
    """Genera una CLABE válida de 18 dígitos para el banco dado."""
    prefix = _CLABE_PREFIXES.get(banco_slug, "072")  # default banorte
    # Ciudad (3 dígitos): 006=CDMX, 009=Guadalajara, 014=Monterrey, 001=Aguascalientes
    city_codes = ["006", "009", "014", "001", "028", "005", "017"]
    city = rng.choice(city_codes)
    # Número de cuenta: 11 dígitos aleatorios
    cuenta = "".join(str(rng.randint(0, 9)) for _ in range(11))
    clabe17 = prefix + city + cuenta
    check = _calc_clabe_check_digit(clabe17)
    return clabe17 + check


def _mask_clabe(clabe: str) -> str:
    """Enmascara una CLABE mostrando solo los últimos 4 dígitos."""
    return "•••••••••••••" + clabe[-4:]


def _generate_rfc(rng: random.Random, nombre: str | None = None) -> str:
    """Genera un RFC con formato válido (4 letras + 6 dígitos + 3 alfanumérico)."""
    letters = string.ascii_uppercase
    # 4 letras iniciales (simulando iniciales de nombre)
    initials = "".join(rng.choice(letters) for _ in range(4))
    # 6 dígitos fecha (YYMMDD)
    year = rng.randint(50, 99)  # 1950–1999 (personas físicas típicas)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    fecha_rfc = f"{year:02d}{month:02d}{day:02d}"
    # Homoclave: 2 letras + 1 dígito
    homoclave = "".join(rng.choice(letters) for _ in range(2)) + str(rng.randint(0, 9))
    return initials + fecha_rfc + homoclave


def _generate_monto(rng: random.Random) -> float:
    """Genera un monto con distribución realista."""
    bucket = rng.random()
    if bucket < 0.70:
        # 70% bajo $10,000
        monto = rng.uniform(50.0, 9999.99)
    elif bucket < 0.90:
        # 20% $10K–$100K
        monto = rng.uniform(10000.0, 99999.99)
    else:
        # 10% $100K–$500K
        monto = rng.uniform(100000.0, 500000.0)
    # Redondear a 2 decimales, con algunos montos redondos (xx.00)
    if rng.random() < 0.4:
        monto = round(monto / 100) * 100
        monto = max(50.0, monto)
    return round(monto, 2)


def _generate_fecha(rng: random.Random) -> str:
    """Genera una fecha aleatoria dentro de los últimos 3 años."""
    today = date.today()
    days_back = rng.randint(0, 365 * 3)
    target = today - timedelta(days=days_back)
    return target.strftime("%Y-%m-%d")


def _generate_hora(rng: random.Random) -> str:
    """Genera una hora aleatoria HH:MM:SS."""
    h = rng.randint(6, 23)  # horario razonable
    m = rng.randint(0, 59)
    s = rng.randint(0, 59)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _generate_numero_comprobante(rng: random.Random, banco_slug: str) -> str:
    """Genera número de comprobante según banco."""
    if banco_slug == "mercadopago":
        return "#" + str(rng.randint(100000000, 9999999999))
    elif banco_slug == "banco-azteca":
        # Folio 9 dígitos zero-padded
        return f"{rng.randint(1, 999999999):09d}"
    else:
        length = rng.randint(8, 12)
        return str(rng.randint(10 ** (length - 1), 10**length - 1))


def _generate_clave_rastreo(rng: random.Random, banco_slug: str, fecha: str) -> str | None:
    """Genera clave de rastreo según formato específico de banco."""
    if banco_slug == "mercadopago":
        return None  # MP no tiene clave de rastreo

    date_compact = fecha.replace("-", "")[2:]  # YYMMDD

    if banco_slug == "bbva":
        prefixes = ["MBANOI00", "BNET0100", "BBVAM000", "BCMER000"]
        prefix = rng.choice(prefixes)
        seq = rng.randint(1000, 999999)
        return f"{prefix}{date_compact}{seq:06d}"
    elif banco_slug == "banorte":
        seq = rng.randint(100000, 9999999)
        return f"BANORT{seq}"
    elif banco_slug == "santander":
        seq = rng.randint(10000000, 99999999)
        return f"SANTE{date_compact}{seq}"
    elif banco_slug == "banamex":
        seq = rng.randint(100000000, 999999999)
        return f"BNAM{date_compact}{seq}"
    elif banco_slug == "bancoppel":
        seq = rng.randint(1000000, 99999999)
        return f"BCOP{date_compact}{seq}"
    elif banco_slug == "banco-azteca":
        seq = rng.randint(100000, 99999999)
        return f"BAZT{date_compact}{seq}"
    elif banco_slug == "oxxo":
        seq = rng.randint(10000000, 99999999)
        return f"OXXO{date_compact}{seq}"
    else:
        seq = rng.randint(1000000, 99999999)
        return f"SPEI{date_compact}{seq}"


def _generate_oxxo_referencia(rng: random.Random) -> str:
    """OXXO: referencia es tarjeta enmascarada ************XXXX."""
    last4 = str(rng.randint(1000, 9999))
    return "•" * 12 + last4


def _generate_comision(rng: random.Random, banco_slug: str) -> tuple[float, float, float]:
    """Retorna (comision, iva_comision, total_comision).

    OXXO tiene comisión fija en rango $7.76–$16.00.
    El resto casi siempre $0.
    """
    if banco_slug == "oxxo":
        comision = round(rng.uniform(7.76, 16.00), 2)
        iva = round(comision * 0.16, 2)
        total = round(comision + iva, 2)
        return comision, iva, total
    # Ocasionalmente Banorte cobra comisión por transferencia a otros bancos
    if banco_slug == "banorte" and rng.random() < 0.1:
        comision = round(rng.choice([5.80, 7.00, 10.00, 15.00]), 2)
        iva = round(comision * 0.16, 2)
        return comision, iva, round(comision + iva, 2)
    return 0.0, 0.0, 0.0


def _pick_receptor_bank(banco_slug: str, rng: random.Random) -> str:
    """Elige banco receptor diferente al emisor."""
    all_banks = [
        "BBVA", "Banorte", "Santander", "Banamex", "HSBC",
        "Scotiabank", "Inbursa", "BanCoppel", "Banco Azteca",
        "Hey Banco", "Spin by OXXO",
    ]
    display = _BANK_DISPLAY_NAMES.get(banco_slug, "BBVA")
    candidates = [b for b in all_banks if b != display]
    return rng.choice(candidates)


# ---------------------------------------------------------------------------
# Generador principal
# ---------------------------------------------------------------------------


def generate_voucher_data(
    banco: str,
    rng: random.Random,
    tipo: str = "spei_recibido",
    seq: int = 1,
) -> dict[str, Any]:
    """Genera datos completos de voucher sintético para el banco dado.

    Args:
        banco:  Slug de banco (ej. "bbva", "banorte").
        rng:    Instancia de random.Random para reproducibilidad.
        tipo:   Tipo de operación (si None, se elige aleatoriamente).
        seq:    Número secuencial del voucher (para IDs únicos).

    Returns:
        Dict con todos los campos del ground-truth schema v2.0.
    """
    fk = _faker_instance()

    banco_slug = banco.lower().replace(" ", "-")
    banco_display = _BANK_DISPLAY_NAMES.get(banco_slug, banco)

    # Datos base
    monto = _generate_monto(rng)
    fecha = _generate_fecha(rng)
    hora = _generate_hora(rng)

    # Tipo de operación: ciclo por todos los valores o el especificado
    tipo_operacion = rng.choice(_TIPO_VALUES)

    # Nombres
    nombre_ordenante = fk.name()
    nombre_beneficiario = fk.name()
    rfc_ordenante = _generate_rfc(rng)

    # CLABEs
    if banco_slug == "mercadopago":
        clabe_emisor = None
        clabe_emisor_mascara = None
    else:
        clabe_emisor = _generate_clabe(banco_slug, rng)
        clabe_emisor_mascara = _mask_clabe(clabe_emisor)

    # Banco receptor y su CLABE
    banco_receptor = _pick_receptor_bank(banco_slug, rng)
    receptor_slug = banco_receptor.lower().replace(" ", "-").replace("á", "a").replace("é", "e")
    if banco_slug == "oxxo":
        # OXXO: referencia enmascarada tipo tarjeta
        clabe_receptor_mascara = _generate_oxxo_referencia(rng)
        clabe_receptor = None
    else:
        clabe_receptor = _generate_clabe(receptor_slug, rng)
        clabe_receptor_mascara = _mask_clabe(clabe_receptor)

    # Comprobante y referencia
    numero_comprobante = _generate_numero_comprobante(rng, banco_slug)
    if banco_slug == "oxxo":
        numero_referencia = _generate_oxxo_referencia(rng)
    else:
        ref_len = rng.randint(6, 10)
        numero_referencia = str(rng.randint(10 ** (ref_len - 1), 10**ref_len - 1))

    # Clave de rastreo
    clave_rastreo = _generate_clave_rastreo(rng, banco_slug, fecha)

    # Concepto
    concepto = rng.choice(_CONCEPTOS)

    # Comisiones
    comision, iva_comision, _total_comision = _generate_comision(rng, banco_slug)

    # Folio (Banco Azteca lo tiene en formato 9 dígitos)
    if banco_slug == "banco-azteca":
        folio = f"{rng.randint(1, 999999999):09d}"
    else:
        folio = None

    # Importe transferido (puede diferir del monto si hay comisión)
    importe_transferido = monto
    importe_total = round(monto + comision + iva_comision, 2)

    # ID del voucher
    voucher_id = f"syn-{banco_slug}-{seq:04d}"

    return {
        "id": voucher_id,
        "schema_version": "2.0",
        "banco_emisor": banco_display,
        "banco_receptor": banco_receptor,
        "monto": monto,
        "moneda": "MXN",
        "fecha": fecha,
        "hora": hora[:5],  # HH:MM (sin segundos para el campo principal)
        "numero_comprobante": numero_comprobante,
        "numero_referencia": numero_referencia,
        "motivo": concepto,
        "clabe_emisor_mascara": clabe_emisor_mascara,
        "clabe_receptor_mascara": clabe_receptor_mascara,
        "tipo": tipo_operacion,
        "formato_origen": _FORMATO_ORIGEN.get(banco_slug, "pdf_digital"),
        "calidad": "alta",
        "notas": "",
        "synthetic": {
            "template": banco_slug,
            "degradations": [],
            "base_id": None,
        },
        "extended": {
            "clave_rastreo": clave_rastreo,
            "concepto": concepto,
            "comision": comision,
            "iva": 0.0,
            "iva_comision": iva_comision,
            "folio": folio,
            "nombre_ordenante": nombre_ordenante,
            "nombre_beneficiario": nombre_beneficiario,
            "rfc_ordenante": rfc_ordenante,
            "estatus": rng.choice(_ESTATUS_OPTIONS),
            "tipo_operacion": rng.choice(_TIPO_OPERACION_OPTIONS),
            "importe_transferido": importe_transferido,
            "importe_total": importe_total,
            "pais": "MX",
            # Internal helpers (used by templates, not stored in final JSON)
            "_hora_full": hora,
            "_nombre_ordenante_short": nombre_ordenante.split()[0],
            "_nombre_beneficiario_short": nombre_beneficiario.split()[0],
            "_clabe_emisor": clabe_emisor,
            "_clabe_receptor": clabe_receptor,
        },
    }


def format_monto(monto: float, currency: str = "MXN") -> str:
    """Formatea un monto como string de moneda mexicana."""
    return f"${monto:,.2f}"


def format_fecha_larga(fecha_str: str) -> str:
    """Convierte '2024-06-02' → '02 DE JUNIO DEL 2024'."""
    meses = [
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    ]
    try:
        d = datetime.strptime(fecha_str, "%Y-%m-%d")
        return f"{d.day:02d} DE {meses[d.month - 1]} DEL {d.year}"
    except ValueError:
        return fecha_str


def format_fecha_display(fecha_str: str) -> str:
    """Convierte '2024-06-02' → '02/06/2024'."""
    try:
        d = datetime.strptime(fecha_str, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return fecha_str
