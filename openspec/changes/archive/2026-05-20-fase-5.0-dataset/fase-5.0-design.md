# Design: Fase 5.0 — Dataset Strategy

**Change:** `fase-5.0-dataset`
**Date:** 2026-05-13
**Status:** Ready for Tasks
**Covers:** R-47–R-68 (23 requirements, 12 scenarios)

---

## Technical Approach

Scripts de investigación standalone en `scripts/` en la raíz del monorepo. Importan servicios de `api/` vía `sys.path` insert, sin modificar ningún servicio existente. Dos tracks paralelos (SROIE + bancario-mx) convergiendo en métricas JSON + documentación final.

---

## Architecture Decisions

### D-13: asyncio.Semaphore para SROIE

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `ThreadPoolExecutor` | Simples, pero `ocr_service.extract_fields` es async — requeriría `asyncio.run()` por hilo, overhead innecesario | ✗ |
| `asyncio.gather` sin límite | Satura llama-server (single-process, 1 inference a la vez) → 429 / timeout en cadena | ✗ |
| `asyncio.Semaphore(4)` | Corre en el mismo event loop que el client HTTP, limita en-flight a 4 sin overhead de threads, compatible con `httpx.AsyncClient` existente | ✅ |

**Valor 4**: llama-server puede procesar hasta ~4 requests antes de que el primero devuelva (pipeline GPU). Ajustable vía flag `--concurrency N`. Docs indican que ≥5 genera contención y sube latencia por imagen.

**Checkpoint**: al iniciar, el script lee el CSV existente y construye un `set[str]` de `image_id` procesados. Antes de lanzar cada tarea async, hace `if image_id in processed: continue`. El CSV se escribe en modo `append` (no rewrite) para atomicidad parcial.

### D-14: Anonimización regex + PIL (no OCR-based)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| PaddleOCR para localizar texto sensible | Instala ~2GB, requiere CUDA separado, alto setup para tesis | ✗ Overengineering |
| Regex sobre texto extraído + PIL `ImageDraw.rectangle` (blur visual) | Regex cubre 100% de CLABEs (18 dígitos contiguos) y referencias numéricas. PIL aplica blur en ROIs hardcoded por layout de banco | ✅ |
| Anonimización solo en metadata (sin tocar imagen) | No cumple publicación académica — la imagen original contiene datos legibles | ✗ |

**Regex patterns específicos**:
- CLABE: `\b\d{18}\b` → `****XXXX` (últimos 4)
- Tarjeta: `\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b` → `****XXXX`
- Referencia: `\b[A-Z0-9]{8,20}\b` → `REF-{sha256[:8].upper()}`

**PIL blur**: `ImageDraw.rectangle` sobre 3 zonas ROI hardcoded por layout: top 15% (logo/header), middle 45%–90% (De/Para, nombres, CLABE, email), bottom 90%–100% (número comprobante/ID transacción). Sin EXIF metadata preservation — `image.save()` sin `exif` kwarg descarta EXIF original.

**Revisión manual**: obligatoria para primeros 20 comprobantes antes de procesar lote completo.

### D-15: Ground-truth schema versionado

**Schema fijo** — ningún campo puede ser renombrado sin incrementar versión del schema.

```json
{
  "schema_version": "2.0",
  "id": "mx-001",
  "banco_emisor": "Mercado Pago Wallet",
  "banco_receptor": "",
  "monto": 3000.0,
  "moneda": "MXN",
  "fecha": "18/04/2026",
  "hora": "22:07",
  "numero_comprobante": "154709419317",
  "numero_referencia": "",
  "motivo": "",
  "clabe_emisor_mascara": "",
  "clabe_receptor_mascara": "",
  "tipo": "spei_recibido",
  "formato_origen": "screenshot_movil",
  "calidad": "buena",
  "notas": "",
  "synthetic": null
}
```

> Schema v2.0 — field `banco` split into `banco_emisor`/`banco_receptor`; `referencia` split into `numero_comprobante`/`numero_referencia`; added `moneda`, `hora`, `motivo`, `clabe_emisor_mascara`, `clabe_receptor_mascara`, `synthetic`.

**Campos obligatorios**: `id`, `banco_emisor`, `banco_receptor`, `monto`, `moneda`, `fecha`, `hora`, `numero_comprobante`, `numero_referencia`, `motivo`, `clabe_emisor_mascara`, `clabe_receptor_mascara`, `tipo`, `formato_origen`, `calidad`, `notas`, `synthetic`.
**Campo `notas`**: string libre, vacío `""` si no hay anomalías — siempre presente para que `eval_duplicates_bancario.py` pueda loggear sin KeyError.
**Campo `calidad`**: `"buena" | "media" | "baja"` — permite segmentar métricas por calidad en `bancario_metrics.json` (e.g., "F1=0.72 en calidad=baja vs 0.91 en calidad=buena").
**Campo `synthetic`**: `null` para comprobantes reales; objeto con metadatos para comprobantes sintéticos.
**Enum `tipo`**: `spei_enviado | spei_recibido | transferencia_interna | oxxo_pay | pago_servicio`.
**Enum `formato_origen`**: `screenshot_movil | pdf_banco | foto_whatsapp | scan`.

### D-16: pairs.csv y distribución 30/40/30

**Schema final** (diferencia respecto a explore: columna `notas` añadida):

```
id_a,id_b,tipo_duplicado,capa_esperada,clasificacion_esperada,notas
```

| `tipo_duplicado` | `capa_esperada` | `clasificacion_esperada` | Cómo se genera |
|-----------------|-----------------|--------------------------|----------------|
| `exacto` | `1` | `duplicado` | `shutil.copy` + rename → mismo SHA-256 |
| `parcial_campos` | `2` | `duplicado` | misma ref/monto/fecha, distinto num_operacion → mismo índice de Capa 2 |
| `parcial_visual` | `3` | `duplicado` o `sospechoso` | JPEG q=50 + rotación ±3° → hash diferente, score Capa 3 ≥ 0.75 |
| `negativo` | `N/A` | `valido` | mismo banco+fecha, monto distinto → score < 0.75 |

**Garantía 30/40/30 ±5%** para N comprobantes base:

```python
n_exacto      = round(N * 0.30)   # tipo=exacto
n_parc_campos = round(N * 0.20)   # tipo=parcial_campos  }→ 40% parciales
n_parc_visual = round(N * 0.20)   # tipo=parcial_visual  }
n_negativos   = N - n_exacto - n_parc_campos - n_parc_visual  # ~30%
```

Para N=100: 30 exactos, 20 campos, 20 visuales, 30 negativos = 100 pares. Tolerancia ±5% = ±5 pares — validado en S-46.

**Negativos**: selección aleatoria de pares `(a, b)` donde `banco_a == banco_b` y `fecha_a == fecha_b` pero `monto_a ≠ monto_b`. Esto garantiza que Capa 2 no los detecte (monto diferente) y el score Capa 3 sea bajo.

### D-17: scripts/_shared.py como bootstrap

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Duplicar `sys.path` en cada script | 3 scripts × misma lógica de 5 líneas → drift inevitable si cambia la estructura | ✗ |
| `_shared.py` como módulo compartido | Un único punto de truth para bootstrap. Si el path cambia (e.g., `api/` se mueve), se arregla en un lugar | ✅ |

**Contratos exactos**:

```python
# scripts/_shared.py

def setup_api_path() -> None:
    """Inserta api/ en sys.path[0]. Idempotente (verifica antes de insertar)."""

def load_settings() -> Settings:
    """Llama setup_api_path() + importa Settings + retorna settings instance.
    Acepta DATASET_DIR/RESULTS_DIR opcionales del entorno."""

def get_ocr_client() -> httpx.AsyncClient:
    """Retorna httpx.AsyncClient(base_url=settings.llama_server_url,
    timeout=settings.llama_timeout_s). Caller es responsable de aclose()."""
```

`get_ocr_client()` retorna el cliente sin context manager para compatibilidad con el pattern `asyncio.Semaphore` (el cliente se comparte entre múltiples tareas concurrentes y se cierra al final del batch, no por request).

### D-18: OCR prompt extendido con campo hora (schema v2.0)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Extraer hora con regex desde campo fecha | Frágil — modelos omiten la hora o la incluyen en distintos formatos dentro de fecha | ✗ |
| Campo hora explícito en el prompt OCR | El modelo la extrae directamente como HH:MM, separada de fecha. Fallback regex mantiene compatibilidad con modelos que ignoran el campo nuevo | ✅ |

MercadoPago Wallet muestra fecha y hora en la misma línea ("Sábado, 18 de abril de 2026, 22:07 hs."). Sin un campo explícito el modelo las unía en `fecha` o descartaba la hora.

---

## Data Flow

**Track A — SROIE:**

```
dataset/sroie/images/*.jpg
  → (per image, Semaphore(4)) validate_mime() → preprocess() → to_base64()
  → extract_fields(b64, client=shared_client)
  → parse_monto(raw["monto"]) + parse_fecha(raw["fecha"])
  → append row to sroie_results.csv  [checkpoint: skip if image_id in existing]
  ↓
metrics_sroie.py reads sroie_results.csv
  → precision/recall/F1 per field (exact match + tolerances)
  → results/sroie_metrics.json
  → exit 0 if F1[monto] ≥ 0.80 else exit 1
```

**Track B — bancario-mx:**

```
bancario-mx/raw/*.{jpg,png,pdf}
  → anonymize_comprobante.py (per image)
      → validate_mime() [reuse]
      → regex scan on OCR text (CLABEs, refs)
      → PIL ImageDraw blur on sensitive ROIs
      → save bancario-mx/anonymized/{id}.jpg
      → write bancario-mx/ground-truth/{id}.json [schema v2.0]

bancario-mx/anonymized/ (≥100 images)
  → generate_duplicates.py
      → read all ground-truth JSONs
      → generate exacto/parcial_campos/parcial_visual/negativo pairs
      → write bancario-mx/duplicates/pairs.csv

pairs.csv + anonymized/
  → eval_duplicates_bancario.py
      → per pair: run Capa 1 (hash) + Capa 2 (campos) + Capa 3 (score)
      → compare vs clasificacion_esperada
      → confusion matrix 3×3 + F1 per layer
      → results/bancario_metrics.json
      → exit 0 if capa_1.precision == 1.0 else exit 1
```

---

## Module Interfaces

### `scripts/_shared.py`

```python
def setup_api_path() -> None: ...
def load_settings() -> "Settings": ...
def get_ocr_client() -> httpx.AsyncClient: ...
```

### `scripts/eval/run_pipeline_sroie.py`

```
Args:
  --images-dir PATH    directorio con *.jpg de SROIE  [required]
  --annotations-dir PATH  directorio con *.txt de anotaciones [required]
  --output-csv PATH    CSV de resultados [default: results/sroie_results.csv]
  --concurrency INT    Semaphore limit [default: 4]
  --help

Input:  dataset/sroie/images/*.jpg
        dataset/sroie/annotations/*.txt (key-value: TOTAL, DATE)
Output: sroie_results.csv
        Columns: image_id, gt_total, gt_date, pred_total, pred_date,
                 match_total, match_date, error
        Row status: match_total/match_date = True|False|None (None si pred=None)

Exit: 0 OK | 1 error fatal (no images found, OCR server unreachable)
```

### `scripts/eval/metrics_sroie.py`

```
Args:
  --input-csv PATH    [default: results/sroie_results.csv]
  --output-json PATH  [default: results/sroie_metrics.json]
  --tolerance-monto FLOAT  [default: 0.01]  ← ±0.01 MXN
  --tolerance-fecha INT    [default: 1]     ← ±1 día
  --help

Input:  sroie_results.csv
Output: sroie_metrics.json
  {
    "monto": { "precision": float, "recall": float, "f1": float, "support": int },
    "fecha": { "precision": float, "recall": float, "f1": float, "support": int }
  }

Exit: 0 if F1[monto] >= 0.80 | 1 si CRITERION FAILED (imprime valor obtenido)
```

### `scripts/eval/eval_duplicates_bancario.py`

```
Args:
  --pairs-csv PATH         [default: dataset/bancario-mx/duplicates/pairs.csv]
  --anonymized-dir PATH    [default: dataset/bancario-mx/anonymized/]
  --ground-truth-dir PATH  [default: dataset/bancario-mx/ground-truth/]
  --output-json PATH       [default: results/bancario_metrics.json]
  --help

Input:  pairs.csv + anonymized/*.jpg + ground-truth/*.json
Output: bancario_metrics.json
  {
    "capa_1":  { "precision": float, "recall": float, "f1": float },
    "capa_2":  { "precision": float, "recall": float, "f1": float },
    "scoring": { "precision": float, "recall": float, "f1": float },
    "confusion_matrix": [[int,int,int],[int,int,int],[int,int,int]],
    "by_quality": {
      "buena": { "f1_scoring": float },
      "media": { "f1_scoring": float },
      "baja":  { "f1_scoring": float }
    }
  }

  confusion_matrix axes: predicted=[duplicado,sospechoso,valido] × actual=[duplicado,sospechoso,valido]

Exit: 0 if capa_1.precision == 1.0 | 1 si CRITERION FAILED (imprime valor)
```

**Nota de implementación**: `eval_duplicates_bancario.py` simula las capas SIN base de datos — construye objetos `Comprobante`-like (dataclasses) con los campos del ground-truth JSON y llama directamente a `compute_score()` y `classify()` de `duplicate_service.py`. Capa 1 = `parser_service.compute_hash(img_bytes)`. Capa 2 = comparación directa de `(referencia, monto, fecha)` entre ground-truths. Esto evita levantar PostgreSQL para la evaluación.

### `scripts/augment/generate_duplicates.py`

```
Args:
  --anonymized-dir PATH    [default: dataset/bancario-mx/anonymized/]
  --ground-truth-dir PATH  [default: dataset/bancario-mx/ground-truth/]
  --output-csv PATH        [default: dataset/bancario-mx/duplicates/pairs.csv]
  --output-degraded-dir PATH [default: dataset/bancario-mx/duplicates/degraded/]
  --seed INT               [default: 42]  ← reproducibilidad
  --help

Input:  anonymized/*.jpg + ground-truth/*.json
Output: pairs.csv + degraded/*.jpg (imágenes degradadas para tipo=parcial_visual)

Exit: 0 OK | 1 si < 50 pares generados o distribución fuera de 30/40/30 ±5%
```

### `scripts/augment/generate_augmented.py`

```
Args:
  --input-dir PATH     directorio con imágenes base [required]
  --output-dir PATH    [default: dataset/augmented/]
  --n INT              imágenes a generar [default: 500]
  --help

Input:  imágenes base (Nano Receipts o bancario-mx/anonymized)
Output: dataset/augmented/*.jpg con transformaciones aplicadas

Transformaciones: rotación ±15°, JPEG q=40-70, ruido gaussiano σ=10-25, blur 3×3
Exit: 0 OK | 1 error
```

### `scripts/anonymize/anonymize_comprobante.py`

```
Args:
  --input PATH        imagen o directorio [required]
  --output-dir PATH   [default: dataset/bancario-mx/anonymized/]
  --gt-dir PATH       [default: dataset/bancario-mx/ground-truth/]
  --id-prefix STR     prefijo para IDs generados [default: "mx"]
  --dry-run           muestra qué haría sin escribir archivos
  --help

Input:  imagen(es) .jpg/.png/.pdf originales
Output: anonymized/{id}.jpg + ground-truth/{id}.json (schema v2.0)

Exit: 0 OK | 1 error (imagen corrupta, MIME no válido)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `api/config.py` | Modify | Add `dataset_dir: Path \| None = None`, `results_dir: Path \| None = None` |
| `.gitignore` | Modify | Add `dataset/bancario-mx/raw/`, `dataset/sroie/`, `dataset/augmented/`, `results/` |
| `scripts/_shared.py` | Create | Bootstrap helper: sys.path, settings, OCR client |
| `scripts/eval/run_pipeline_sroie.py` | Create | SROIE batch eval con checkpoint + Semaphore(4) |
| `scripts/eval/metrics_sroie.py` | Create | F1 por campo desde CSV |
| `scripts/eval/eval_duplicates_bancario.py` | Create | Evaluación duplicados sin DB |
| `scripts/augment/generate_duplicates.py` | Create | Generación pares 30/40/30 |
| `scripts/augment/generate_augmented.py` | Create | Augmentation visual |
| `scripts/anonymize/anonymize_comprobante.py` | Create | Regex + PIL anonimización |
| `api/services/ocr_service.py` | Modify | Prompt extendido con campo `hora`; `CAMPOS_ESPERADOS` = 6 campos |
| `dataset/bancario-mx/README.md` | Create | Schema, licencia CC BY 4.0, instrucciones |
| `docs/dataset-evaluation.md` | Create | Resultados reproducibles SROIE + bancario-mx |
| `dataset/bancario-mx/.gitkeep` | Create | Marca el directorio en git (sin contenido raw/) |

---

## Metrics Definitions

### SROIE — precisión flexible

- `match_total`: `True` si `|pred_monto - gt_monto| ≤ 0.01` (Decimal), `False` si ambos presentes y difieren, `None` si `pred_monto is None`
- `match_date`: `True` si `|pred_fecha - gt_fecha| ≤ 1 día`, `False` si difieren, `None` si `pred_fecha is None`
- **precision** = `TP / (TP + FP)` donde `TP = match=True`, `FP = match=False`, `None` excluidos del denominador
- **recall** = `TP / (TP + FN)` donde `FN` = imágenes donde `pred=None` pero `gt` existe
- **F1** = harmonic mean(precision, recall)

### bancario-mx — matriz de confusión 3×3

Clases: `duplicado | sospechoso | valido` (predicho vs esperado según `clasificacion_esperada` en pairs.csv).

- **Capa 1 F1**: solo sobre pares con `capa_esperada=1` — precision = TP_hash / (TP_hash + FP_hash)
- **Capa 2 F1**: solo sobre pares con `capa_esperada=2`
- **Scoring F1**: sobre todos los pares — usa `sklearn.metrics.classification_report` con `average='macro'`
- **by_quality**: agrupa pares por `calidad` del ground-truth de `id_a` → F1 scoring por segmento

---

## Testing Strategy

Los scripts son herramientas de investigación standalone — **no aplica pytest** (no hay lógica de dominio nueva en `api/`). La verificación es mediante los criterios de aceptación ejecutables:

| Verificación | Comando | Criterio |
|-------------|---------|---------|
| R-53 F1 SROIE | `python scripts/eval/metrics_sroie.py` | exit 0 |
| R-66 Capa 1 precision | `python scripts/eval/eval_duplicates_bancario.py` | exit 0 |
| R-57 raw/ en git | `git ls-files dataset/bancario-mx/raw/` | output vacío |
| R-62 distribución pares | `python scripts/augment/generate_duplicates.py` | exit 0 |
| R-49b config.py | `cd api && uv run pytest tests/ -q` (regresión existente) | 0 failures |

La modificación de `api/config.py` (R-49b) usa los tests existentes como guardrail — no se crean tests nuevos para campos opcionales con default=None.

---

## Implementation Order

```
1. api/config.py + .gitignore + estructura directorios  [Track C, día 1]
2. scripts/_shared.py                                   [bloqueador de todo]
3. anonymize_comprobante.py                             [Track B, necesario antes de recolectar]
4. run_pipeline_sroie.py                                [Track A, paralelo a recolección]
5. metrics_sroie.py                                     [depende de 4]
6. generate_duplicates.py                               [depende de recolección ≥100 imágenes]
7. eval_duplicates_bancario.py                          [depende de 6]
8. generate_augmented.py                                [independiente, baja prioridad]
9. docs/dataset-evaluation.md                           [post-resultados]
```

---

## Open Questions

- [ ] **Capa 2 sin DB en eval_duplicates_bancario.py**: `run_capa2` en `duplicate_service.py` requiere `AsyncSession`. El script simula la lógica con comparación directa de campos. Si la lógica de Capa 2 cambia en Fase 6, el script necesita actualizarse manualmente — no hay acoplamiento automático.
- [ ] **Formato ground-truth para `monto` anonimizado**: el campo `monto` en el JSON debe contener el valor **real** (pre-anonimización) para que las métricas OCR sean válidas, pero la imagen tiene el valor sintético. Esto es correcto por diseño pero requiere documentarlo explícitamente en el README para evitar confusión en revisión de tesis.
- [ ] **llama-server debe estar corriendo** para `run_pipeline_sroie.py`. El script debe fallar con mensaje claro (`exit 1 + "ERROR: llama-server unreachable at {url}"`) si el server no responde, no con un traceback de httpx.
