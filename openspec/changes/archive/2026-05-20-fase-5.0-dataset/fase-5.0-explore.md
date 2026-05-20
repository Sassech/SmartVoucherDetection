# Exploration: Fase 5.0 — Dataset Strategy para SmartVoucherDetection

**Change:** `fase-5.0-dataset`
**Date:** 2026-05-13
**Status:** COMPLETE

---

## Executive Summary

- **No hay bloqueadores técnicos** para la estrategia híbrida. El pipeline existente (validate_mime → preprocess → extract_fields → parse_*) ya es directamente reutilizable para SROIE y Nano Receipts sin modificar ningún servicio.
- **SROIE v2 es el dataset más valioso de los tres públicos**: tiene ground-truth estructurado por campo (total, date, company, address) alineado exactamente con los campos que mide parser_service. El pipeline GLM-OCR + parse_monto/parse_fecha puede evaluarse F1 directamente sobre él.
- **Nano Receipts (Donut)** aporta robustez visual a bajo costo: 2400+ imágenes sintéticas con ruido y layouts variados. Ideal para augmentation de duplicados degradados (tarea 5.0.2.5).
- **OCR Receipts Text Detection debe omitirse**: GLM-OCR maneja el layout internamente (multimodal end-to-end), las bounding boxes de regiones son irrelevantes para el pipeline actual. Confirmar en 5.0.1.6 antes de descargar.
- **El mini-dataset bancario MX es el aporte académico crítico**. Sin él, toda la evaluación es sobre dominio comercial (receipts), no bancario mexicano. Los duplicados controlados (30/40/30) son la contribución diferenciadora.
- **La anonimización solo con regex + PIL es suficiente para publicación académica** (CC BY 4.0), siempre que los originales nunca se committeen y el `.gitignore` sea explícito sobre `raw/`.
- **La arquitectura de scripts debe vivir en `scripts/` en el monorepo raíz**, no dentro de `api/`. Son scripts de investigación/evaluación, no lógica de producción — no deben tener dependencias de FastAPI y deben poder correr standalone con un `uv run python scripts/...`.

---

## 1. Current State

### 1.1 Pipeline de producción (estado actual)

```
POST /upload-slip
  │
  ├─ validate_mime(bytes)           → str (image_service.py)
  ├─ pdf_to_image(bytes)            → bytes (si es PDF)
  ├─ preprocess(bytes)              → bytes (gray→deskew→threshold→crop)
  ├─ to_base64(bytes)              → str
  ├─ extract_fields(b64)           → dict[str, Any]  (ocr_service.py → GLM-OCR)
  ├─ parse_monto/fecha/ref/banco   → tipos dominio    (parser_service.py)
  └─ Capa 1 (hash Redis) → Capa 2 (campos exactos Postgres) → Capa 3 (scoring)
```

**Entradas del pipeline**: bytes (JPEG/PNG/PDF), whitelist MIME via libmagic.
**Salidas del OCR**: dict con 5 claves `{monto, fecha, referencia, numero_operacion, banco}` — crudos del LLM.
**Normalización**: `parse_monto` (US/MX style, coma=miles, punto=decimal), `parse_fecha` (dateutil, DD/MM/YYYY), `normalize_banco` (fuzzy Levenshtein ≥0.85 contra catálogo de 7 bancos).

### 1.2 Qué NO existe todavía

- `scripts/` directory (ni en raíz ni en `api/`)
- `dataset/` directory
- `results/` directory
- Ningún script de evaluación ni augmentación
- `DATASET_DIR` / `RESULTS_DIR` en `api/config.py`

---

## 2. Dataset Analysis

### 2.1 SROIE v2 — Viabilidad: ALTA ✅

**Descripción**: ~973 recibos comerciales reales (supermercados, farmacias, restaurantes tailandeses). Cada recibo tiene:
- Imagen escaneada (`images/*.jpg`)
- Anotación de bounding boxes (`entities/*.txt`)
- Extracción key-value estructurada: `COMPANY`, `DATE`, `ADDRESS`, `TOTAL`

**Alineación con el pipeline**:

| Campo SROIE | Equivalente en parser_service | Función de evaluación |
|-------------|-------------------------------|-----------------------|
| `TOTAL`     | `parse_monto()`               | Exact match Decimal o tolerancia ±0.01 |
| `DATE`      | `parse_fecha()`               | Exact match `date` |
| `COMPANY`   | `normalize_banco()` (aprox.)  | No aplica directamente — dominio distinto |
| `ADDRESS`   | Sin equivalente               | Ignorar |

**Lo que aporta**:
- Bench real de `preprocess` + `extract_fields` + `parse_monto/fecha` sobre 973 imágenes variadas
- F1 por campo calculable con ground-truth existente
- Pipeline idéntico: validate_mime → preprocess → extract_fields → parse_*
- Validación de robustez: imágenes escaneadas con ruido, distintas calidades

**Limitaciones**:
- Dominio comercial, no bancario. Los campos `referencia` y `banco` no se pueden evaluar.
- Formato de fechas puede diferir (DD/MM/YYYY vs mon-DD-YYYY según el país de emisión)
- `parse_monto` tiene heurística US/MX (coma=miles, punto=decimal). SROIE tiene recibos asiáticos con formato diferente — habrá falsos negativos inevitables. **Esperado y documentable.**
- La descarga requiere Kaggle account + `kaggle datasets download`

**Métricas a medir**:
- `precision`, `recall`, `F1` para campo `total` (monto)
- `precision`, `recall`, `F1` para campo `date` (fecha)
- `F1 macro` como métrica agregada
- Tasa de parse exitoso (% de imágenes donde OCR devuelve campo no-None)

**Esfuerzo de integración**: BAJO. Script `run_pipeline_sroie.py` reutiliza los servicios directamente via import. No requiere modificar nada en `api/`.

**Umbral de aceptación (5.0.4.1)**: F1 ≥ 0.80 en `total`. Alcanzable dado que GLM-OCR + parse_monto ya funciona bien en smoke tests internos.

---

### 2.2 Nano Receipts (HuggingFace `katanaml-org/invoices-donut-data-v1`) — Viabilidad: MEDIA ✅

**Descripción**: 2400+ imágenes de receipts/facturas sintéticas generadas con Donut. Layouts variados, ruido visual controlado, varios idiomas. Datos completamente sintéticos, sin problemas de privacidad ni licencia (libre de modificar).

**Alineación con el pipeline**:
- Las imágenes pasan por el pipeline completo (preprocess → GLM-OCR) sin cambios.
- El valor principal NO es la evaluación F1 (los campos están en formato Donut que requiere parseo adicional), sino como **fuente de imágenes variadas para augmentation**.

**Lo que aporta**:
- Base de imágenes para `generate_augmented.py` (5.0.1.5): rotación ±15°, JPEG q=40-70, ruido, blur
- Testing de robustez del pipeline de preprocess (deskew, threshold) bajo condiciones degradadas
- Sin costo legal — directamente usable en tesis académica

**Limitaciones**:
- Ground-truth en formato Donut (JSON de parsing Donut) — no mapeado directamente a los campos del OCR prompt. Extraer F1 requiere un parser adicional.
- Sintético: no representa distribución real de comprobantes MX.
- `load_dataset` de HuggingFace descarga ~2GB.

**Uso recomendado**: Solo para augmentation (tarea 5.0.1.5), no para métricas F1. Las métricas de robustez se miden como: "% de imágenes augmentadas donde el pipeline no crashea + campo monto parseado exitosamente".

**Esfuerzo de integración**: BAJO para augmentation. MEDIO si se quiere extraer F1 (requiere parser Donut adicional — no recomendado para Fase 5.0).

---

### 2.3 OCR Receipts Text Detection — Viabilidad: BAJA ⚠️

**Descripción**: Dataset con bounding boxes de regiones (store, date_time, total, items) + XML annotations.

**Análisis de viabilidad**:
- GLM-OCR es un modelo multimodal end-to-end: recibe la imagen completa y extrae campos directamente via prompt.
- **No hay un paso de detección de regiones en el pipeline actual**. `image_service.preprocess` hace deskew + threshold pero no segmenta regiones.
- Las bounding boxes de este dataset solo son útiles si se añade una capa OpenCV de segmentación ANTES del OCR (recortar región de "total" antes de mandar a GLM-OCR).
- Añadir esa capa no está en el scope de Fase 5.0 y podría degradar performance en imágenes donde GLM-OCR ya lo hace bien.

**Recomendación**: **Omitir en Fase 5.0**. Evaluar solo si en Fase 6 se detecta que GLM-OCR falla sistemáticamente en imágenes con layouts complejos y se decide agregar pre-segmentación.

---

### 2.4 Mini-dataset bancario MX — Viabilidad: ALTA ✅ (con riesgos)

**Descripción**: 100-300 comprobantes reales anonimizados de bancos mexicanos (BBVA, Santander, Banorte, SPEI, OXXO Pay). Formatos: screenshot móvil, PDF banco, foto WhatsApp, scan.

**Por qué es el aporte crítico**:
- SROIE y Nano Receipts no tienen `referencia SPEI`, `CLABE`, `tipo_operacion`, ni el layout visual específico de la banca mexicana.
- Los umbrales del scoring (W_REF=0.35, THRESHOLD_DUPLICADO=0.90) solo se pueden validar/ajustar con comprobantes reales del dominio.
- Es un benchmark reproducible que no existe en literatura pública — contribución original de la tesis.

**Métricas a medir**:
- Capa 1 (hash exacto): precision 100% (criterio de aceptación 5.0.4.4)
- Capa 2 (campos exactos): precision/recall sobre pares `tipo_duplicado=exacto_campos`
- Capa 3 (scoring): F1 por clase (`duplicado/sospechoso/valido`) sobre todos los pares
- Matriz de confusión 3×3 (predicho vs esperado)
- Distribución de scores para análisis de umbrales

**Métricas del OCR (sub-evaluación)**:
- F1 por campo: `monto`, `fecha`, `referencia`, `banco` (4 campos con ground-truth)
- Tasa de extracción exitosa por `formato_origen` (screenshot vs PDF vs WhatsApp foto)
- Tasa de extracción por `calidad` (buena / media / baja)

---

## 3. Arquitectura de Scripts

### 3.1 Estructura propuesta

```
scripts/                          # raíz del monorepo (NO dentro de api/)
├── eval/
│   ├── run_pipeline_sroie.py     # procesa SROIE imagen a imagen → CSV
│   ├── metrics_sroie.py          # calcula precision/recall/F1 desde CSV
│   ├── eval_duplicates_bancario.py  # corre los pares → matriz de confusión
│   └── README.md                 # uso de los scripts de evaluación
├── augment/
│   ├── generate_augmented.py     # aplica transformaciones a Nano Receipts
│   ├── generate_duplicates.py    # genera pares controlados desde bancario-mx
│   └── README.md
└── anonymize/
    ├── anonymize_comprobante.py  # anonimiza imagen + genera ground-truth JSON
    └── README.md

dataset/                          # raíz del monorepo
├── sroie/
│   ├── images/                   # *.jpg originales de SROIE
│   └── annotations/              # *.txt key-value por imagen
├── bancario-mx/
│   ├── raw/                      # ← en .gitignore, NUNCA committear
│   ├── anonymized/               # versión publicable
│   ├── ground-truth/             # {id}.json por imagen
│   ├── duplicates/
│   │   └── pairs.csv             # id_a, id_b, tipo_duplicado, esperado
│   └── README.md
└── augmented/                    # output de generate_augmented.py

results/
├── sroie_results.csv
├── sroie_metrics.json
└── bancario_metrics.json
```

### 3.2 Dependencias de los scripts

Los scripts de `scripts/` **no deben importar FastAPI ni Alembic**. Solo usan:
- `api/services/image_service.py` (preprocess, validate_mime)
- `api/services/parser_service.py` (parse_monto, parse_fecha, etc.)
- `api/services/ocr_service.py` (extract_fields — requiere llama-server corriendo)
- `api/config.py` (para LLAMA_SERVER_URL)
- Bibliotecas standalone: `csv`, `json`, `pathlib`, `PIL`, `cv2`, `sklearn`

Para importar los módulos de `api/` desde `scripts/`, los scripts deben correr con `sys.path.insert(0, "api/")` o usando `uv run --directory api python ../scripts/eval/run_pipeline_sroie.py`.

**Mejor opción**: Agregar `scripts/` como módulo standalone con su propio `pyproject.toml` mínimo que declare `api/` como dependencia local via `uv workspace`. Pero para Fase 5.0, con `sys.path` es suficiente — mantener simple.

### 3.3 Integración con config.py (tarea 5.0.3.1)

```python
# api/config.py — agregar:
DATASET_DIR: Path = Path("../dataset")    # relativo al repo root
RESULTS_DIR: Path = Path("../results")

# ambos opcionales (default None es suficiente para producción)
```

---

## 4. Estructura del Mini-dataset

### 4.1 Organización de directorios

```
dataset/bancario-mx/
├── raw/                    # ← .gitignore explícito
├── anonymized/
│   ├── bbva/               # opcional: sub-carpeta por banco para análisis
│   ├── santander/
│   ├── banorte/
│   ├── spei/
│   └── oxxo-pay/
├── ground-truth/
│   ├── mx-001.json
│   ├── mx-002.json
│   └── ...
├── duplicates/
│   ├── pairs.csv           # id_a, id_b, tipo_duplicado, esperado
│   └── degraded/           # imágenes degradadas generadas por generate_duplicates.py
└── README.md
```

### 4.2 Schema del ground-truth JSON

```json
{
  "id": "mx-001",
  "banco": "BBVA",
  "monto": 1500.00,
  "fecha": "2026-03-15",
  "referencia": "REF-A1B2C3D4",
  "tipo": "spei_enviado",
  "formato_origen": "screenshot_movil",
  "calidad": "buena",
  "notas": "texto inclinado ~3°"
}
```

**Valores de `tipo`**: `spei_enviado`, `spei_recibido`, `transferencia_interna`, `oxxo_pay`, `pago_servicio`
**Valores de `formato_origen`**: `screenshot_movil`, `pdf_banco`, `foto_whatsapp`, `scan`
**Valores de `calidad`**: `buena`, `media`, `baja`

### 4.3 Schema de pairs.csv

```csv
id_a,id_b,tipo_duplicado,esperado,notas
mx-001,mx-001-copy,exacto_hash,duplicado,"mismo archivo distinto nombre"
mx-001,mx-001-partial,exacto_campos,duplicado,"misma referencia+monto+fecha"
mx-001,mx-001-degraded,visual_degradado,duplicado,"JPEG q=50 + rotación 3°"
mx-001,mx-002,negativo,valido,"mismo banco, distinto monto"
```

**Valores de `tipo_duplicado`**: `exacto_hash`, `exacto_campos`, `visual_degradado`, `negativo`
**Distribución objetivo**: 30% exacto_hash, 40% exacto_campos+visual_degradado, 30% negativo

---

## 5. Pipeline de Anonimización

### 5.1 Técnica recomendada: regex textual + PIL text-replace

Para la versión académica publicable, es suficiente con:

1. **Paso regex sobre texto extraído** (pre-anonimización, sobre ground-truth):
   - Nombres: regex `[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Z ]{3,}` → "JUAN PÉREZ"
   - CLABEs: regex `\b\d{18}\b` → `****1234` (últimos 4)
   - Tarjetas: regex `\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b` → `****1234`
   - Referencias: hash → `REF-{sha256[:8].upper()}`
   - Montos: reemplazar por valor sintético plausible (mismo orden de magnitud)

2. **PIL text overlay sobre imagen** (anonimización visual):
   - Localizar texto en la imagen via bounding boxes del OCR (si se usa SROIE-style) o via coordenadas aproximadas
   - Pintar rectángulo del color del fondo + escribir valor anonimizado
   - **Limitación**: sin bounding boxes previos, el overlay requiere re-correr OCR para localizar texto — costoso pero necesario para imágenes fotográficas

3. **Alternativa más simple** (si el pipeline de localización es demasiado costoso):
   - Blur gaussiano fuerte sobre regiones de nombre/CLABE/referencia en posiciones conocidas por layout (para bancos con layout fijo como BBVA/Santander)
   - Suficiente para privacidad, menos reproducible

**Recomendación**: Implementar primero blur por regiones para los primeros 5 comprobantes de prueba (criterio 5.0.2.3), iterar si la revisión manual muestra datos filtrados.

### 5.2 Suficiencia legal para publicación académica

Para CC BY 4.0 en un dataset académico MX, la anonimización es suficiente si:
- ✅ Nombres → pseudónimos genéricos
- ✅ CLABEs → truncadas (últimos 4 dígitos)
- ✅ Montos → valores sintéticos en mismo orden de magnitud
- ✅ Referencias → hasheadas
- ✅ `raw/` nunca en git
- ⚠️ Verificar con responsable de tesis sobre requisitos institucionales específicos (UNAM/TEC/etc. tienen protocolos distintos)

---

## 6. Generación de Duplicados Controlados

### 6.1 Estrategia por tipo

| Tipo | Capa objetivo | Transformación | Generador |
|------|--------------|----------------|-----------|
| `exacto_hash` | Capa 1 | Copiar archivo, distinto nombre | `shutil.copy` + rename |
| `exacto_campos` | Capa 2 | Mismo banco/monto/fecha/ref, diferente referencia_operacion | Regenerar imagen con Pillow cambiando número_operacion |
| `visual_degradado` | Capa 3 | JPEG q=40-70 + rotación ±5° + ruido gaussiano | PIL + cv2 |
| `negativo` | Todas (debe ser válido) | Mismo banco, distinto monto/fecha | Imagen diferente del mismo banco |

### 6.2 Garantía de distribución (30/40/30)

```python
# En generate_duplicates.py:
n_exacto_hash = int(n_comprobantes * 0.30)     # 1 copia exacta por comp
n_exacto_campos = int(n_comprobantes * 0.20)    # 1 variante campos por comp
n_visual = int(n_comprobantes * 0.20)           # 1 degradado por comp
n_negativos = int(n_comprobantes * 0.30)        # selección aleatoria de pares distintos

# Total pares = n_comprobantes * 1.0 (1 par por comprobante + negativos seleccionados)
```

Para 100 comprobantes: ~30 exactos_hash, ~20 exactos_campos, ~20 visuales, ~30 negativos = 100 pares totales (supera el mínimo de 50 de 5.0.4.3).

---

## 7. Affected Areas

| Archivo/Directorio | Tipo de afectación | Notas |
|---|---|---|
| `scripts/eval/run_pipeline_sroie.py` | **NEW** | Script principal SROIE |
| `scripts/eval/metrics_sroie.py` | **NEW** | Cálculo F1 SROIE |
| `scripts/eval/eval_duplicates_bancario.py` | **NEW** | Evaluación duplicados bancario-mx |
| `scripts/augment/generate_augmented.py` | **NEW** | Augmentation Nano Receipts |
| `scripts/augment/generate_duplicates.py` | **NEW** | Generación pares controlados |
| `scripts/anonymize/anonymize_comprobante.py` | **NEW** | Anonimización imagen + GT JSON |
| `dataset/bancario-mx/` | **NEW** | Estructura de directorios + README |
| `dataset/sroie/` | **NEW** | Dataset descargado (no tracked en git) |
| `api/config.py` | **MODIFY** | Agregar `DATASET_DIR`, `RESULTS_DIR` |
| `docs/dataset-evaluation.md` | **NEW** | Resultados documentados |
| `.gitignore` | **MODIFY** | Agregar `dataset/bancario-mx/raw/`, `dataset/sroie/`, `results/` |

**Servicios sin modificar**: `image_service.py`, `ocr_service.py`, `parser_service.py`, `duplicate_service.py` — los scripts los usan como librerías, no los tocan.

---

## 8. Risks

### RIESGO 1 — Recolección del mini-dataset bancario (CRÍTICO)
**Descripción**: Conseguir 100 comprobantes reales anonimizados requiere tiempo y acceso a documentos bancarios reales.
**Probabilidad**: Alta — es el único paso que depende de recursos externos.
**Mitigación**:
- Empezar con los propios comprobantes del investigador (método más rápido, sin fricción legal).
- Complementar con comprobantes de colegas/familia que consientan la recolección anónima.
- Si no se llegan a 100 antes de la deadline: el criterio 5.0.4.2 puede ajustarse a ≥50 para mantener el timeline.

### RIESGO 2 — SROIE F1 < 0.80 en monto (MEDIO)
**Descripción**: `parse_monto` tiene heurística US/MX (coma=miles, punto=decimal). SROIE tiene recibos de múltiples países con formatos diferentes (europeo: punto=miles, coma=decimal).
**Probabilidad**: Media — los recibos tailandeses y malayos de SROIE usan `.` como separador decimal, lo que es compatible. Pero hay variabilidad.
**Mitigación**:
- Documentar la limitación de la heurística en `docs/dataset-evaluation.md` como "Known limitation: heurística US/MX puede fallar en recibos con formato europeo (punto=miles)".
- Si F1 < 0.80: agregar filtro para recibos en inglés/tailandés solo, que son los de mayor volumen en SROIE.
- El umbral 0.80 es el publicable mínimo, no el objetivo — un F1 de 0.75 con análisis de error documentado es igualmente válido académicamente.

### RIESGO 3 — GLM-OCR lento en batch de 973 imágenes (MEDIO)
**Descripción**: GLM-OCR tardó 3.73s en el smoke test de 1 imagen. 973 imágenes = ~60 minutos de procesamiento secuencial.
**Probabilidad**: Alta — el batch va a tardar.
**Mitigación**:
- `run_pipeline_sroie.py` debe ser reanudable: guardar resultados parciales en CSV e implementar checkpoint (skip de imágenes ya procesadas).
- Correr con concurrencia limitada: `asyncio.Semaphore(4)` para 4 requests paralelos sin saturar llama-server.
- Estimado real: con semaphore(4) → ~15 minutos para 973 imágenes. Documentar en README.

### RIESGO 4 — Anonimización incompleta (MEDIO)
**Descripción**: La anonimización visual por blur/overlay puede dejar datos legibles en comprobantes de alta resolución o con layouts inusuales.
**Probabilidad**: Baja-Media — los layouts bancarios MX son relativamente uniformes.
**Mitigación**:
- Revisión manual de los primeros 20 comprobantes anonimizados antes de procesar el lote completo.
- Checklist: nombre, CLABE, monto, referencia, correo/teléfono del destinatario.
- No publicar el dataset en git hasta que la revisión manual esté completa.

### RIESGO 5 — Pesos de scoring no optimales (BAJO para Fase 5.0)
**Descripción**: Los umbrales actuales (THRESHOLD_DUPLICADO=0.90, W_REF=0.35) se decidieron sin dataset real. El mini-dataset puede revelar que son subóptimos.
**Probabilidad**: Media — es esperable que necesiten ajuste.
**Mitigación**: Este riesgo es **intencional** para Fase 5.0. La tarea 6.2 del PROGRESO ya contempla grid search. En Fase 5.0 solo medir — el ajuste se hace en Fase 6 con los resultados.

---

## 9. Approaches Comparados

### Approach A — Scripts standalone en `scripts/` (RECOMENDADO)

- **Pros**: Separación clara producción/investigación. Sin dependencias de FastAPI. Reproducibles por cualquier investigador con `uv run python scripts/...`. No poluciona `api/` con código de bench.
- **Cons**: Requiere `sys.path` trick para importar servicios de `api/`. Un poco de boilerplate extra.
- **Complejidad**: Baja

### Approach B — Scripts dentro de `api/` como módulo `api/eval/`

- **Pros**: Imports directos sin sys.path. Misma venv.
- **Cons**: Mezcla código de investigación con código de producción. Un `import api.eval` en producción sería un error conceptual grave. El directorio `api/` debe quedar limpio.
- **Complejidad**: Baja pero **conceptualmente incorrecta**

### Approach C — Repo separado para el dataset

- **Pros**: Máxima separación. Gitea/GitHub repo público para el dataset.
- **Cons**: Overhead de sincronización. Los scripts de eval necesitan acceso a la misma versión del pipeline. Demasiado para una tesis.
- **Complejidad**: Alta

---

## 10. Recommendation

**Approach A (scripts en raíz del monorepo)** es la arquitectura correcta:

1. Los scripts de evaluación son **herramientas de investigación**, no código de producción. No deben mezclarse con `api/`.
2. Cada subdirectorio de `scripts/` tiene su propio `README.md` con instrucciones de uso.
3. El `sys.path` trick se documenta en el README de cada script — no es un gotcha, es una convención explícita.
4. `dataset/bancario-mx/raw/` en `.gitignore` desde el primer commit — es la única protección robusta.

**Orden de implementación recomendado para la propuesta**:
1. Crear estructura de directorios + `.gitignore` (5.0.2.1)
2. Implementar `anonymize_comprobante.py` — necesario antes de recolectar (5.0.2.3)
3. Definir schema ground-truth (5.0.2.4) — bloqueador de todo lo demás
4. Descargar SROIE + implementar `run_pipeline_sroie.py` (5.0.1.1 + 5.0.1.2)
5. Calcular métricas SROIE (5.0.1.3) — feedback temprano sobre calidad del OCR
6. Recolectar comprobantes bancarios MX (5.0.2.2) — proceso paralelo al paso 4-5
7. Generar duplicados controlados (5.0.2.5)
8. Evaluar duplicados (5.0.2.6)
9. Documentar resultados (5.0.3.3, 5.0.2.7)

---

## Ready for Proposal

**Sí** — la exploración está completa. Los riesgos son conocidos y tienen mitigaciones concretas. El siguiente paso es la propuesta formal (sdd-propose) con:
- Scope preciso de las tareas del PROGRESO
- Criterios de aceptación ajustados (especialmente si el conteo de comprobantes MX es ≥50 en lugar de ≥100 para el primer milestone)
- Decisión explícita sobre si OCR Receipts Text Detection se omite permanentemente (recomendado: sí)
