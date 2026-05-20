# Dataset: bancario-mx

Mini dataset de comprobantes bancarios mexicanos anonimizados para evaluación de tesis.

Contiene imágenes procesadas con `scripts/anonymize/anonymize_comprobante.py` y sus correspondientes
archivos de ground-truth en JSON (schema v2.0). Los comprobantes cubren múltiples bancos
y distintos tipos de operación SPEI.

> **IMPORTANTE**: El directorio `raw/` está excluido de git (`.gitignore`).  
> Los comprobantes originales con datos reales NUNCA deben subirse al repositorio.

---

## Estructura

```
dataset/bancario-mx/
├── raw/               # ← NO en git. Originales con datos reales (local only)
├── anonymized/        # Imágenes anonimizadas (se commitean)
├── ground-truth/      # JSONs de etiquetas manuales (schema v2.0)
├── duplicates/        # pairs.csv + degraded/ generados por generate_duplicates.py
└── README.md
```

---

## Ground-Truth Schema v2.0

Cada imagen en `anonymized/{id}.jpg` tiene su correspondiente `ground-truth/{id}.json`.
El schema es fijo — ningún campo puede ser renombrado sin incrementar `schema_version`.

### Campos principales

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `schema_version` | `string` | Siempre `"2.0"` | `"2.0"` |
| `id` | `string` | ID único del comprobante | `"mx-001"` |
| `banco_emisor` | `string` | Nombre del banco que emite el comprobante | `"BBVA"`, `"Santander"` |
| `banco_receptor` | `string` | Banco destino (puede ser vacío para transferencias internas) | `"Banorte"` |
| `monto` | `float` | Importe en la moneda del campo `moneda` | `1500.00` |
| `moneda` | `string` | Código ISO 4217; casi siempre `"MXN"` | `"MXN"` |
| `fecha` | `string` | Fecha de la operación | `"2026-03-15"` |
| `hora` | `string` | Hora de la operación `HH:MM` | `"22:07"` |
| `numero_comprobante` | `string` | Número de comprobante o folio del recibo | `"123456789"` |
| `numero_referencia` | `string` | Referencia SPEI u operación bancaria | `"987654"` |
| `motivo` | `string` | Motivo o descripción libre indicado por el ordenante | `"Pago renta"` |
| `clabe_emisor_mascara` | `string` | CLABE del emisor enmascarada | `"****8919"` |
| `clabe_receptor_mascara` | `string` | CLABE del receptor enmascarada | `"****5381"` |
| `tipo` | `enum` | Tipo de operación (ver abajo) | `"spei_enviado"` |
| `formato_origen` | `enum` | Formato del comprobante original (ver abajo) | `"screenshot_movil"` |
| `calidad` | `enum` | Calidad visual de la imagen | `"buena"` |
| `notas` | `string` | Texto libre; `""` si no hay anomalías | `""` |
| `synthetic` | `object\|null` | `null` en comprobantes reales; objeto de metadata en sintéticos | `null` |

### Bloque `extended`

El bloque `extended` siempre está presente en comprobantes reales (incluso si todos sus valores
son vacíos o por defecto). Solo es `null` en comprobantes sintéticos.

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `clave_rastreo` | `string` | Clave de rastreo SPEI (15–40 chars alfanumérico) | `"2026041800123456789012"` |
| `concepto` | `string` | Concepto o descripción del pago | `"Pago de factura"` |
| `comision` | `float` | Comisión cobrada por la operación | `5.80` |
| `iva` | `float` | IVA de la comisión | `0.93` |
| `iva_comision` | `float` | IVA adicional sobre comisión (raro; default `0.0`) | `0.0` |
| `folio` | `string` | Folio de la operación (4–20 chars alfanumérico) | `"ABC123"` |
| `nombre_ordenante` | `string` | Siempre `""` — dato personal, nunca se extrae | `""` |
| `nombre_beneficiario` | `string` | Siempre `""` — dato personal, nunca se extrae | `""` |
| `rfc_ordenante` | `string` | Siempre `""` — dato personal, nunca se extrae | `""` |
| `estatus` | `string` | Estatus de la operación; default `"exitosa"` | `"exitosa"` |
| `tipo_operacion` | `string` | Descripción textual del tipo de operación | `"SPEI Enviado"` |
| `pais` | `string` | País del comprobante; default `"MX"` | `"MX"` |

> **Nota sobre `extended.pais`**: los comprobantes con `pais != "MX"` se excluyen de las
> métricas de evaluación. Se mantienen en `raw/misc/` únicamente como referencia de layout.
> El campo solo se cambia de `"MX"` mediante revisión manual explícita.

### Enum `tipo`

| Valor | Descripción |
|-------|-------------|
| `spei_enviado` | Transferencia SPEI saliente |
| `spei_recibido` | Transferencia SPEI entrante |
| `transferencia_interna` | Transferencia entre cuentas del mismo banco |
| `oxxo_pay` | Depósito vía OXXO Pay |
| `pago_servicio` | Pago de servicio (CFE, Telmex, etc.) |
| `deposito_efectivo` | Depósito en efectivo en ventanilla o corresponsal |
| `traspaso_propio` | Traspaso entre cuentas propias del mismo titular |

### Enum `formato_origen`

| Valor | Descripción |
|-------|-------------|
| `screenshot_movil` | Captura de pantalla desde app bancaria móvil |
| `pdf_banco` | PDF oficial descargado desde banca en línea |
| `foto_whatsapp` | Foto tomada con cámara o recibida por WhatsApp (posible compresión) |
| `scan` | Escaneo físico del comprobante impreso |

### Enum `calidad`

| Valor | Descripción |
|-------|-------------|
| `buena` | Texto perfectamente legible, sin distorsión notable |
| `media` | Algo de ruido, compresión o ángulo; OCR puede tener errores menores |
| `baja` | Muy borrosa, muy comprimida o con fuerte perspectiva; OCR frecuentemente falla |

### Ejemplo completo

```json
{
  "schema_version": "2.0",
  "id": "mx-001",
  "banco_emisor": "BBVA",
  "banco_receptor": "Santander",
  "monto": 1500.00,
  "moneda": "MXN",
  "fecha": "2026-03-15",
  "hora": "14:32",
  "numero_comprobante": "123456789",
  "numero_referencia": "987654",
  "motivo": "Pago renta",
  "clabe_emisor_mascara": "****8919",
  "clabe_receptor_mascara": "****5381",
  "tipo": "spei_enviado",
  "formato_origen": "screenshot_movil",
  "calidad": "buena",
  "notas": "",
  "synthetic": null,
  "extended": {
    "clave_rastreo": "2026031500123456789012",
    "concepto": "Pago renta marzo",
    "comision": 0.0,
    "iva": 0.0,
    "iva_comision": 0.0,
    "folio": "",
    "nombre_ordenante": "",
    "nombre_beneficiario": "",
    "rfc_ordenante": "",
    "estatus": "exitosa",
    "tipo_operacion": "SPEI Enviado",
    "pais": "MX"
  }
}
```

> **Nota sobre `monto`**: el campo contiene el valor **real** del comprobante original
> (pre-anonimización). La imagen anonimizada puede tener el monto pixelado/borrado,
> pero el JSON siempre contiene el valor verdadero para que las métricas OCR sean válidas.

---

## Bancos incluidos

El dataset cubre comprobantes de los siguientes bancos:

- **BBVA** (Bancomer)
- **Santander**
- **Banorte**
- **Banamex** (Citibanamex)
- **BanCoppel**
- **Banco Azteca**
- **Mercado Pago Wallet**
- **OXXO Pay**

---

## Soporte para PDF

El script de anonimización soporta archivos `.pdf` de forma nativa. Cuando se detecta
un PDF, se convierte automáticamente a imagen PNG (primera página, 300 dpi) mediante
`pdf_to_image()` de `api/services/image_service.py` antes de aplicar el preprocesado
OCR y el blur PIL. La validación MIME se realiza siempre sobre el archivo original.

---

## Instrucciones de contribución

### Requisitos previos

- Python 3.12+ con `uv` instalado
- `Pillow`, `httpx`, `python-magic` disponibles (ver `api/pyproject.toml`)
- llama-server corriendo localmente (para extracción OCR)

### Agregar nuevos comprobantes

1. Coloca el comprobante original (`.jpg`, `.png` o `.pdf`) en `dataset/bancario-mx/raw/`.
   **Este directorio está en `.gitignore` — los originales nunca se commitean.**

2. Ejecuta el script de anonimización:

   ```bash
   # Vista previa (sin escribir archivos)
   uv run python scripts/anonymize/anonymize_comprobante.py \
     --input dataset/bancario-mx/raw/mi_comprobante.jpg \
     --dry-run

   # Procesar y guardar
   uv run python scripts/anonymize/anonymize_comprobante.py \
     --input dataset/bancario-mx/raw/mi_comprobante.jpg \
     --output-dir dataset/bancario-mx/anonymized/ \
     --gt-dir dataset/bancario-mx/ground-truth/ \
     --id-prefix mx
   ```

3. El script genera:
   - `dataset/bancario-mx/anonymized/{id}.jpg` — imagen con CLABE/tarjeta borrada
   - `dataset/bancario-mx/ground-truth/{id}.json` — JSON con campos pre-completados por OCR

4. **Revisión manual obligatoria** (especialmente para los primeros 20 comprobantes):
   - Abre el JSON generado y verifica/corrige los campos extraídos por OCR
   - Completa el campo `tipo` según el tipo real de operación
   - Ajusta el campo `calidad` según la imagen anonimizada resultante
   - Completa los campos del bloque `extended` que no pudo extraer el OCR
   - Añade `notas` si hay anomalías relevantes

5. Commitea **solo** los archivos en `anonymized/` y `ground-truth/`:

   ```bash
   git add dataset/bancario-mx/anonymized/{id}.jpg
   git add dataset/bancario-mx/ground-truth/{id}.json
   git commit -m "dataset: add comprobante {id}"
   ```

### Procesamiento en lote

```bash
uv run python scripts/anonymize/anonymize_comprobante.py \
  --input dataset/bancario-mx/raw/ \
  --output-dir dataset/bancario-mx/anonymized/ \
  --gt-dir dataset/bancario-mx/ground-truth/ \
  --id-prefix mx
```

---

## Licencia

Los datos anonimizados en este dataset se publican bajo **CC BY 4.0**
(Creative Commons Attribution 4.0 International).

> You are free to share and adapt the material for any purpose, even commercially,
> as long as you give appropriate credit.
> See: <https://creativecommons.org/licenses/by/4.0/>

Los datos originales en `raw/` (nunca en git) son propiedad de sus titulares y
**no** se redistribuyen.
