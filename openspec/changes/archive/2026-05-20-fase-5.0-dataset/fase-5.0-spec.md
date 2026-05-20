# Fase 5.0 — Dataset Strategy — Spec

**Change:** `fase-5.0-dataset`
**Date:** 2026-05-13
**Phase:** SPEC
**Mode:** openspec
**Continues from:** fase-4-spec.md (R-46 was last requirement; S-40 was last scenario)
**Closes:** D-12 (métricas diferidas: req 1.9.1, 1.9.2, 2.7.1)

---

## Capability: dataset-evaluation

Scripts de evaluación y benchmarking del pipeline OCR + detección de duplicados sobre SROIE + bancario-mx.

### Requirements

#### R-47: Estructura de directorios dataset/ y scripts/

El repositorio MUST contener los directorios `dataset/sroie/`, `dataset/bancario-mx/`, `dataset/augmented/`, `scripts/eval/`, `scripts/augment/`, `scripts/anonymize/`. El `.gitignore` del proyecto MUST excluir `dataset/raw/`, `dataset/sroie/`, `dataset/augmented/`, y `results/` de tracking git.

#### R-48: Interfaz de scripts standalones

Cada script en `scripts/` MUST soportar la flag `--help` y retornar exit code `0` en ejecución exitosa y exit code `1` ante cualquier error. Los scripts MUST ser ejecutables directamente con `python script.py` sin importar módulos internos del API.

#### R-50: Script de evaluación SROIE — run_pipeline_sroie.py

`scripts/eval/run_pipeline_sroie.py` MUST procesar un directorio de imágenes SROIE corriendo el pipeline completo en el orden: `validate_mime → preprocess → extract_fields → parse_monto/fecha`. Los resultados MUST escribirse en un CSV incremental con columnas `image_id, monto_pred, monto_gt, fecha_pred, fecha_gt, status`.

#### R-51: Checkpoint reanudable en evaluación SROIE

`run_pipeline_sroie.py` MUST soportar checkpoint: si el CSV de salida ya existe con registros previos, el script MUST omitir las imágenes ya procesadas y continuar desde el último registro. El script MUST soportar concurrencia controlada con `asyncio.Semaphore(4)` para limitar llamadas simultáneas al servidor OCR.

#### R-52: Script de métricas SROIE — metrics_sroie.py

`scripts/eval/metrics_sroie.py` MUST calcular precision, recall y F1 por campo (`monto`, `fecha`) a partir del CSV generado por R-50. Los resultados MUST escribirse en `results/sroie_metrics.json` con schema `{ campo: { precision, recall, f1, support } }`.

#### R-53: Criterio de aceptación SROIE — F1 ≥ 0.80 en total

El F1 del campo `total` (monto) calculado por R-52 MUST ser ≥ 0.80 para que el criterio de aceptación 5.0.4.1 se considere cumplido. Si F1 < 0.80 el script MUST retornar exit code `1` e imprimir el valor obtenido con el mensaje "CRITERION FAILED".

#### R-64: Script de evaluación duplicados bancario — eval_duplicates_bancario.py

`scripts/eval/eval_duplicates_bancario.py` MUST correr el pipeline de detección sobre cada par listado en `dataset/bancario-mx/duplicates/pairs.csv`, comparar el resultado con la columna `clasificacion_esperada`, y producir una matriz de confusión + precision/recall/F1 por capa de detección.

#### R-65: Output de métricas bancario-mx

`eval_duplicates_bancario.py` MUST escribir `results/bancario_metrics.json` con schema `{ capa_1: { precision, recall, f1 }, capa_2: { precision, recall, f1 }, scoring: { precision, recall, f1 }, confusion_matrix: [[...]] }`.

#### R-66: Criterio de aceptación — precision 100% en Capa 1

El campo `capa_1.precision` en `bancario_metrics.json` MUST ser 1.0 (100%). Si no se alcanza, el script MUST retornar exit code `1` e imprimir "CRITERION FAILED: Capa 1 precision = {valor}".

### Scenarios

#### S-41: pipeline SROIE extrae total y fecha de imagen válida

- GIVEN una imagen SROIE con total legible `$1,234.56` y fecha `2022-01-15`
- WHEN `run_pipeline_sroie.py` procesa la imagen
- THEN el CSV contiene `monto_pred=1234.56` y `fecha_pred=2022-01-15`
- AND el campo `status` es `ok`

#### S-42: pipeline SROIE tolera imagen con ruido severo

- GIVEN una imagen SROIE con ruido severo donde OCR no detecta el total
- WHEN `run_pipeline_sroie.py` procesa la imagen
- THEN el CSV contiene `monto_pred=None` y `status=partial`
- AND el script NO lanza excepción ni detiene el batch

#### S-43: checkpoint SROIE reanuda desde último registro

- GIVEN el CSV ya contiene 200 registros de 973 imágenes
- WHEN `run_pipeline_sroie.py` se relanza con el mismo directorio de imágenes y CSV
- THEN el script omite las primeras 200 imágenes
- AND procesa solo las 773 restantes, sin duplicar registros en el CSV

#### S-47: duplicado exacto detectado por Capa 1 con precision 100%

- GIVEN `pairs.csv` contiene pares marcados como `tipo_duplicado=exacto` con `capa_esperada=1`
- WHEN `eval_duplicates_bancario.py` evalúa esos pares
- THEN todos los pares exactos son clasificados correctamente por hash SHA-256
- AND `capa_1.precision` en `bancario_metrics.json` es `1.0`

#### S-48: duplicado parcial escapa Capa 1 y es capturado por Capa 2 o scoring

- GIVEN un par con mismo `referencia` pero distinto `monto`, marcado `capa_esperada=2`
- WHEN `eval_duplicates_bancario.py` evalúa el par
- THEN el par no es detectado por Capa 1 (hashes difieren)
- AND el par es detectado como duplicado por Capa 2 o el scoring de similitud

#### S-49: negativo clasificado como válido (no duplicado)

- GIVEN un par con distinto banco y distinto monto, marcado `clasificacion_esperada=valido`
- WHEN `eval_duplicates_bancario.py` evalúa el par
- THEN el par es clasificado como `valido` (no duplicado)
- AND no aparece en ninguna capa de detección positiva

---

## Capability: dataset-bancario-mx

Mini-dataset bancario MX anonimizado con ground-truth, pares de duplicados controlados y documentación reproducible.

### Requirements

#### R-49: Configuración extendida en api/config.py

`api/config.py` MUST ser extendido con dos campos opcionales: `DATASET_DIR: Path | None = None` y `RESULTS_DIR: Path | None = None`. Ambos campos MUST ser configurables vía variables de entorno. La ausencia de estos valores NO MUST afectar el comportamiento de la API de producción.

#### R-54: Script de anonimización — anonymize_comprobante.py

`scripts/anonymize/anonymize_comprobante.py` MUST procesar una imagen de comprobante bancario MX y producir: (1) una imagen anonimizada con datos sensibles reemplazados/difuminados y (2) un archivo JSON de ground-truth con los campos extraídos antes de la anonimización.

#### R-55: Reglas de anonimización por tipo de dato

El script de anonimización MUST aplicar las siguientes transformaciones:
- Nombres propios → reemplazar con `"JUAN PÉREZ"` (persona) o `"EMPRESA SA"` (razón social)
- CLABEs (18 dígitos) → `****XXXX` donde `XXXX` son los últimos 4 dígitos
- Montos → valores sintéticos plausibles dentro de ±20% del original
- Referencias numéricas → `REF-{sha256_de_referencia_original[:8]}`
- PIL blur: 3 zonas ROI — top 15% (logo/header), middle 45%–90% (De/Para, nombres, CLABE, email), bottom 90%–100% (número comprobante/ID transacción)

#### R-56: Schema del JSON de ground-truth

Cada imagen anonimizada MUST tener un JSON de ground-truth con el schema v2.0 exacto:

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

El campo `monto` MUST contener el valor real (pre-anonimización).

> Schema bumped to v2.0. Field `banco` split into `banco_emisor`/`banco_receptor`. Field `referencia` split into `numero_comprobante`/`numero_referencia`. Added: `moneda`, `hora`, `motivo`, `clabe_emisor_mascara`, `clabe_receptor_mascara`, `synthetic`.

#### R-57: Protección de raw/ contra git tracking

El directorio `dataset/bancario-mx/raw/` MUST estar explícitamente listado en `.gitignore`. El proyecto MUST incluir un pre-commit hook o documentación explícita que advierta al committer si detecta archivos en `raw/` siendo staged. `raw/` NEVER MUST aparecer en el historial git.

#### R-58: Volumen mínimo del mini-dataset

El directorio `dataset/bancario-mx/anonymized/` MUST contener ≥ 100 comprobantes anonimizados, cada uno con su archivo JSON de ground-truth correspondiente en `dataset/bancario-mx/ground-truth/`.

#### R-59: Distribución mínima del mini-dataset

El mini-dataset MUST representar ≥ 3 bancos distintos y ≥ 2 formatos distintos de comprobante (screenshot, PDF digitalizado, foto). Esta distribución MUST estar documentada en el README del dataset.

#### R-60: README del dataset bancario-mx

`dataset/bancario-mx/README.md` MUST contener: descripción del dataset, instrucciones de recolección y anonimización, schema del ground-truth JSON, y declaración de licencia CC BY 4.0.

#### R-61: Script de generación de duplicados controlados

`scripts/augment/generate_duplicates.py` MUST generar `dataset/bancario-mx/duplicates/pairs.csv` con columnas `id_a, id_b, tipo_duplicado, capa_esperada, clasificacion_esperada`. El script MUST leer los comprobantes existentes en `dataset/bancario-mx/anonymized/` para construir los pares.

#### R-62: Distribución de pares de duplicados

Los pares generados por R-61 MUST seguir la distribución: 30% ± 5% duplicados exactos (`tipo_duplicado=exacto`, `capa_esperada=1`), 40% ± 5% duplicados parciales (`tipo_duplicado=parcial`, `capa_esperada=2` o `3`), 30% ± 5% negativos (`tipo_duplicado=negativo`, `clasificacion_esperada=valido`).

#### R-63: Volumen mínimo de pares

`pairs.csv` MUST contener ≥ 50 pares de duplicados al completar la fase.

#### R-67: Documentación de evaluación — dataset-evaluation.md

`docs/dataset-evaluation.md` MUST contener: tabla de F1 por campo para SROIE, tabla de precision/recall/F1 por capa para bancario-mx, análisis de errores documentando los top 5 casos de falla OCR, e instrucciones para reproducir la evaluación desde cero.

#### R-68: Campo hora en prompt OCR y schema GT v2.0

`api/services/ocr_service.py` MUST incluir el campo `hora` (string HH:MM) en `OCR_PROMPT` y en `CAMPOS_ESPERADOS`. El script `anonymize_comprobante.py` MUST leer `ocr_fields["hora"]` directamente y mapearlo al campo `hora` del ground-truth JSON v2.0.

### Scenarios

#### S-44: anonimización reemplaza CLABE visible en imagen y ground-truth

- GIVEN un comprobante con CLABE `012345678901234567` visible en la imagen
- WHEN `anonymize_comprobante.py` procesa el comprobante
- THEN la imagen resultante no contiene la CLABE original (reemplazada o difuminada)
- AND el JSON de ground-truth contiene `"referencia": "****4567"` (últimos 4)

#### S-45: anonimización preserva banco y fecha

- GIVEN un comprobante de BBVA con fecha `2026-03-15`
- WHEN `anonymize_comprobante.py` procesa el comprobante
- THEN el JSON de ground-truth contiene `"banco": "BBVA"` y `"fecha": "2026-03-15"`
- AND estos campos no son alterados por la anonimización

#### S-46: generate_duplicates respeta distribución 30/40/30 ± 5%

- GIVEN `dataset/bancario-mx/anonymized/` contiene ≥ 100 comprobantes
- WHEN `generate_duplicates.py` es ejecutado
- THEN `pairs.csv` contiene ≥ 50 pares
- AND exactos representan entre 25%–35% del total
- AND parciales representan entre 35%–45% del total
- AND negativos representan entre 25%–35% del total

#### S-50: raw/ no aparece en git ls-files

- GIVEN `.gitignore` incluye `dataset/bancario-mx/raw/`
- WHEN se ejecuta `git ls-files dataset/bancario-mx/raw/`
- THEN la salida está vacía (ningún archivo en raw/ es tracked)
- AND `git log --all -- dataset/bancario-mx/raw/` no retorna ningún commit

---

## MODIFIED Capability: api-config

> **Reference:** `api/config.py` — campos existentes de configuración de la API

### Requirement R-49b: api/config.py acepta DATASET_DIR y RESULTS_DIR

`api/config.py` MUST exponer `DATASET_DIR: Path | None = None` y `RESULTS_DIR: Path | None = None` como campos de configuración Pydantic (BaseSettings), legibles desde variables de entorno `DATASET_DIR` y `RESULTS_DIR` respectivamente. Los campos MUST ser `None` por defecto — la API de producción MUST continuar funcionando si las variables no están seteadas.
(Previously: `api/config.py` no tenía campos de configuración relacionados con dataset o resultados)

#### Scenario: API arranca sin DATASET_DIR seteado

- GIVEN las variables de entorno `DATASET_DIR` y `RESULTS_DIR` no están definidas
- WHEN la API FastAPI inicia
- THEN `settings.DATASET_DIR is None` y `settings.RESULTS_DIR is None`
- AND la API responde normalmente en `/health`

#### Scenario: DATASET_DIR configurable desde env var

- GIVEN la variable de entorno `DATASET_DIR=/data/bancario-mx`
- WHEN la API o un script importa `settings`
- THEN `settings.DATASET_DIR == Path("/data/bancario-mx")`

---

## Summary

| Capability | Tipo | Requisitos | R Range | Scenarios |
|------------|------|------------|---------|-----------|
| dataset-evaluation | New | 9 | R-47, R-48, R-50–R-53, R-64–R-66 | S-41–S-43, S-47–S-49 (6) |
| dataset-bancario-mx | New | 13 | R-49, R-54–R-63, R-67, R-68 | S-44–S-46, S-50 (4) |
| api-config | Modified delta | 1 | R-49b | 2 |
| **Total** | | **23 req (22 new + 1 modified)** | **R-47–R-68** | **12 scenarios** |

### Acceptance Criteria Mapping

| Criterio | Requisito | Scenario |
|----------|-----------|----------|
| 5.0.4.1 F1 ≥ 0.80 en total | R-53 | S-41, S-42 |
| 5.0.4.2 ≥ 100 comprobantes anonimizados | R-58 | S-44, S-45 |
| 5.0.4.3 ≥ 50 pares distribución 30/40/30 | R-62, R-63 | S-46 |
| 5.0.4.4 Capa 1 precision 100% | R-66 | S-47 |
| 5.0.4.5 docs/dataset-evaluation.md | R-67 | — |
| 5.0.4.6 raw/ nunca en git history | R-57 | S-50 |
| hora extraída en OCR y persistida en GT | R-68 | S-44, S-45 |

### Requisitos adicionales identificados

| Req | Origen | Justificación |
|-----|--------|---------------|
| R-48 | Implícito en propuesta | La propuesta asume scripts standalone; la interfaz `--help` y exit codes son necesarios para CI y reproducibilidad |
| R-51 | Riesgo "GLM-OCR lento" | Checkpoint + Semaphore(4) eran parte del approach pero sin req formal |
| R-66 exit code | Best practice | Criterio de aceptación automatizable requiere exit code verificable |
| R-53 exit code | Best practice | Ídem para SROIE — permite uso en CI sin leer JSON |
