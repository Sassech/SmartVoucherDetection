"""Anonimizador de comprobantes bancarios mexicanos.

Flujo por imagen:
    1. Validar MIME (validate_mime de image_service)
    2. Obtener texto OCR vía llama-server (get_ocr_client + extract_fields)
    3. Detectar datos sensibles con regex (CLABE, tarjeta, referencia)
    4. Aplicar blur PIL adaptativo (top 40% + bottom strip con nombre/CLABE)
    5. Guardar anonymized/{id}.jpg sin EXIF
    6. Escribir ground-truth/{id}.json (schema v2.0)

Schema v2.0 agrega sobre v1.0:
    - banco_emisor / banco_receptor (split de banco)
    - numero_comprobante / numero_referencia (split de referencia)
    - moneda, hora, motivo
    - clabe_emisor_mascara / clabe_receptor_mascara
    - synthetic: null (null en reales, objeto en sintéticos)

Uso:
    uv run python scripts/anonymize/anonymize_comprobante.py --help
    uv run python scripts/anonymize/anonymize_comprobante.py \\
        --input dataset/bancario-mx/raw/ \\
        --output-dir dataset/bancario-mx/anonymized/ \\
        --gt-dir dataset/bancario-mx/ground-truth/ \\
        --id-prefix mx

Exit 0: éxito (todas las imágenes procesadas)
Exit 1: error (MIME inválido, imagen corrupta, error de escritura)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Bootstrap: inserta api/ en sys.path antes de cualquier import de api/
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from _shared import get_ocr_client, setup_api_path  # noqa: E402

setup_api_path()

# ---------------------------------------------------------------------------
# Patrones regex para datos sensibles (D-14)
# ---------------------------------------------------------------------------

# CLABE: 18 dígitos contiguos
_RE_CLABE = re.compile(r"\b\d{18}\b")

# Número de tarjeta: 16 dígitos con separadores opcionales
_RE_CARD = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")

# Referencia alfanumérica: 8–20 chars mayúsculas/dígitos
_RE_REF = re.compile(r"\b[A-Z0-9]{8,20}\b")

# Número de comprobante: # seguido de 6–15 dígitos
# Cubre MercadoPago (#154709419317), Banamex (#764877), Citibanamex (#009079)
_RE_COMPROBANTE = re.compile(r"#\s*(\d{6,15})")

# Número de referencia numérica: 5–15 dígitos
# Cubre "Número de referencia: 33426", "Referencia numérica: 210217", "Referencia numérica 1458110"
_RE_REFERENCIA_NUM = re.compile(
    r"(?:N[úu]mero\s+de\s+referencia|Referencia\s+num[eé]rica|Referencia)[:\s]+(\d{5,15})",
    re.IGNORECASE,
)

# Hora: HH:MM (con o sin segundos)
_RE_HORA = re.compile(r"\b(\d{1,2}:\d{2})(?::\d{2})?\b")

# Motivo / concepto: línea que sigue a "Motivo:" o "Concepto:"
_RE_MOTIVO = re.compile(r"(?:Motivo|Concepto)[:\s]+(.+?)(?:\n|$)", re.IGNORECASE)

# CLABE enmascarada por MercadoPago: **** o ****NNNN
_RE_CLABE_MASK = re.compile(r"\*{4,7}(\d{4})")

# Clave de rastreo SPEI: alfanumérico 20-40 chars
_RE_CLAVE_RASTREO = re.compile(r"(?:Clave de rastreo|CLABE rastreo|clave_rastreo)[:\s]+([A-Z0-9]{15,40})", re.IGNORECASE)

# Comisión: cubre "Comisión:", "COMISION DEL BANCO:", "TOTAL COMISION:"
# También tolera prefijos de moneda como "M.N. $" antes del número (OXXO).
_RE_COMISION = re.compile(
    r"(?:(?:TOTAL\s+)?COMISI[OÓ]N(?:\s+DEL\s+BANCO)?)[:\s]+(?:M\.?N\.?\s*)?\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# IVA: número decimal precedido de "IVA:"
_RE_IVA = re.compile(r"\bIVA[:\s]+\$?\s*([\d,]+\.?\d*)", re.IGNORECASE)

# Folio: número precedido de "Folio", "Folio de internet", "FOLIO NUMERO", etc.
_RE_FOLIO = re.compile(r"(?:Folio(?:\s+de\s+internet)?|FOLIO(?:\s+NUMERO)?)[:\s#]+([A-Z0-9]{4,20})", re.IGNORECASE)

# Número de transacción: cubre "N° Transacción:", "No. Transacción:", "número de transacción"
# Formatos largos como "20190725220110402971" (Santander Chile) o "#764877" (BanCoppel)
_RE_NUM_TRANSACCION = re.compile(
    r"(?:N[°º]\.?\s*Transacci[oó]n|n[uú]mero\s+de\s+transacci[oó]n)[:\s#]+(\d{6,25})",
    re.IGNORECASE,
)

# Tipo de operación: línea que sigue a "Tipo de operación:" o "Operación:"
_RE_TIPO_OP = re.compile(r"(?:Tipo de operaci[oó]n|Operaci[oó]n)[:\s]+(.+?)(?:\n|$)", re.IGNORECASE)

# Concepto de pago
_RE_CONCEPTO = re.compile(r"(?:Concepto(?:\s+de\s+pago)?|Descripci[oó]n)[:\s]+(.+?)(?:\n|$)", re.IGNORECASE)

# Estatus de operación
_RE_ESTATUS = re.compile(r"(?:Estatus|Estado|Status)[:\s]+(.+?)(?:\n|$)", re.IGNORECASE)

# Monto genérico desde PDF text: captura cualquier etiqueta de importe/monto
# cuando el OCR devuelve null — fallback para layouts no estándar (BanCoppel, etc.)
_RE_MONTO_PDF = re.compile(
    r"(?:Monto|Importe|Amount)[:\s]+\$?\s*([\d,\.]+)\s*(?:MXN|MN|USD)?",
    re.IGNORECASE,
)

# Importe transferido: etiqueta "Importe transferido" o "Importe giro" (BBVA, Banorte)
_RE_IMPORTE_TRANSFERIDO = re.compile(
    r"(?:Importe\s+transferido|Importe\s+giro)[:\s]+\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Monto base OXXO: línea "MONTO : M.N. $ 600.00" — aparece ANTES de comisión.
# Patrón específico: "MONTO" seguido de separadores y opcionalmente "M.N. $".
# Se diferencia del monto principal porque en OXXO la etiqueta es exactamente "MONTO".
_RE_MONTO_BASE_OXXO = re.compile(
    r"^[\s\-]*MONTO\s*[:\s]+(?:M\.?N\.?\s*)?\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE | re.MULTILINE,
)

# Importe total / pago total: incluye monto + comisión (OXXO, Banorte, BanCoppel).
# Etiquetas exactas aceptadas — NO matchea "TOTAL COMISION" (eso es el subtotal de comisión):
#   "PAGO TOTAL."  → OXXO
#   "Cantidad Total:" → Banorte / BanCoppel
#   "Importe a debitar:" → BBVA Uruguay
# Usa negative lookahead para excluir "TOTAL COMISION" y "TOTAL COMISION DEL BANCO".
_RE_IMPORTE_TOTAL = re.compile(
    r"(?:PAGO\s+TOTAL|Cantidad\s+Total|Importe\s+a\s+debitar)"
    r"[.:\s]+(?:M\.?N\.?\s*)?\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Extensiones de imagen soportadas
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".pdf"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _anonymize_text(text: str) -> str:
    """Aplica sustituciones regex sobre el texto OCR extraído."""
    # CLABE: conservar últimos 4 dígitos
    def _replace_clabe(m: re.Match) -> str:
        return f"****{m.group()[-4:]}"

    # Tarjeta: conservar últimos 4 dígitos (sin separadores)
    def _replace_card(m: re.Match) -> str:
        digits = re.sub(r"[\s\-]", "", m.group())
        return f"****{digits[-4:]}"

    # Referencia: hash SHA-256 primeros 8 chars en mayúsculas
    def _replace_ref(m: re.Match) -> str:
        digest = hashlib.sha256(m.group().encode()).hexdigest()
        return f"REF-{digest[:8].upper()}"

    text = _RE_CLABE.sub(_replace_clabe, text)
    text = _RE_CARD.sub(_replace_card, text)
    text = _RE_REF.sub(_replace_ref, text)
    return text


def _load_image_bytes(image_path: Path) -> bytes:
    """Lee la imagen como bytes, convirtiendo PDF → PNG si es necesario.

    Para archivos PDF llama a pdf_to_image() (primera página, 300dpi) y
    devuelve PNG bytes. Para cualquier otro formato devuelve los bytes crudos.
    La conversión es lazy (import interno) para evitar imports circulares.
    """
    raw = image_path.read_bytes()
    if image_path.suffix.lower() == ".pdf":
        from services.image_service import pdf_to_image  # type: ignore[import-untyped]
        return pdf_to_image(raw)
    return raw


def _apply_pil_blur(img_bytes: bytes) -> bytes:
    """Abre la imagen desde bytes, aplica blur en zonas con datos personales y retorna JPEG sin EXIF.

    Estrategia de 3 franjas (layout MercadoPago Wallet y similares):
      - Top 15%:    logo + header (banco, tipo de operación)
      - Middle 55–85%: sección "De / Para" con nombres, CLABE, email
      - Bottom 5%:  número de comprobante al pie

    Las franjas de monto (15–55%) y fecha permanecen nítidas para que
    el OCR las lea correctamente ANTES de que se aplique este blur.

    Nota: el blur se aplica DESPUÉS del OCR — la imagen original nunca
    se modifica, solo el output guardado en anonymized/.
    """
    import io

    from PIL import Image, ImageFilter  # type: ignore[import-untyped]

    with Image.open(io.BytesIO(img_bytes)) as img:
        img = img.convert("RGB")
        w, h = img.size

        rois = [
            (0, 0,             w, int(h * 0.15)),   # top: logo / header
            (0, int(h * 0.45), w, int(h * 0.90)),  # medio: De/Para, nombres, CLABE, email
            (0, int(h * 0.90), w, h),               # pie: número comprobante / ID transacción
        ]
        for roi in rois:
            region = img.crop(roi)
            img.paste(region.filter(ImageFilter.GaussianBlur(radius=18)), roi)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def _safe_float(value: object) -> float:
    """Convierte a float tolerando comas de miles, monedas y sufijos/prefijos variados.

    Maneja:
      "3,000.MXN"   → 3000.0   (sufijo 3-letras)
      "4,651.23 MN" → 4651.23  (sufijo 2-letras: MN = moneda nacional MX)
      "$500.00 MXN" → 500.0    (prefijo $ + sufijo)
      "3.675,00"    → 3675.0   (formato europeo coma decimal — Argentina/Uruguay)
      "−263"        → -263.0   (guión largo unicode)
    """
    if value is None:
        return 0.0
    s = str(value).strip()
    # Eliminar sufijos de moneda (MXN, USD, MN, CLP, ARS, etc.) al final
    s = re.sub(r"\s*[A-Z]{2,3}$", "", s).strip()
    # Eliminar prefijo/sufijo de símbolo monetario
    s = s.replace("$", "").replace("¢", "").strip()
    # Detectar formato europeo: si hay punto de miles y coma decimal (ej. "3.675,00")
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        # Formato estándar: eliminar comas de miles
        s = s.replace(",", "")
    # Manejar negativos con guión largo unicode
    s = s.replace("−", "-").replace(" ", "")
    # Normalizar punto al final sin decimales
    s = s.rstrip(".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_extra_fields(ocr_fields: dict, pdf_text: str = "") -> dict:
    """Extrae campos adicionales del texto OCR y pdf_text para schema v2.0.

    pdf_text: texto completo extraído con pdftotext (vacío para imágenes JPEG/PNG).
    Permite encontrar etiquetas reales del documento que el OCR no captura como
    campos estructurados (numero_comprobante en PDFs, numero_referencia, etc.).
    """
    ocr_raw = str(ocr_fields.get("raw_text") or ocr_fields.get("referencia") or "")
    # Combinar pdf_text + OCR raw para búsqueda de patrones
    raw = f"{pdf_text} {ocr_raw}".strip() if pdf_text else ocr_raw

    # hora: el OCR prompt ahora la extrae directamente como campo "hora".
    # Fallback: buscar HH:MM en el campo "fecha" (modelos que ignoran el campo)
    # y luego en raw/referencia como último recurso.
    hora = str(ocr_fields.get("hora") or "")
    if not hora:
        fecha_raw = str(ocr_fields.get("fecha") or "")
        hora_m = _RE_HORA.search(fecha_raw) or _RE_HORA.search(raw)
        hora = hora_m.group(1) if hora_m else ""

    # numero_comprobante: #XXXXXXXXX al pie del comprobante
    comprobante_m = _RE_COMPROBANTE.search(raw)
    numero_comprobante = comprobante_m.group(1) if comprobante_m else ""

    # numero_referencia: "Número de referencia: XXXXXX"
    ref_m = _RE_REFERENCIA_NUM.search(raw)
    numero_referencia = ref_m.group(1) if ref_m else ""

    # motivo: texto después de "Motivo:" (puede ser vacío o emoji)
    motivo_m = _RE_MOTIVO.search(raw)
    motivo = motivo_m.group(1).strip() if motivo_m else ""

    # CLABEs enmascaradas: MercadoPago muestra ****8919 / ****5381
    mascaras = _RE_CLABE_MASK.findall(raw)
    clabe_emisor_mascara = f"****{mascaras[0]}" if len(mascaras) > 0 else ""
    clabe_receptor_mascara = f"****{mascaras[1]}" if len(mascaras) > 1 else ""

    # banco_receptor: cuando el destino es banco externo (ej. "BBVA MEXICO")
    banco_receptor = str(ocr_fields.get("banco_receptor") or "")

    return {
        "numero_comprobante": numero_comprobante,
        "numero_referencia": numero_referencia,
        "hora": hora,
        "motivo": motivo,
        "clabe_emisor_mascara": clabe_emisor_mascara,
        "clabe_receptor_mascara": clabe_receptor_mascara,
        "banco_receptor": banco_receptor,
    }


def _extract_extended_fields(ocr_fields: dict, raw_text: str) -> dict:
    """Extrae el bloque 'extended' del schema v2.0 desde los campos OCR y texto crudo.

    raw_text debe ser los valores OCR concatenados (join de ocr_fields.values()).
    Los campos de nombre/RFC siempre quedan vacíos: son datos personales que no
    se extraen ni almacenan (solo se anotan para revisión manual si fuera necesario).
    """
    # clave_rastreo: regex sobre raw_text, fallback al campo OCR directo
    cr_m = _RE_CLAVE_RASTREO.search(raw_text)
    clave_rastreo = cr_m.group(1) if cr_m else str(ocr_fields.get("clave_rastreo") or "")

    # concepto de pago
    concepto_m = _RE_CONCEPTO.search(raw_text)
    concepto = concepto_m.group(1).strip() if concepto_m else ""

    # comisión e IVA: numéricos vía _safe_float
    comision_m = _RE_COMISION.search(raw_text)
    comision = _safe_float(comision_m.group(1)) if comision_m else 0.0

    iva_m = _RE_IVA.search(raw_text)
    iva = _safe_float(iva_m.group(1)) if iva_m else 0.0

    # folio: regex sobre raw_text, fallback al campo OCR directo
    folio_m = _RE_FOLIO.search(raw_text)
    folio = folio_m.group(1) if folio_m else str(ocr_fields.get("folio") or "")

    # estatus de operación
    estatus_m = _RE_ESTATUS.search(raw_text)
    estatus = estatus_m.group(1).strip() if estatus_m else "exitosa"

    # tipo de operación
    tipo_op_m = _RE_TIPO_OP.search(raw_text)
    tipo_operacion = tipo_op_m.group(1).strip() if tipo_op_m else ""

    # importe_transferido: monto neto sin comisión.
    # Prioridad:
    #   1) campo directo OCR "importe_base" (prompt v2 — modelo lo extrae cuando lo ve claro)
    #   2) regex "Importe transferido / Importe giro" en raw_text (BBVA JUSTIFICANTE, Banorte)
    #   3) regex "MONTO : M.N. $ X" en raw_text (patrón OXXO — línea antes de comisión)
    #   4) fallback al campo monto del OCR
    ocr_importe_base = _safe_float(ocr_fields.get("importe_base")) if ocr_fields.get("importe_base") else None
    imp_trans_m = _RE_IMPORTE_TRANSFERIDO.search(raw_text)
    monto_oxxo_m = _RE_MONTO_BASE_OXXO.search(raw_text)
    if ocr_importe_base:
        importe_transferido = ocr_importe_base
    elif imp_trans_m:
        importe_transferido = _safe_float(imp_trans_m.group(1))
    elif monto_oxxo_m:
        importe_transferido = _safe_float(monto_oxxo_m.group(1))
    else:
        importe_transferido = _safe_float(ocr_fields.get("monto"))

    # importe_total: total cobrado incluyendo comisión.
    # Prioridad:
    #   1) regex "PAGO TOTAL / Cantidad Total / Importe a debitar" en raw_text
    #   2) monto OCR cuando difiere del importe_transferido (OCR captura el total)
    #   3) igual a importe_transferido (sin comisión)
    imp_total_m = _RE_IMPORTE_TOTAL.search(raw_text)
    ocr_monto = _safe_float(ocr_fields.get("monto"))
    if imp_total_m:
        importe_total = _safe_float(imp_total_m.group(1))
    elif ocr_monto and ocr_monto != importe_transferido:
        importe_total = ocr_monto
    else:
        importe_total = importe_transferido

    return {
        "clave_rastreo": clave_rastreo,
        "concepto": concepto,
        "comision": comision,
        "iva": iva,
        "iva_comision": 0.0,          # campo raro — solo vía revisión manual
        "folio": folio,
        "nombre_ordenante": "",       # siempre anonimizado — nunca extraído
        "nombre_beneficiario": "",    # siempre anonimizado — nunca extraído
        "rfc_ordenante": "",          # siempre anonimizado — nunca extraído
        "estatus": estatus,
        "tipo_operacion": tipo_operacion,
        "importe_transferido": importe_transferido,
        "importe_total": importe_total,
        "pais": "MX",                 # default MX — cambiar solo vía revisión manual
    }


def _build_gt_stub(image_id: str, ocr_fields: dict, pdf_text: str = "") -> dict:
    """Construye el JSON de ground-truth v2.0 con valores OCR pre-completados.

    Mapeo de keys OCR → schema v2.0:
      ocr_fields['banco']            → banco_emisor
      ocr_fields['monto']            → monto  (via _safe_float)
      ocr_fields['fecha']            → fecha
      ocr_fields['numero_operacion'] → numero_comprobante  (MercadoPago)
      ocr_fields['referencia']       → descartada (texto libre no estructurado)
    """
    # raw_text: texto PDF completo + valores OCR concatenados.
    # El texto PDF permite que los regex encuentren las etiquetas reales del doc.
    ocr_text = " ".join(str(v) for v in ocr_fields.values() if v is not None)
    raw_text = f"{pdf_text} {ocr_text}".strip() if pdf_text else ocr_text

    extra = _extract_extra_fields(ocr_fields, pdf_text=pdf_text)

    # monto: OCR primero; si es null o 0 intentamos recuperarlo del pdf_text.
    monto_ocr = _safe_float(ocr_fields.get("monto"))
    if monto_ocr == 0.0 and pdf_text:
        m = _RE_MONTO_PDF.search(pdf_text)
        monto_ocr = _safe_float(m.group(1)) if m else 0.0

    # folio desde pdf_text (BBVA cajero, Banco Azteca)
    folio_m = _RE_FOLIO.search(raw_text)
    folio_pdf = folio_m.group(1) if folio_m else ""

    # numero de transacción desde pdf_text (Santander Chile, BanCoppel texto libre)
    num_tx_m = _RE_NUM_TRANSACCION.search(raw_text)
    num_transaccion = num_tx_m.group(1) if num_tx_m else ""

    # numero_comprobante: prioridad descendente —
    #   1) regex #XXXXXXXXX en raw_text (MercadoPago, Banamex, Citibanamex)
    #   2) campo OCR numero_operacion
    #   3) folio del pdf_text (BBVA cajero, Banco Azteca)
    #   4) número de transacción del pdf_text (Santander Chile, BanCoppel)
    #   5) referencia numérica OCR como último recurso
    referencia_ocr = str(ocr_fields.get("referencia") or "")
    numero_comprobante = (
        extra["numero_comprobante"]
        or str(ocr_fields.get("numero_operacion") or "")
        or folio_pdf
        or num_transaccion
        or (referencia_ocr if referencia_ocr.strip().isdigit() else "")
    )

    return {
        "schema_version": "2.0",
        "id": image_id,
        "banco_emisor": ocr_fields.get("banco") or "DESCONOCIDO",
        "banco_receptor": extra["banco_receptor"],
        "monto": monto_ocr,
        "moneda": "MXN",
        "fecha": str(ocr_fields.get("fecha") or ""),
        "hora": extra["hora"],
        "numero_comprobante": numero_comprobante,
        "numero_referencia": extra["numero_referencia"],
        "motivo": extra["motivo"],
        "clabe_emisor_mascara": extra["clabe_emisor_mascara"],
        "clabe_receptor_mascara": extra["clabe_receptor_mascara"],
        "tipo": "spei_recibido",           # TODO: revisar manualmente
        "formato_origen": "screenshot_movil",  # TODO: revisar manualmente
        "calidad": "buena",                # TODO: ajustar según imagen
        "notas": "",
        "synthetic": None,
        "extended": _extract_extended_fields(ocr_fields, raw_text),
    }


def _extract_pdf_text(image_path: Path) -> str:
    """Extrae texto plano de un PDF usando pdftotext (poppler-utils).

    Retorna el texto completo como string, o "" si el archivo no es PDF
    o pdftotext no está disponible. No lanza excepciones — falla silenciosa.
    """
    if image_path.suffix.lower() != ".pdf":
        return ""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(image_path), "-"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _collect_images(input_path: Path) -> list[Path]:
    """Devuelve lista de imágenes a procesar desde ruta (archivo o directorio)."""
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            p for p in input_path.iterdir()
            if p.suffix.lower() in _IMAGE_EXTENSIONS
        )
    return []


def _next_id(prefix: str, output_dir: Path) -> str:
    """Genera el próximo ID secuencial basado en los archivos existentes."""
    existing = list(output_dir.glob(f"{prefix}-*.jpg"))
    if not existing:
        return f"{prefix}-001"
    nums = []
    for p in existing:
        stem = p.stem  # e.g. "mx-001"
        parts = stem.split("-")
        if len(parts) >= 2 and parts[-1].isdigit():
            nums.append(int(parts[-1]))
    next_num = (max(nums) + 1) if nums else 1
    return f"{prefix}-{next_num:03d}"


# ---------------------------------------------------------------------------
# Core async processing
# ---------------------------------------------------------------------------


async def _process_image(
    image_path: Path,
    image_id: str,
    output_dir: Path,
    gt_dir: Path,
    dry_run: bool,
) -> str:
    """Procesa una imagen individual. Retorna 'ok', 'partial' (OCR falló), o 'error'."""
    print(f"  [{image_id}] {image_path.name}", end="")

    # Leer bytes originales (para validar MIME del archivo fuente)
    try:
        file_bytes = image_path.read_bytes()
    except OSError as exc:
        print(f" ERROR: no se pudo leer — {exc}")
        return "error"

    # Validar MIME del archivo original
    try:
        from services.image_service import validate_mime  # type: ignore[import-untyped]
        validate_mime(file_bytes)
    except ValueError as exc:
        print(f" ERROR: MIME inválido — {exc}")
        return "error"

    if dry_run:
        print(f" → {output_dir / image_id}.jpg [dry-run]")
        return "ok"

    # Convertir PDF → PNG si aplica (para OCR y blur)
    try:
        image_bytes = _load_image_bytes(image_path)
    except Exception as exc:  # noqa: BLE001
        print(f" ERROR: conversión de imagen falló — {exc}")
        return "error"

    # Extraer campos OCR (async) — non-fatal: el blur visual no depende del OCR.
    # Si OCR falla, los campos del GT quedan vacíos para revisión manual.
    ocr_fields: dict = {}
    ocr_ok = True
    try:
        client = get_ocr_client()
        try:
            from services.image_service import preprocess, to_base64  # type: ignore[import-untyped]
            from services.ocr_service import extract_fields  # type: ignore[import-untyped]

            # Preprocesar imagen para OCR (usa image_bytes: PDF ya convertido a PNG)
            preprocessed = preprocess(image_bytes)
            b64 = to_base64(preprocessed)
            ocr_fields = await extract_fields(b64, client=client)
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        print(f" WARN: OCR falló ({exc}), campos GT quedarán vacíos", end="")
        ocr_fields = {}
        ocr_ok = False

    # Texto plano del PDF (para regex de comisión, clave rastreo, etc.)
    # Para imágenes JPEG/PNG queda vacío — los campos extended dependen del OCR.
    pdf_text = _extract_pdf_text(image_path)

    # Anonimizar texto OCR (si lo hay)
    if ocr_fields:
        ocr_text = " ".join(
            str(v) for v in ocr_fields.values() if v is not None
        )
        _anonymize_text(ocr_text)  # resultado usado para log; blur es visual

    # Aplicar blur PIL sobre ROI sensible (usa image_bytes: Pillow puede leerlos)
    try:
        anon_bytes = _apply_pil_blur(image_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f" ERROR: PIL blur falló — {exc}")
        return "error"

    # Guardar imagen anonimizada
    out_img = output_dir / f"{image_id}.jpg"
    try:
        out_img.write_bytes(anon_bytes)
    except OSError as exc:
        print(f" ERROR: no se pudo guardar imagen — {exc}")
        return "error"

    # Escribir ground-truth JSON
    gt_data = _build_gt_stub(image_id, ocr_fields, pdf_text=pdf_text)
    if not ocr_ok:
        gt_data["notas"] = "OCR falló — revisión manual requerida"
    out_json = gt_dir / f"{image_id}.json"
    try:
        out_json.write_text(json.dumps(gt_data, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        print(f" ERROR: no se pudo guardar JSON — {exc}")
        return "error"

    status_tag = "partial" if not ocr_ok else "ok"
    print(f" → {out_img.name} + {out_json.name}" + (" [OCR parcial]" if not ocr_ok else ""))
    return status_tag


async def _run(
    images: list[Path],
    output_dir: Path,
    gt_dir: Path,
    id_prefix: str,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Procesa todas las imágenes. Retorna (ok, partial, errors)."""
    ok_count = 0
    partial_count = 0
    error_count = 0
    for img_path in images:
        # Generar ID único basado en los ya existentes + posición actual
        existing_count = len(list(output_dir.glob(f"{id_prefix}-*.jpg")))
        image_id = f"{id_prefix}-{(existing_count + 1):03d}"

        result = await _process_image(img_path, image_id, output_dir, gt_dir, dry_run)
        if result == "ok":
            ok_count += 1
        elif result == "partial":
            partial_count += 1
        else:
            error_count += 1
    return ok_count, partial_count, error_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Anonimiza comprobantes bancarios mexicanos con regex + PIL blur adaptativo.\n"
            "Genera anonymized/{id}.jpg y ground-truth/{id}.json (schema v2.0)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="PATH",
        help="Imagen individual o directorio con imágenes (.jpg/.png/.pdf)",
    )
    parser.add_argument(
        "--output-dir",
        default="dataset/bancario-mx/anonymized/",
        metavar="PATH",
        help="Directorio destino para imágenes anonimizadas (default: %(default)s)",
    )
    parser.add_argument(
        "--gt-dir",
        default="dataset/bancario-mx/ground-truth/",
        metavar="PATH",
        help="Directorio destino para JSONs ground-truth (default: %(default)s)",
    )
    parser.add_argument(
        "--id-prefix",
        default="mx",
        metavar="STR",
        help="Prefijo para IDs generados (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué haría sin escribir archivos",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    gt_dir = Path(args.gt_dir)

    # Recopilar imágenes
    images = _collect_images(input_path)
    if not images:
        print(f"ERROR: no se encontraron imágenes en {input_path!r}", file=sys.stderr)
        return 1

    print(f"Procesando {len(images)} imagen(es) {'[dry-run]' if args.dry_run else ''}...")

    # Crear directorios de salida si no existen
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        gt_dir.mkdir(parents=True, exist_ok=True)

    # Ejecutar pipeline async
    ok, partial, errors = asyncio.run(
        _run(
            images=images,
            output_dir=output_dir,
            gt_dir=gt_dir,
            id_prefix=args.id_prefix,
            dry_run=args.dry_run,
        )
    )

    total = len(images)
    print(f"\nFINALIZADO: {ok} OK, {partial} parcial (OCR falló), {errors} error(es) — {total} total.")
    if partial:
        print("  ⚠ Los parciales tienen GT con campos vacíos — revisión manual requerida.", file=sys.stderr)

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
