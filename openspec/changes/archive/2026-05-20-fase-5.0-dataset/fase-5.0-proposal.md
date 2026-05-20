# Proposal: Fase 5.0 — Dataset Strategy para SmartVoucherDetection

**Change:** `fase-5.0-dataset`
**Date:** 2026-05-13
**Status:** DRAFT

---

## Intent

Las métricas de precisión OCR (req 1.9.1, 1.9.2) y precisión de detección de duplicados (req 2.7.1) fueron diferidas como D-12 por falta de dataset etiquetado. Fase 5.0 resuelve esto con una estrategia híbrida: benchmark público (SROIE v2) + mini-dataset bancario MX propio. El mini-dataset es la contribución diferenciadora de la tesis: un benchmark reproducible de comprobantes bancarios mexicanos con duplicados controlados que no existe en literatura pública.

---

## Scope

### In Scope
- Estructura de directorios `scripts/`, `dataset/`, `results/` con `.gitignore` protegiendo `raw/`
- Script de evaluación SROIE: pipeline completo → CSV → métricas F1 por campo
- Script de augmentation (Nano Receipts): genera imágenes degradadas para robustez
- Pipeline de anonimización: regex textual + PIL blur sobre comprobantes bancarios MX
- Mini-dataset bancario MX: ≥100 comprobantes anonimizados con ground-truth JSON
- Generación de duplicados controlados (distribución 30/40/30)
- Script de evaluación bancario-mx: capa 1/2/3 → matriz de confusión + F1 por clase
- `api/config.py`: agregar `DATASET_DIR`, `RESULTS_DIR`
- `docs/dataset-evaluation.md` con resultados reproducibles
- `.gitignore`: proteger `dataset/bancario-mx/raw/`, `dataset/sroie/`, `results/`

### Out of Scope
- Ajuste de pesos del scoring (`W_REF`, `THRESHOLD_DUPLICADO`) — diferido a Fase 6
- Modificaciones estructurales al pipeline OCR — solo se agrega campo `hora` al prompt para soporte de schema v2.0
- Nuevo entrenamiento o fine-tuning de GLM-OCR
- Dataset "OCR Receipts Text Detection" — omitido permanentemente (GLM-OCR es end-to-end, no usa bounding boxes de regiones)
- Repo separado para el dataset público

---

## Capabilities

### New Capabilities
- `dataset-evaluation`: Scripts de evaluación y benchmarking del pipeline OCR + detección de duplicados sobre datasets etiquetados (SROIE + bancario-mx)
- `dataset-bancario-mx`: Mini-dataset bancario MX anonimizado con ground-truth, pares de duplicados controlados y documentación reproducible

### Modified Capabilities
- `api-config`: Agregar `DATASET_DIR` y `RESULTS_DIR` como campos opcionales en `api/config.py`

---

## Approach

**3 tracks paralelos**, con dependencias controladas:

### Track A — SROIE Bench (días 1-5)
Descarga SROIE v2 → `run_pipeline_sroie.py` (reanudable, Semaphore(4), ~15 min) → `metrics_sroie.py` (F1 por campo monto/fecha) → resultados en `results/sroie_metrics.json`.

### Track B — Bancario-MX (días 1-10, paralelo a A)
Estructura directorios + `.gitignore` → `anonymize_comprobante.py` → recolección ≥100 comprobantes propios/colega → ground-truth JSON por imagen → `generate_duplicates.py` (distribución 30/40/30) → `eval_duplicates_bancario.py` (capas 1/2/3, matriz confusión) → `bancario_metrics.json`.

### Track C — Integración y Docs (días 1 en paralelo → docs al final)
Día 1: `api/config.py` + `.gitignore` + estructura `scripts/` y `dataset/`. Post-resultados: `docs/dataset-evaluation.md`.

**Dependencias**: Track C.estructura puede correr desde día 1. Track A y B son paralelos entre sí. Track C.docs requiere resultados de ambos.

---

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `scripts/eval/` | New | `run_pipeline_sroie.py`, `metrics_sroie.py`, `eval_duplicates_bancario.py` |
| `scripts/augment/` | New | `generate_augmented.py`, `generate_duplicates.py` |
| `scripts/anonymize/` | New | `anonymize_comprobante.py` — genera ground-truth schema v2.0 con campo `hora` |
| `api/services/ocr_service.py` | Modify | Prompt actualizado: campo `hora` agregado. `CAMPOS_ESPERADOS` extendido a 6 campos. |
| `dataset/sroie/` | New | Imágenes + anotaciones SROIE (no tracked en git) |
| `dataset/bancario-mx/` | New | `raw/` (gitignored), `anonymized/`, `ground-truth/`, `duplicates/` |
| `results/` | New | CSVs y JSONs de métricas (no tracked en git) |
| `api/config.py` | Modify | `DATASET_DIR: Path`, `RESULTS_DIR: Path` (opcionales) |
| `docs/dataset-evaluation.md` | New | Resultados reproducibles con metodología |
| `.gitignore` | Modify | `dataset/bancario-mx/raw/`, `dataset/sroie/`, `results/` |

---

## Risks

| Riesgo | Prob | Mitigación |
|--------|------|------------|
| Recolección <100 comprobantes MX antes de deadline | Alta | Iniciar con comprobantes propios; ajustar mínimo a ≥50 si hay restricción de tiempo |
| SROIE F1 < 0.80 en monto (heurística US/MX vs formato europeo) | Media | Documentar como "known limitation"; filtrar por locale si es necesario; F1 0.75 con análisis de error es aceptable académicamente |
| GLM-OCR lento en batch 973 imgs (~15 min) | Alta | Script reanudable con checkpoint CSV + `asyncio.Semaphore(4)` |
| Anonimización incompleta (datos legibles residuales) | Media | Revisión manual de primeros 20 comprobantes antes de procesar lote; checklist explícito |
| Umbrales de scoring no optimales revelados por el dataset | Baja | Intencional — solo medir en Fase 5.0, ajustar en Fase 6 |

---

## Rollback Plan

Los scripts son herramientas de investigación standalone — no modifican la API de producción. Rollback:
1. Eliminar `scripts/`, `dataset/`, `results/`, `docs/dataset-evaluation.md`
2. Revertir `api/config.py` (eliminar `DATASET_DIR`, `RESULTS_DIR`)
3. Revertir `.gitignore` (eliminar las 3 entradas nuevas)

El pipeline de producción no se ve afectado en ningún momento.

---

## Dependencies

- Kaggle account con `kaggle.json` configurado (Track A — descarga SROIE)
- `llama-server` corriendo con GLM-OCR (Track A — eval batch)
- Acceso a comprobantes bancarios MX reales (Track B — recolección)
- Bibliotecas: `Pillow`, `opencv-python`, `scikit-learn`, `kaggle` (todos en uv workspace)

---

## Success Criteria

- [ ] **5.0.4.1** SROIE F1 ≥ 0.80 en campo `total` (monto)
- [ ] **5.0.4.2** ≥ 100 comprobantes anonimizados en `dataset/bancario-mx/anonymized/`
- [ ] **5.0.4.3** ≥ 50 pares de duplicados en `pairs.csv` (distribución 30/40/30)
- [ ] **5.0.4.4** Pipeline detecta duplicados exactos (Capa 1) con precision 100% sobre mini-dataset
- [ ] **5.0.4.5** `docs/dataset-evaluation.md` publicado con metodología y resultados reproducibles
- [ ] **5.0.4.6** `dataset/bancario-mx/raw/` nunca aparece en `git log` (verificable con `git log --all -- dataset/bancario-mx/raw/`)
