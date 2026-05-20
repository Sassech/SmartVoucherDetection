# Tasks: Fase 5.0 — Dataset Strategy

**Change:** `fase-5.0-dataset`
**Date:** 2026-05-13
**Status:** Apply complete — all 14 tasks done. Ready for verify.
**Covers:** R-47–R-68 (23 requirements, 12 scenarios)

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated new files | ~16 |
| Estimated changed lines | ~650–850 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | PR-A (infra + bootstrap + anon) → PR-B (eval pipeline) → PR-C (augment + metrics + docs) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Estimated lines | Notes |
|------|------|-----------|----------------|-------|
| PR-A | Infra base + `_shared.py` + `anonymize_comprobante.py` | PR-A | ~250 | Grupo A + B + C |
| PR-B | SROIE pipeline eval (`run_pipeline_sroie.py` + `metrics_sroie.py`) | PR-B | ~230 | Grupo D — base: PR-A |
| PR-C | Augmentation + duplicados + eval bancario + docs | PR-C | ~300 | Grupos E + F + G — base: PR-B |

> **PR-A es el bloqueador de todo**: todos los scripts importan `_shared.py`. PR-B y PR-C son estrictamente secuenciales porque `eval_duplicates_bancario.py` depende de `pairs.csv` que genera PR-C.

---

## Grupo A — Infraestructura base

*Sin dependencias — primer commit.*

- [x] **5.0.1** Agregar a `.gitignore`: `dataset/bancario-mx/raw/`, `dataset/sroie/`, `dataset/augmented/`, `results/`.
  - **Req**: R-57
  - **Scenario**: S-50
  - **Files**: `.gitignore`
  - **Acceptance**: `git ls-files dataset/bancario-mx/raw/` → output vacío tras agregar cualquier archivo en ese dir

- [x] **5.0.2** Agregar a `api/config.py` los campos `dataset_dir: Path | None = None` y `results_dir: Path | None = None` como campos opcionales de `Settings` (Pydantic BaseSettings). Sin default env var — producción ignora estos campos.
  - **Req**: R-49b
  - **Files**: `api/config.py`
  - **Depends**: —
  - **Acceptance**: `cd api && uv run pytest tests/ -q` → 0 failures (regresión); `Settings().dataset_dir is None` en shell Python

- [x] **5.0.3** Crear estructura de directorios `dataset/bancario-mx/`: subdirectorios `ground-truth/`, `anonymized/`, `duplicates/` cada uno con `.gitkeep`.
  - **Req**: R-54, R-55, R-56
  - **Files**: `dataset/bancario-mx/ground-truth/.gitkeep`, `dataset/bancario-mx/anonymized/.gitkeep`, `dataset/bancario-mx/duplicates/.gitkeep`
  - **Acceptance**: `git status` muestra los tres `.gitkeep` como tracked; `dataset/bancario-mx/raw/` NO aparece

- [x] **5.0.4** Crear `dataset/bancario-mx/README.md`: descripción del dataset, schema GT v1.0 (todos los campos obligatorios + enum `tipo` + enum `formato_origen` + campo `calidad`), instrucciones de contribución, licencia CC BY 4.0.
  - **Req**: R-54, R-67
  - **Files**: `dataset/bancario-mx/README.md`
  - **Acceptance**: Contiene la tabla de campos GT, los enums documentados y la sección de licencia

- [x] **5.0.5** Crear `scripts/README.md`: tabla con cada script, sus args clave, el comando de invocación con `uv run python scripts/...`, y los criterios de exit 0/1.
  - **Req**: R-48, R-67
  - **Files**: `scripts/README.md`
  - **Acceptance**: Cubre los 6 scripts ejecutables; cada fila tiene comando de ejemplo y criterio de éxito

---

## Grupo B — Bootstrap de scripts

*Depende de: 5.0.2 (Settings ya tiene DATASET_DIR/RESULTS_DIR)*

- [x] **5.0.6** Crear `scripts/_shared.py` con las tres funciones exactas del diseño: `setup_api_path() -> None` (idempotente, inserta `api/` en `sys.path[0]`), `load_settings() -> Settings` (llama setup_api_path + instancia Settings), `get_ocr_client() -> httpx.AsyncClient` (base_url=settings.llama_server_url, timeout=settings.llama_timeout_s, sin context manager).
  - **Req**: R-47 (bootstrap compartido)
  - **Files**: `scripts/_shared.py`
  - **Depends**: 5.0.2
  - **Acceptance**: `uv run python -c "from scripts._shared import load_settings; s = load_settings(); print(s)"` ejecuta sin error desde raíz del repo

---

## Grupo C — Anonimización

*Depende de: 5.0.6 (_shared.py disponible)*

- [x] **5.0.7** Crear `scripts/anonymize/anonymize_comprobante.py`: CLI con args `--input`, `--output-dir`, `--gt-dir`, `--id-prefix`, `--dry-run`, `--help`. Flujo: `validate_mime()` → OCR-lite vía `get_ocr_client()` → regex CLABE/tarjeta/referencia → `PIL ImageDraw.rectangle` blur en 3 ROI zones → guarda `anonymized/{id}.jpg` + escribe `ground-truth/{id}.json` (schema v2.0 con `schema_version: "2.0"`, campos: `banco_emisor`, `banco_receptor`, `monto`, `moneda`, `fecha`, `hora`, `numero_comprobante`, `numero_referencia`, `motivo`, `clabe_emisor_mascara`, `clabe_receptor_mascara`, `tipo`, `formato_origen`, `calidad`, `notas`, `synthetic`). Exit 0 OK, exit 1 en imagen corrupta o MIME inválido.
  - **Req**: R-54, R-55, R-56, R-58, R-59, R-60
  - **Scenario**: S-44, S-45
  - **Files**: `scripts/anonymize/anonymize_comprobante.py`
  - **Depends**: 5.0.6
  - **Acceptance**: `uv run python scripts/anonymize/anonymize_comprobante.py --input <test_img.jpg> --dry-run` → imprime plan sin escribir archivos; `--input <corrupted>` → exit 1

- [x] **5.0.14** Actualizar `api/services/ocr_service.py`: agregar campo `hora` al `OCR_PROMPT` y a `CAMPOS_ESPERADOS`. Actualizar comentario de cabecera: "Plan §1.3 — actualizado 2026-05-18".
  - **Req**: R-68
  - **Files**: `api/services/ocr_service.py`
  - **Depends**: 5.0.6
  - **Acceptance**: `uv run python -c "from services.ocr_service import CAMPOS_ESPERADOS; assert 'hora' in CAMPOS_ESPERADOS"` → sin error

---

## Grupo D — SROIE pipeline eval

*Depende de: 5.0.6. Paralelo a Grupo C.*

- [x] **5.0.8** Crear `scripts/eval/run_pipeline_sroie.py`: CLI con args `--images-dir`, `--annotations-dir`, `--output-csv`, `--concurrency` (default 4), `--help`. Async con `asyncio.Semaphore(--concurrency)`. Lee CSV existente al inicio → construye `set[str]` de `image_id` procesados → skip si ya procesado (checkpoint). Columnas CSV: `image_id, gt_total, gt_date, pred_total, pred_date, match_total, match_date, error`. `match_total/match_date`: `True|False|None`. CSV en modo append. Exit 0 OK, exit 1 si no hay imágenes o llama-server inaccesible (mensaje claro: `"ERROR: llama-server unreachable at {url}"`).
  - **Req**: R-47, R-48, R-50, R-51, R-52
  - **Scenario**: S-41, S-42, S-43
  - **Files**: `scripts/eval/run_pipeline_sroie.py`
  - **Depends**: 5.0.6
  - **Acceptance**: `uv run python scripts/eval/run_pipeline_sroie.py --help` → 0; con server caído → exit 1 + mensaje `"ERROR: llama-server unreachable"`

- [x] **5.0.9** Crear `scripts/eval/metrics_sroie.py`: CLI con args `--input-csv`, `--output-json`, `--tolerance-monto` (default 0.01), `--tolerance-fecha` (default 1), `--help`. Calcula precision/recall/F1 para `monto` y `fecha` con la semántica exacta del diseño (`None` excluido de denominador de precision, cuenta como FN en recall). Escribe `sroie_metrics.json`. Exit 0 si `F1[monto] >= 0.80`, exit 1 con mensaje `"CRITERION FAILED: F1[monto]={valor}"`.
  - **Req**: R-48, R-53
  - **Scenario**: S-41, S-42
  - **Files**: `scripts/eval/metrics_sroie.py`
  - **Depends**: 5.0.8
  - **Acceptance**: `uv run python scripts/eval/metrics_sroie.py --input-csv results/sroie_results.csv` → genera JSON válido; exit 1 si F1 < 0.80

---

## Grupo E — Augmentation y duplicados

*Depende de: 5.0.7 (imágenes anonimizadas disponibles)*

- [x] **5.0.10** Crear pipeline de generación sintética + augmentación: `generate_synthetic.py` (Faker es_MX + 8 templates HTML banco + Playwright screenshot → PNG + ground-truth JSON schema v2.0) + `generate_augmented.py` refactoreado (Albumentations: rotación ±15°, JPEG q=40–70, ruido gaussiano σ=10–25, blur 3×3, perspective warp, brightness/contrast, downscale+upscale). Detección automática de modo sintético vs raw.
  - **Req**: R-64, R-65
  - **Scenario**: S-47, S-48, S-49
  - **Files**: `scripts/augment/generate_synthetic.py`, `scripts/augment/generate_augmented.py`, `scripts/augment/faker_mx.py`, `scripts/augment/templates/` (8 HTML + base.css)
  - **Depends**: 5.0.7
  - **Acceptance**: `uv run python scripts/augment/generate_synthetic.py --bank all --count 3 --output /tmp/test/ --seed 42` → 24 imágenes + 24 JSONs; `uv run python scripts/augment/generate_augmented.py --input-dir /tmp/test/images/ --gt-dir /tmp/test/ground-truth/ --output-dir /tmp/aug/ --n 24 --seed 42` → 240 augmentadas; exit 0

- [x] **5.0.11** Crear `scripts/augment/generate_duplicates.py`: CLI con args `--anonymized-dir`, `--ground-truth-dir`, `--output-csv`, `--output-degraded-dir`, `--seed 42`, `--help`. Genera pares con distribución 30/40/30 ±5% (`exacto`/`parcial_campos+parcial_visual`/`negativos`). Schema CSV: `id_a,id_b,tipo_duplicado,capa_esperada,clasificacion_esperada,notas`. `exacto` = `shutil.copy` + rename. `parcial_visual` = JPEG q=50 + rotación ±3° → guarda en `duplicates/degraded/`. `negativos` = mismo banco+fecha, monto distinto. Exit 0 OK, exit 1 si < 50 pares o distribución fuera de ±5%.
  - **Req**: R-61, R-62, R-63
  - **Scenario**: S-46
  - **Files**: `scripts/augment/generate_duplicates.py`
  - **Depends**: 5.0.7
  - **Acceptance**: `uv run python scripts/augment/generate_duplicates.py --seed 42` → exit 0; CSV generado con ≥ 50 filas; distribución 30/40/30 ±5% verificable con `python -c "import pandas as pd; df=pd.read_csv('...')..."`

---

## Grupo F — Evaluación bancario-mx

*Depende de: 5.0.7 (ground-truth JSONs), 5.0.11 (pairs.csv)*

- [x] **5.0.12** Crear `scripts/eval/eval_duplicates_bancario.py`: CLI con args `--pairs-csv`, `--anonymized-dir`, `--ground-truth-dir`, `--output-json`, `--help`. Simula capas SIN PostgreSQL: Capa 1 = `parser_service.compute_hash(img_bytes)` (importado desde `api/`), Capa 2 = comparación directa `(referencia, monto, fecha)` entre ground-truth JSONs, Capa 3 = `compute_score()` + `classify()` de `duplicate_service.py` con dataclasses que replican campos GT. Genera `bancario_metrics.json` con `capa_1`, `capa_2`, `scoring`, `confusion_matrix` 3×3, `by_quality`. Exit 0 si `capa_1.precision == 1.0`, exit 1 con `"CRITERION FAILED: capa_1.precision={valor}"`.
  - **Req**: R-64, R-65, R-66
  - **Scenario**: S-47, S-48, S-49
  - **Files**: `scripts/eval/eval_duplicates_bancario.py`
  - **Depends**: 5.0.7, 5.0.11
  - **Acceptance**: `uv run python scripts/eval/eval_duplicates_bancario.py` → JSON con todas las claves requeridas; exit 1 si `capa_1.precision < 1.0`

---

## Grupo G — Documentación

*Depende de: 5.0.9 (métricas SROIE), 5.0.12 (métricas bancario-mx). Template con placeholders — se completa tras correr los scripts con datos reales.*

- [x] **5.0.13** Crear `docs/dataset-evaluation.md`: template con secciones SROIE (tabla F1 por campo, placeholders `<!-- F1_MONTO -->` / `<!-- F1_FECHA -->`), bancario-mx (tabla precision/recall/F1 por capa, matriz de confusión, F1 por calidad), sección de análisis de errores (clases de error observadas, ejemplos), y sección de reproducibilidad (comandos exactos para regenerar resultados).
  - **Req**: R-67
  - **Scenario**: S-50 (documentación pública)
  - **Files**: `docs/dataset-evaluation.md`
  - **Depends**: 5.0.9, 5.0.12
  - **Acceptance**: Archivo existe; secciones SROIE + bancario-mx presentes; comandos de reproducibilidad ejecutables (no requieren DB); placeholders claramente marcados para rellenar con resultados reales

---

## Task Summary

| Grupo | Tasks | Focus | PR sugerido |
|-------|-------|-------|-------------|
| A — Infra base | 5 (5.0.1–5.0.5) | `.gitignore`, config, dirs, READMEs | PR-A |
| B — Bootstrap | 1 (5.0.6) | `_shared.py` | PR-A |
| C — Anonimización | 2 (5.0.7, 5.0.14) | `anonymize_comprobante.py`, `ocr_service.py` | PR-A |
| D — SROIE eval | 2 (5.0.8–5.0.9) | pipeline + métricas SROIE | PR-B |
| E — Augmentation | 2 (5.0.10–5.0.11) | augmented + duplicates | PR-C |
| F — Eval bancario | 1 (5.0.12) | eval completo sin DB | PR-C |
| G — Docs | 1 (5.0.13) | template dataset-evaluation | PR-C |
| **Total** | **14** | | |

## Requirement Coverage Matrix

| Requirement | Grupo | Task |
|------------|-------|------|
| R-47 bootstrap compartido | B | 5.0.6 |
| R-48 --help + exit codes | A, D, E, F, G | 5.0.5, 5.0.8–5.0.13 |
| R-49b config.py delta | A | 5.0.2 |
| R-50 SROIE batch async | D | 5.0.8 |
| R-51 checkpoint + Semaphore(4) | D | 5.0.8 |
| R-52 CSV con 3 estados match | D | 5.0.8 |
| R-53 F1[monto] ≥ 0.80 → exit | D | 5.0.9 |
| R-54 estructura dataset dirs | A, C | 5.0.3, 5.0.7 |
| R-55 anonimización PIL blur 3 ROI zones | C | 5.0.7 |
| R-56 ground-truth schema v2.0 | C | 5.0.7 |
| R-57 raw/ nunca en git | A | 5.0.1 |
| R-58 ≥100 comprobantes | C | 5.0.7 |
| R-59 campo `calidad` GT | C | 5.0.7 |
| R-60 campo `notas` GT | C | 5.0.7 |
| R-61 ≥50 pares | E | 5.0.11 |
| R-62 distribución 30/40/30 ±5% | E | 5.0.11 |
| R-63 seed determinista | E | 5.0.11 |
| R-64 negativos mismo banco+fecha | E, F | 5.0.11, 5.0.12 |
| R-65 augmented 500 imgs | E | 5.0.10 |
| R-66 capa_1.precision=1.0 → exit | F | 5.0.12 |
| R-67 docs/dataset-evaluation.md | A, G | 5.0.4, 5.0.13 |
| R-68 OCR hora + GT schema v2.0 | C | 5.0.7, 5.0.14 |

## Dependency Graph

```
5.0.1─┐
5.0.2─┤→ 5.0.3, 5.0.4, 5.0.5
      └→ 5.0.6 (_shared)
              ├→ 5.0.7 (anonymize) → 5.0.10
              │                    → 5.0.11 → 5.0.12
              ├→ 5.0.14 (ocr hora) ┐  [paralelo a 5.0.7]
              ├→ 5.0.8 (SROIE run) → 5.0.9 (metrics)
              └─────────────────────────────────────── 5.0.9 + 5.0.12 → 5.0.13
```
