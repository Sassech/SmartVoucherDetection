# scripts/ — Herramientas de evaluación (Fase 5.0)

Scripts de investigación standalone para el pipeline de evaluación OCR y detección de duplicados.
Todos importan servicios de `api/` vía `_shared.py` sin modificar el código de producción.

> **Prerequisitos**: `uv` instalado. Todos los comandos se ejecutan desde la **raíz del monorepo**.
> Para los scripts de generación sintética (`generate_synthetic.py`) se requiere Playwright Chromium:
> ```bash
> uv run playwright install chromium
> ```

---

## Tabla de scripts

| Script | Descripción | Args clave | Exit 0 | Exit 1 |
|--------|-------------|------------|--------|--------|
| `scripts/anonymize/anonymize_comprobante.py` | Anonimiza comprobantes originales con regex + PIL y genera ground-truth JSON (schema v1.0) | `--input`, `--output-dir`, `--gt-dir`, `--id-prefix`, `--dry-run` | Todos los archivos procesados correctamente | MIME inválido, imagen corrupta, error de escritura |
| `scripts/_shared.py` | Módulo bootstrap compartido — **no es ejecutable directamente** | N/A | N/A | N/A |
| `scripts/eval/run_pipeline_sroie.py` | Batch async de evaluación OCR sobre dataset SROIE con checkpoint y Semaphore(4) | `--images-dir`, `--annotations-dir`, `--output-csv`, `--concurrency` | Todas las imágenes procesadas | Sin imágenes, llama-server inalcanzable |
| `scripts/eval/metrics_sroie.py` | Calcula precisión/recall/F1 por campo desde CSV de resultados SROIE | `--input-csv`, `--output-json`, `--tolerance-monto`, `--tolerance-fecha` | F1[monto] ≥ 0.80 | F1[monto] < 0.80 (`CRITERION FAILED`) |
| `scripts/augment/generate_synthetic.py` | Genera vouchers sintéticos (Faker + HTML + Playwright) con ground-truth JSON schema v2.0 | `--bank`, `--count`, `--output`, `--seed` | N vouchers generados (imágenes + JSONs) | Error de template, Playwright no instalado |
| `scripts/augment/generate_augmented.py` | Aplica 7 degradaciones visuales (Albumentations) sobre imágenes sintéticas o raw | `--input-dir`, `--gt-dir`, `--output-dir`, `--n`, `--seed` | N imágenes degradadas generadas | Error en transformación o escritura |
| `scripts/augment/generate_duplicates.py` | Genera pares de duplicados exacto/parcial_visual/negativo (distribución 30/40/30 ±5%) | `--images-dir`, `--gt-dir`, `--output-csv`, `--output-degraded-dir`, `--seed` | ≥ 50 pares, distribución válida | < 50 pares o distribución fuera de ±5% |
| `scripts/eval/eval_duplicates_bancario.py` | Evalúa las 3 capas de detección sobre pares bancario-mx SIN base de datos | `--pairs-csv`, `--images-dir`, `--gt-dir`, `--degraded-dir`, `--output-json` | capa_1.precision == 1.0 | capa_1.precision < 1.0 (`CRITERION FAILED`) |

---

## Ejemplos de invocación

### `anonymize_comprobante.py`

```bash
# Vista previa (sin escribir archivos)
uv run python scripts/anonymize/anonymize_comprobante.py \
  --input dataset/bancario-mx/raw/comprobante.jpg \
  --dry-run

# Procesar imagen individual
uv run python scripts/anonymize/anonymize_comprobante.py \
  --input dataset/bancario-mx/raw/comprobante.jpg \
  --output-dir dataset/bancario-mx/anonymized/ \
  --gt-dir dataset/bancario-mx/ground-truth/ \
  --id-prefix mx

# Procesar directorio completo
uv run python scripts/anonymize/anonymize_comprobante.py \
  --input dataset/bancario-mx/raw/ \
  --output-dir dataset/bancario-mx/anonymized/ \
  --gt-dir dataset/bancario-mx/ground-truth/ \
  --id-prefix mx
```

### `run_pipeline_sroie.py` ← Coming in PR-B

```bash
uv run python scripts/eval/run_pipeline_sroie.py \
  --images-dir dataset/sroie/images/ \
  --annotations-dir dataset/sroie/annotations/ \
  --output-csv results/sroie_results.csv \
  --concurrency 4
```

### `metrics_sroie.py` ← Coming in PR-B

```bash
uv run python scripts/eval/metrics_sroie.py \
  --input-csv results/sroie_results.csv \
  --output-json results/sroie_metrics.json \
  --tolerance-monto 0.01 \
  --tolerance-fecha 1
```

### `generate_augmented.py` ← Coming in PR-C

```bash
uv run python scripts/augment/generate_augmented.py \
  --input-dir dataset/bancario-mx/anonymized/ \
  --output-dir dataset/augmented/ \
  --n 500
```

### `generate_duplicates.py` ← Coming in PR-C

```bash
uv run python scripts/augment/generate_duplicates.py \
  --anonymized-dir dataset/bancario-mx/anonymized/ \
  --ground-truth-dir dataset/bancario-mx/ground-truth/ \
  --output-csv dataset/bancario-mx/duplicates/pairs.csv \
  --seed 42
```

### `eval_duplicates_bancario.py` ← Coming in PR-C

```bash
uv run python scripts/eval/eval_duplicates_bancario.py \
  --pairs-csv dataset/bancario-mx/duplicates/pairs.csv \
  --anonymized-dir dataset/bancario-mx/anonymized/ \
  --ground-truth-dir dataset/bancario-mx/ground-truth/ \
  --output-json results/bancario_metrics.json
```

---

## Módulo `_shared.py`

Todos los scripts ejecutables importan este módulo para acceder a `api/` sin duplicar la lógica
de path setup. Si la estructura del monorepo cambia, solo se actualiza `_shared.py`.

```python
from _shared import load_settings, get_ocr_client

settings = load_settings()
client = get_ocr_client()
```

---

## Dependencias

Las dependencias de los scripts se resuelven automáticamente con `uv` desde el entorno de `api/`.
Los scripts usan `sys.path.insert` para importar desde `api/` — no requieren instalación separada.

Librerías externas usadas (ya en `api/pyproject.toml`):
- `httpx` — cliente HTTP async para llama-server
- `Pillow` — transformaciones de imagen
- `python-magic` — detección de MIME

Para métricas (PR-B/PR-C), se añadirán: `pandas`, `scikit-learn`.
